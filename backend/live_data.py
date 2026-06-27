from typing import List, Dict, Any

import logging
import time

from .models import InstrumentType
from .sector_labels import is_unknown_sector, normalize_sector_for_symbol
from .seed_data import resolve_instrument, ALL_INSTRUMENTS
from .symbol_normalizer import canonicalize_symbol, normalize_ticker
from .krx_etf import (
    get_krx_etf_holdings,
    get_krx_etf_name,
    get_krx_stock_sector,
    is_krx_etf_symbol,
)


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


def _is_seed_direct_instrument(symbol: str) -> bool:
    """Return True when seed metadata identifies a symbol as non-fund exposure."""
    try:
        instrument_id = resolve_instrument(symbol)
        if not instrument_id:
            return False
        instrument = ALL_INSTRUMENTS.get(instrument_id)
        if not instrument:
            return False
        return instrument.instrument_type not in {InstrumentType.ETF, InstrumentType.FUND}
    except Exception:
        return False


def _krx_holdings_for_ticker(ticker: str) -> List[Dict[str, Any]]:
    """Fetch KRX ETF PDF holdings for domestic ETFs when available."""
    try:
        if not is_krx_etf_symbol(ticker):
            return []
        return get_krx_etf_holdings(ticker)
    except Exception as exc:
        LOG.warning("KRX ETF holdings lookup failed for %s: %s", ticker, exc)
        return []


def _escape_html(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _normalize_ticker(raw: Any) -> str:
    return normalize_ticker(raw)


def _position_symbol(pos: Dict[str, Any]) -> str:
    return canonicalize_symbol(
        pos.get("ticker", ""),
        pos.get("name") or pos.get("instrument_name") or pos.get("product_name"),
    )


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
        if is_krx_etf_symbol(symbol):
            return _escape_html(get_krx_etf_name(symbol)), "기타"
        krx_sector = get_krx_stock_sector(symbol)
        if krx_sector:
            return _escape_html(symbol), normalize_sector_for_symbol(symbol, krx_sector)
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


def analyze_live_portfolio(positions: List[Dict[str, Any]], source_mode: str = "seed_fast") -> Dict[str, Any]:
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
    mode = "live" if str(source_mode or "").lower() in {"live", "realtime", "real"} else "seed_fast"

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
        "krx": 0,
        "seed": 0,
        "seed_fast": 0,
        "seed_fallback": 0,
        "direct": 0,
        "invalid": 0,
        "positions_requested": 0,
        "source_mode": mode,
    }
    resolved_meta_map: dict[str, tuple[str, str]] = {}

    _log("INFO", "입력 수집 시작", f"요청 포지션 수신: {len(positions)}건")
    for idx, pos in enumerate(positions, start=1):
        ticker = _position_symbol(pos)
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

        # Determine if it's likely an ETF or stock.
        # seed_fast mode uses known seed compositions first for speed, while live mode
        # forces KRX/yfinance lookup and keeps seed only as a fallback.
        seed_holdings = _seed_holdings_for_ticker(ticker)
        if mode == "seed_fast" and seed_holdings:
            holdings = seed_holdings
            source = "seed_fast"
            source_metrics["seed"] += 1
            source_metrics["seed_fast"] += 1
            _log(
                "INFO",
                "데이터 수집 (시드 fast)",
                f"{ticker}: 속도 우선 경로로 시드 구성종목 {len(holdings)}개 즉시 사용",
                {
                    "ticker": ticker,
                    "source": "seed_data_fast",
                    "count": len(holdings),
                    "top": [h.get("holding_symbol") for h in holdings[:5]],
                },
            )
        elif is_krx_etf_symbol(ticker):
            krx_holdings = _krx_holdings_for_ticker(ticker)
            if krx_holdings:
                holdings = krx_holdings
                source = "krx"
                source_metrics["krx"] += 1
                _log(
                    "INFO",
                    "데이터 수집 (KRX)",
                    f"{ticker}: KRX ETF PDF에서 구성종목 {len(holdings)}개 조회",
                    {
                        "ticker": ticker,
                        "source": "krx_pdf",
                        "count": len(holdings),
                        "top": [h.get("holding_symbol") for h in holdings[:5]]
                    }
                )
            else:
                holdings = []
                source = ""
                if seed_holdings:
                    holdings = seed_holdings
                    source = "seed"
                    source_metrics["seed"] += 1
                    source_metrics["seed_fallback"] += 1
                    _log(
                        "WARN",
                        "데이터 수집 (시드 fallback)",
                        f"{ticker}: KRX 실데이터 조회 실패로 시드 구성종목 {len(holdings)}개 사용",
                        {
                            "ticker": ticker,
                            "source": "seed_data_fallback",
                            "count": len(holdings),
                            "top": [h.get("holding_symbol") for h in holdings[:5]],
                        },
                    )
        elif _is_seed_direct_instrument(ticker):
            holdings = []
            source = "direct"
        else:
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
                holdings = []
                source = ""
                if seed_holdings:
                    holdings = seed_holdings
                    source = "seed"
                    source_metrics["seed"] += 1
                    source_metrics["seed_fallback"] += 1
                    _log(
                        "WARN",
                        "데이터 수집 (시드 fallback)",
                        f"{ticker}: yfinance 구성종목 조회 실패로 시드 구성종목 {len(holdings)}개 사용",
                        {
                            "ticker": ticker,
                            "source": "seed_data_fallback",
                            "count": len(holdings),
                            "top": [h.get("holding_symbol") for h in holdings[:5]],
                        },
                    )

        if not holdings:
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
                h_sym = canonicalize_symbol(h.get("holding_symbol", ""), h.get("holding_name", ""))
                if not h_sym:
                    continue
                h_weight = h["weight"]
                h_amt = amount * h_weight
                h_name = _escape_html(str(h.get("holding_name", h_sym)))
                meta_name, meta_sector = _resolve_asset_metadata(h_sym)
                if meta_name and meta_name != _escape_html(h_sym):
                    h_name = meta_name
                # yfinance/seed sector를 우선 사용하고, 없으면 KRX 공식 업종명으로 보강한다.
                raw_sector = h.get("sector")
                if is_unknown_sector(raw_sector):
                    if not is_unknown_sector(meta_sector):
                        raw_sector = meta_sector
                if is_unknown_sector(raw_sector):
                    try:
                        uid = resolve_instrument(h_sym)
                        inst = ALL_INSTRUMENTS.get(uid) if uid else None
                        if inst and inst.sector:
                            raw_sector = inst.sector
                    except Exception:
                        pass
                if is_unknown_sector(raw_sector):
                    krx_sector = get_krx_stock_sector(h_sym)
                    if krx_sector:
                        raw_sector = krx_sector
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
            "name": resolved_meta_map.get(_position_symbol(p), (_escape_html(_position_symbol(p)), "기타"))[0],
            "value": p.get("amount", 0),
        } for p in positions if _position_symbol(p)],
        "sectors": sectors,
        "source_summary": source_metrics,
        "debug_trace": trace,
        "duration_ms": int((time.time() - started_at) * 1000),
        "nodes": nodes,
        "links": links
    }
