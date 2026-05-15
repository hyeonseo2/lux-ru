from typing import List, Dict, Any

import logging
import re
import time

from .sector_labels import normalize_sector, normalize_sector_for_symbol
from .seed_data import resolve_instrument, ALL_INSTRUMENTS


LOG = logging.getLogger(__name__)


def _get_holdings_from_crawler(symbol: str) -> List[Dict[str, Any]]:
    """Load holdings using crawler dependency only when endpoint is used."""
    try:
        from .worker.crawler import fetch_us_etf_holdings
    except Exception as exc:
        LOG.warning("Crawler module not available for holdings lookup: %s", exc)
        return []
    return fetch_us_etf_holdings(symbol)


def _seed_holdings_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """
    Fallback composition for known ETFs from seed data.
    """
    try:
        from .seed_data import ETF_HOLDINGS, resolve_instrument, ALL_INSTRUMENTS
    except Exception:
        return []

    instrument_id = resolve_instrument(ticker)
    if not instrument_id:
        return []

    snap = ETF_HOLDINGS.get(instrument_id)
    if not snap or not getattr(snap, "holdings", None):
        return []

    result: List[Dict[str, Any]] = []
    total_weight = 0.0
    for h in snap.holdings:
        inst = ALL_INSTRUMENTS.get(h.holding_instrument_id)
        if not inst:
            continue
        w = float(h.weight)
        if w <= 0:
            continue
        total_weight += w
        result.append({
            "holding_symbol": inst.symbol,
            "holding_name": inst.name_ko or h.name,
            "weight": w,
            "currency": h.currency,
            "country": h.country,
            "sector": h.sector or inst.sector or "Other",
        })

    if total_weight > 0 and total_weight < 0.98:
        for r in result:
            r["weight"] = r["weight"] / total_weight

    return result


def _escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _normalize_ticker(raw: Any) -> str:
    text = str(raw or "").upper().strip()
    text = re.sub(r"[^A-Z0-9.\-]", "", text)
    return text[:20]


def _resolve_asset_metadata(symbol: str) -> tuple[str, str]:
    """
    Resolve display name and sector from seed metadata when available.
    """
    try:
        from .seed_data import resolve_instrument, ALL_INSTRUMENTS
    except Exception:
        return _escape_html(symbol), normalize_sector_for_symbol(symbol, None)

    instrument_id = resolve_instrument(symbol)
    if not instrument_id:
        return _escape_html(symbol), normalize_sector_for_symbol(symbol, None)

    instrument = ALL_INSTRUMENTS.get(instrument_id)
    if not instrument:
        return _escape_html(symbol), normalize_sector_for_symbol(symbol, None)

    display_name = instrument.name_ko or instrument.name_en or symbol
    # symbol(또는 단축코드)을 우선 사용해 반도체/2차전지 본업 종목을 정확히 라벨링.
    label_sector = normalize_sector_for_symbol(instrument.symbol or symbol, instrument.sector)
    return _escape_html(display_name), label_sector


def _normalize_account(raw: Any) -> tuple[str, str]:
    text = str(raw or "").strip().lower().replace(" ", "")
    if text in {"stock", "taxable", "주식", "주식계좌", "개인", "개인계좌", "개인운용"}:
        return "주식계좌", "taxable"
    if text in {"pension", "pension_saving", "연금저축", "연금", "연금저축계좌", "pensionsaving"}:
        return "연금저축", "pension_saving"
    if text in {"isa", "isA", "연금저축운용", "개인종합", "personalisa"}:
        return "ISA", "isa"
    if text in {"irp", "개인형IRP", "개인형퇴직연금", "퇴직연금"}:
        return "IRP", "irp"
    if text in {"deposit", "cash", "입출금", "예수금", "savings", "적금"}:
        return "예수금/입출금", "deposit"
    return "기타", "etc"


def analyze_live_portfolio(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build a dynamic persona graph from user-input positions.
    positions: [{"ticker": "SPY", "amount": 10000000}, ...]
    """
    nodes = []
    links = []
    total_value = 0
    sectors = {}
    trace = []
    started_at = time.time()

    def _log(level: str, title: str, detail: str, payload: Dict[str, Any] | None = None):
        entry = {
            "ts": time.time(),
            "level": level,
            "title": title,
            "detail": detail,
        }
        if payload:
            entry["payload"] = payload
        trace.append(entry)

    # Track unique items
    account_nodes: dict[str, Dict[str, Any]] = {}

    def get_account_node(raw_account: Any) -> dict[str, Any]:
        account_label, account_key = _normalize_account(raw_account)
        if account_key not in account_nodes:
            account_nodes[account_key] = {
                "id": f"Account_{account_key}",
                "group": 1,
                "type": "account",
                "val": 0,
                "name": account_label
            }
            nodes.append(account_nodes[account_key])
        return account_nodes[account_key]

    stock_exposures = {}  # stock_symbol -> amount
    source_metrics = {
        "yfinance": 0,
        "seed": 0,
        "direct": 0,
        "invalid": 0,
        "positions_requested": 0,
    }
    resolved_meta_map: dict[str, tuple[str, str]] = {}

    _log("INFO", "입력 수집 시작", f"요청 포지션 수신: {len(positions)}건")
    for idx, pos in enumerate(positions, start=1):
        ticker = _normalize_ticker(pos.get("ticker", ""))
        amount = float(pos.get("amount", 0))
        if amount <= 0 or not ticker:
            _log("WARN", "입력 스킵", f"{idx}번 항목 누락/무효 (ticker={ticker}, amount={amount})")
            source_metrics["invalid"] += 1
            continue

        if ticker not in resolved_meta_map:
            resolved_meta_map[ticker] = _resolve_asset_metadata(ticker)

        product_name, product_sector = resolved_meta_map[ticker]
        account_node = get_account_node(pos.get("account_type") or pos.get("account_label") or "taxable")
        total_value += amount
        account_node["val"] += amount
        source_metrics["positions_requested"] += 1

        _log("DEBUG", "정규화", f"{idx}번: {ticker} / {int(amount):,}원 정규화 완료")

        # Determine if it's likely an ETF or Stock
        # If yfinance returns empty, use static fallback for known ETFs
        raw_holdings = _get_holdings_from_crawler(ticker)
        if raw_holdings:
            holdings = raw_holdings
            source = "yfinance"
            source_metrics["yfinance"] += 1
            _log(
                "INFO",
                "데이터 수집 (실시간)",
                f"{ticker}: yfinance에서 상위 보유종목 {len(holdings)}개 수집",
                {
                    "ticker": ticker,
                    "source": "yfinance",
                    "count": len(holdings),
                    "top": [h.get("holding_symbol") for h in holdings[:5]]
                }
            )
        else:
            seed_holdings = _seed_holdings_for_ticker(ticker)
            if seed_holdings:
                holdings = seed_holdings
                source = "seed"
                source_metrics["seed"] += 1
                _log(
                    "INFO",
                    "데이터 수집 (시드)",
                    f"{ticker}: 시드 데이터에서 상위 보유종목 {len(holdings)}개 조회",
                    {
                        "ticker": ticker,
                        "source": "seed_data",
                        "count": len(holdings),
                        "top": [h.get("holding_symbol") for h in holdings[:5]]
                    }
                )
            else:
                holdings = []
                source = "direct"
                source_metrics["direct"] += 1
                _log("INFO", "데이터 수집 (직접종목)", f"{ticker}: 보유종목 미확보로 직접 보유로 처리")
                _log(
                    "DEBUG",
                    "보유 비중 추정",
                    f"{ticker}: 보유 금액 {int(amount):,}원을 직접 종목으로 100% 노출 반영"
                )

        if holdings:
            # It's an ETF
            etf_id = f"ETF_{ticker}"
            nodes.append({
                "id": etf_id,
                "group": 2,
                "type": "fund",
                "val": amount,
                "name": product_name,
            })
            links.append({"source": account_node["id"], "target": etf_id, "value": amount})
            _log("DEBUG", "노드 생성", f"{ticker} 상품 노드 생성, 계좌 연결선 등록")

            for h in holdings:
                h_sym = _normalize_ticker(h.get("holding_symbol", ""))
                if not h_sym:
                    continue
                h_weight = h["weight"]
                h_amt = amount * h_weight
                h_name = _escape_html(str(h.get("holding_name", h_sym)))
                # 보유 종목의 raw sector + symbol을 모두 활용해 반도체/2차전지 본업을 격상.
                raw_sector = h.get("sector")
                # yfinance top-holdings 경로는 sector를 "Other"로 반환하는 경우가 많다.
                # 시드 메타에 있는 종목이면 해당 섹터로 보정해 과도한 "기타" 쏠림을 줄인다.
                if str(raw_sector or "").strip().lower() in {"", "other", "unknown", "none", "n/a"}:
                    try:
                        uid = resolve_instrument(h_sym)
                        inst = ALL_INSTRUMENTS.get(uid) if uid else None
                        if inst and inst.sector:
                            raw_sector = inst.sector
                    except Exception:
                        pass
                h_sector = normalize_sector_for_symbol(h_sym, raw_sector)

                if h_sym not in stock_exposures:
                    stock_exposures[h_sym] = {"name": h_name, "val": 0, "sector": h_sector}
                stock_exposures[h_sym]["val"] += h_amt

                links.append({"source": etf_id, "target": f"Stock_{h_sym}", "value": h_amt})
                _log("TRACE", "계산 내역", f"{etf_id} -> Stock_{h_sym}: {h_amt:,.0f}원 반영 (비중 {h_weight:.4f})")

                # Sector accumulation
                sec = h_sector
                sectors[sec] = sectors.get(sec, 0) + (h_weight * amount)
                _log("TRACE", "섹터 집계", f"{sec}: +{(h_weight * amount):,.0f}원", {"ticker": h_sym, "sector": sec})
        else:
            # It's a single stock
            stk_id = f"Stock_{ticker}"
            stock_name, stock_sector = product_name, product_sector
            if ticker not in stock_exposures:
                stock_exposures[ticker] = {
                    "name": stock_name,
                    "val": 0,
                    "sector": stock_sector
                }
            stock_exposures[ticker]["val"] += amount
            _log("DEBUG", "노드 생성", f"직접보유 종목 노드 등록: {ticker}")

            links.append({"source": account_node["id"], "target": stk_id, "value": amount})
            sectors[stock_sector] = sectors.get(stock_sector, 0) + amount

    # Add stock nodes
    for sym, data in stock_exposures.items():
            nodes.append({"id": f"Stock_{sym}", "group": 3, "type": "stock", "val": data["val"], "name": data["name"], "sector": data["sector"]})

    # Calculate HHI
    hhi = 0
    max_exp = {"name": "", "pct": 0}
    _log("INFO", "최종 집계", f"노드 {len(nodes)}개, 링크 {len(links)}개 집계")
    if total_value > 0:
        for sym, data in stock_exposures.items():
            pct = data["val"] / total_value
            hhi += (pct * 100) ** 2
            if pct * 100 > max_exp["pct"]:
                max_exp = {"name": data["name"], "pct": pct * 100}

        # Normalize sectors
        for sec in sectors:
            sectors[sec] /= total_value
        _log("INFO", "비중 정규화", "섹터 비중 정규화 완료")
    else:
        _log("WARN", "데이터 비정상", "유효한 금액 총합이 0입니다. 입력을 확인하세요.")

    return {
        "name": "내 포트폴리오 (라이브 연동)",
        "total_value": total_value,
        "hhi": hhi,
        "max_exposure": max_exp,
        "description": "사용자가 직접 입력한 실시간 포트폴리오 분석 결과",
        "positions": [{
            "account": _normalize_account(p.get("account_type", p.get("account_label")))[0],
            "name": resolved_meta_map.get(_normalize_ticker(p.get("ticker", "")), (_escape_html(_normalize_ticker(p.get("ticker", ""))), "기타"))[0],
            "value": p.get("amount", 0),
        } for p in positions if _normalize_ticker(p.get("ticker", ""))],
        "sectors": sectors,
        "source_summary": source_metrics,
        "debug_trace": trace,
        "duration_ms": int((time.time() - started_at) * 1000),
        "nodes": nodes,
        "links": links
    }
