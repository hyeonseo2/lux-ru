"""Historical event backtest engine.

사용자가 입력한 포트폴리오를 과거의 실제 시장 충격 기간에 대입해
종목별 실측 수익률과 포트폴리오 일별 평가액 시계열을 산출한다.

데이터 소스
-----------
- yfinance 일봉 (Close).
- 한국 종목/ETF는 `<코드>.KS` 접미사로 조회.
- 채권형 종목(`BOND_*`)은 KODEX 종합채권(273130.KS)을 프록시로 사용.

캐시
----
프로세스 메모리, 키 = (yfinance 심볼, start, end). TTL 7일.
"""
from __future__ import annotations

from bisect import bisect_right
import copy
from datetime import date, timedelta
import logging
import os
import time
from typing import Any, Optional

LOG = logging.getLogger(__name__)

# ── Scenarios ─────────────────────────────────────────────────────

SCENARIOS: dict[str, dict[str, Any]] = {
    "covid_2020": {
        "id": "covid_2020",
        "name": "2020년 코로나19 초기 충격",
        "subtitle": "팬데믹 공포, 글로벌 위험회피",
        "start": "2020-02-19",
        "end": "2020-03-24",
        "rationale": (
            "2020년 2-3월 약 한 달간 팬데믹 공포로 S&P 500이 -34%, KOSPI가 -33% 급락했던 "
            "실제 시장 데이터입니다."
        ),
    },
    "rate_hike_2022": {
        "id": "rate_hike_2022",
        "name": "2022년 미 연준 급격한 금리 인상기",
        "subtitle": "성장주 압박, 채권 약세",
        "start": "2022-01-03",
        "end": "2022-10-14",
        "rationale": (
            "2022년 연준이 기준금리를 0%에서 4%까지 급격히 인상하며 NASDAQ -36%, "
            "KOSPI -28%까지 하락한 실제 시장 데이터입니다."
        ),
    },
    "trade_war_2018": {
        "id": "trade_war_2018",
        "name": "2018년 미중 무역분쟁",
        "subtitle": "관세 정책 및 글로벌 수출주 압박",
        "start": "2018-01-26",
        "end": "2018-12-24",
        "rationale": (
            "2018년 미국 관세 부과 발표 이후 약 11개월간 KOSPI -25%, 글로벌 IT 평균 "
            "-18% 하락했던 실제 시장 데이터입니다."
        ),
    },
    "financial_crisis_2008": {
        "id": "financial_crisis_2008",
        "name": "2008년 글로벌 금융위기",
        "subtitle": "리먼브라더스 파산 직후 6개월",
        "start": "2008-09-15",
        "end": "2009-03-09",
        "rationale": (
            "리먼브라더스 파산(2008-09-15)부터 약 6개월간 S&P 500 -47%, KOSPI -45% "
            "급락했던 실제 시장 데이터입니다."
        ),
    },
    "nvidia_2024": {
        "id": "nvidia_2024",
        "name": "2024년 엔비디아 어닝쇼크",
        "subtitle": "AI 반도체 수요 우려",
        "start": "2024-07-15",
        "end": "2024-09-06",
        "rationale": (
            "2024년 8월 엔비디아 실적 발표 전후 약 한 달간 글로벌 AI 반도체 종목이 "
            "평균 -15% 변동했던 실제 시장 데이터입니다."
        ),
    },
}


# ── Cache ─────────────────────────────────────────────────────────

# (yfinance_symbol, start, end) -> (close_series_dict, expires_at_unix)
# close_series_dict는 {iso_date_str: float} 형태로 보관 (pandas 의존성 회피).
_PRICE_CACHE: dict[tuple[str, str, str], tuple[dict[str, float], float]] = {}
DEFAULT_TTL_SECONDS = 7 * 24 * 3600
_BENCHMARK_RESULT_CACHE: dict[tuple[Any, ...], tuple[dict[str, Any], float]] = {}
BENCHMARK_RESULT_TTL_SECONDS = int(os.getenv("BENCHMARK_RESULT_TTL_SECONDS", str(6 * 3600)))


# ── Symbol mapping ────────────────────────────────────────────────

BOND_PROXY = "273130.KS"  # KODEX 종합채권(AA-이상)액티브
BENCHMARK_SYMBOLS: dict[str, str] = {
    "kospi": "^KS11",
    "sp500": "^GSPC",
    "nasdaq": "^IXIC",
}


def map_to_yfinance(ticker: str) -> Optional[str]:
    """포트폴리오 ticker → yfinance 심볼 변환. 매핑 불가시 None."""
    t = (ticker or "").strip().upper()
    if not t:
        return None
    if t.startswith("BOND_") or t.startswith("CASH_"):
        return BOND_PROXY
    # 6자리 숫자 → 한국 상장 종목/ETF (.KS 우선, KOSDAQ은 .KQ이지만 .KS로도 거의 매칭됨)
    if t.isdigit() and len(t) == 6:
        return f"{t}.KS"
    # 그 외 영문 티커는 그대로
    return t


# ── Fetcher ───────────────────────────────────────────────────────

def _fetch_series_bulk(symbols: list[str], start: str, end: str) -> dict[str, dict[str, float]]:
    """yfinance.download 한 번에 다종목 조회. 실패 시 빈 dict 반환."""
    out: dict[str, dict[str, float]] = {}
    if not symbols:
        return out

    try:
        import yfinance as yf
    except Exception as exc:
        LOG.warning("yfinance unavailable: %s", exc)
        return out

    try:
        df = yf.download(
            symbols,
            start=start,
            end=end,
            progress=False,
            auto_adjust=True,
            group_by="ticker",
            threads=True,
            timeout=6,
        )
    except Exception as exc:
        LOG.warning("yfinance.download(%s) failed: %s", symbols, exc)
        return out

    if df is None or df.empty:
        return out

    # yfinance.download의 컬럼 구조:
    #   - group_by="ticker"이고 단일/다중 심볼 모두 (sym, field) MultiIndex 가능
    #   - 일부 버전·옵션은 단일 심볼일 때 평탄 컬럼(field)을 반환
    # 두 경우 모두 견고하게 처리.
    is_multi = getattr(df.columns, "nlevels", 1) > 1

    for sym in symbols:
        try:
            ser = None
            if is_multi:
                try:
                    ser = df[sym]["Close"].dropna()
                except Exception:
                    # 단일 심볼인데 평탄 컬럼인 경우 fallback
                    if "Close" in df.columns and len(symbols) == 1:
                        ser = df["Close"].dropna()
            else:
                if "Close" in df.columns and len(symbols) == 1:
                    ser = df["Close"].dropna()

            if ser is not None and len(ser) > 0:
                out[sym] = {str(idx.date()): float(v) for idx, v in ser.items()}
        except Exception:
            continue
    return out


def fetch_prices(symbols: list[str], start: str, end: str) -> dict[str, dict[str, float]]:
    """캐시 + bulk fetch. 결과는 {symbol: {iso_date: close}}."""
    now = time.time()
    out: dict[str, dict[str, float]] = {}
    missing: list[str] = []

    for sym in set(symbols):
        cached = _PRICE_CACHE.get((sym, start, end))
        if cached and cached[1] > now:
            out[sym] = cached[0]
        else:
            missing.append(sym)

    if missing:
        fetched = _fetch_series_bulk(missing, start, end)
        for sym, series in fetched.items():
            _PRICE_CACHE[(sym, start, end)] = (series, now + DEFAULT_TTL_SECONDS)
            out[sym] = series

    return out


def _prepare_series_lookup(series: dict[str, float]) -> tuple[list[str], list[float]]:
    dates = sorted(series.keys())
    values = [float(series[d]) for d in dates]
    return dates, values


def _value_on_or_before(dates: list[str], values: list[float], target_date: str) -> Optional[float]:
    if not dates:
        return None
    idx = bisect_right(dates, target_date) - 1
    if idx < 0:
        return None
    return values[idx]


# ── Backtest ──────────────────────────────────────────────────────

def list_scenarios() -> list[dict[str, Any]]:
    """클라이언트가 시나리오 목록을 받기 위한 헬퍼."""
    return [
        {k: v for k, v in sc.items() if k != "rationale"}
        | {"rationale": sc["rationale"]}
        for sc in SCENARIOS.values()
    ]


def compute_backtest(positions: list[dict[str, Any]], scenario_id: str) -> dict[str, Any]:
    """Run a historical backtest of `positions` over `scenario_id`'s period.

    Args:
        positions: [{ticker, amount, account_type?}] — amount는 KRW.
        scenario_id: SCENARIOS의 키.

    Returns:
        {status, scenario, period, rationale, total_impact_pct, total_loss_value,
         ticker_impacts: [...], daily_series: [{date, value}], data_coverage: %}
    """
    sc = SCENARIOS.get(scenario_id)
    if not sc:
        return {"status": "error", "message": f"unknown scenario: {scenario_id}"}

    start, end = sc["start"], sc["end"]

    # 입력 정규화
    valid = []
    for p in positions or []:
        ticker = str(p.get("ticker", "")).strip()
        try:
            amount = float(p.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if ticker and amount > 0:
            yf_sym = map_to_yfinance(ticker)
            valid.append({"ticker": ticker, "amount": amount, "yf_symbol": yf_sym})
    if not valid:
        return {"status": "error", "message": "no valid positions"}

    total_value = sum(p["amount"] for p in valid)
    unique_symbols = sorted({p["yf_symbol"] for p in valid if p["yf_symbol"]})
    prices = fetch_prices(unique_symbols, start, end)

    # 종목별 수익률
    ticker_impacts = []
    portfolio_impact = 0.0
    matched_amount = 0.0

    for p in valid:
        series = prices.get(p["yf_symbol"]) if p["yf_symbol"] else None
        if not series or len(series) < 2:
            ticker_impacts.append({
                "ticker": p["ticker"],
                "yf_symbol": p["yf_symbol"],
                "amount": p["amount"],
                "weight": p["amount"] / total_value if total_value else 0,
                "return_pct": 0.0,
                "data_source": "no_data",
            })
            continue

        sorted_dates = sorted(series.keys())
        first_price = series[sorted_dates[0]]
        last_price = series[sorted_dates[-1]]
        ret = (last_price / first_price - 1.0) if first_price > 0 else 0.0

        weight = p["amount"] / total_value if total_value else 0
        portfolio_impact += ret * weight
        matched_amount += p["amount"]

        ticker_impacts.append({
            "ticker": p["ticker"],
            "yf_symbol": p["yf_symbol"],
            "amount": p["amount"],
            "weight": weight,
            "return_pct": ret * 100,
            "data_source": "yfinance",
        })

    ticker_impacts.sort(key=lambda x: x["return_pct"])

    # 일별 시계열
    all_dates: set[str] = set()
    for series in prices.values():
        all_dates.update(series.keys())
    sorted_dates = sorted(all_dates)

    daily_series = []
    for d in sorted_dates:
        v = 0.0
        for p in valid:
            series = prices.get(p["yf_symbol"]) if p["yf_symbol"] else None
            if not series:
                v += p["amount"]
                continue
            sd = sorted(series.keys())
            first = series[sd[0]]
            # 해당 날짜 또는 가장 가까운 이전 거래일 사용
            if d in series:
                cur = series[d]
            else:
                prior = [x for x in sd if x <= d]
                cur = series[prior[-1]] if prior else first
            v += p["amount"] * (cur / first if first > 0 else 1.0)
        daily_series.append({"date": d, "value": v})

    data_coverage = (matched_amount / total_value) if total_value else 0

    return {
        "status": "success",
        "scenario_id": scenario_id,
        "name": sc["name"],
        "subtitle": sc["subtitle"],
        "period": f"{start} ~ {end}",
        "start": start,
        "end": end,
        "rationale": sc["rationale"],
        "total_impact_pct": portfolio_impact * 100,
        "total_loss_value": total_value * portfolio_impact,
        "total_value_before": total_value,
        "total_value_after": total_value * (1 + portfolio_impact),
        "data_coverage": data_coverage,
        "ticker_impacts": ticker_impacts,
        "daily_series": daily_series,
    }


def compute_benchmark_comparison(
    positions: list[dict[str, Any]],
    period_days: int = 365,
) -> dict[str, Any]:
    """Compare portfolio return series against benchmark indices.

    Args:
        positions: [{ticker, amount}] (amount in KRW)
        period_days: lookback window in days (clamped 90~1825)

    Returns:
        {
          status, start, end, period_days, data_coverage,
          summary: {portfolio_return_pct, kospi_return_pct, sp500_return_pct, nasdaq_return_pct},
          series: [{date, portfolio_return_pct, kospi_return_pct, sp500_return_pct, nasdaq_return_pct}]
        }
    """
    days = int(period_days or 365)
    days = max(90, min(days, 1825))

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days)
    start = start_date.isoformat()
    end = end_date.isoformat()

    raw_valid: list[dict[str, Any]] = []
    for p in positions or []:
        ticker = str(p.get("ticker", "")).strip()
        try:
            amount = float(p.get("amount", 0))
        except (TypeError, ValueError):
            amount = 0.0
        if not ticker or amount <= 0:
            continue
        yf_symbol = map_to_yfinance(ticker)
        raw_valid.append({
            "ticker": ticker,
            "amount": amount,
            "yf_symbol": yf_symbol,
        })

    if not raw_valid:
        return {"status": "error", "message": "no valid positions"}

    total_value = sum(p["amount"] for p in raw_valid)
    aggregated: dict[str, dict[str, Any]] = {}
    for p in raw_valid:
        key = p["yf_symbol"] or p["ticker"]
        if key not in aggregated:
            aggregated[key] = {
                "ticker": p["ticker"],
                "amount": 0.0,
                "yf_symbol": p["yf_symbol"],
            }
        aggregated[key]["amount"] += p["amount"]

    valid = sorted(aggregated.values(), key=lambda x: x["amount"], reverse=True)

    cache_key = (
        start,
        end,
        days,
        tuple((p["yf_symbol"] or p["ticker"], round(float(p["amount"]), 2)) for p in valid),
    )
    now = time.time()
    cached = _BENCHMARK_RESULT_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return copy.deepcopy(cached[0])

    bench_symbols = list(BENCHMARK_SYMBOLS.values())
    target_symbols = sorted({
        *(p["yf_symbol"] for p in valid if p["yf_symbol"]),
        *bench_symbols,
    })
    prices = fetch_prices(target_symbols, start, end)

    # 포지션별 룩업 준비
    portfolio_nodes: list[dict[str, Any]] = []
    matched_amount = 0.0
    for p in valid:
        series = prices.get(p["yf_symbol"]) if p["yf_symbol"] else None
        if not series or len(series) < 2:
            portfolio_nodes.append({
                **p,
                "has_data": False,
                "dates": [],
                "values": [],
                "first": None,
            })
            continue

        dates, values = _prepare_series_lookup(series)
        first = values[0] if values and values[0] > 0 else None
        if first is None:
            portfolio_nodes.append({
                **p,
                "has_data": False,
                "dates": [],
                "values": [],
                "first": None,
            })
            continue
        matched_amount += p["amount"]
        portfolio_nodes.append({
            **p,
            "has_data": True,
            "dates": dates,
            "values": values,
            "first": first,
        })

    # 벤치마크 룩업 준비
    benchmark_lookup: dict[str, dict[str, Any]] = {}
    for key, sym in BENCHMARK_SYMBOLS.items():
        series = prices.get(sym)
        if not series or len(series) < 2:
            benchmark_lookup[key] = {
                "has_data": False,
                "dates": [],
                "values": [],
                "first": None,
            }
            continue
        dates, values = _prepare_series_lookup(series)
        first = values[0] if values and values[0] > 0 else None
        benchmark_lookup[key] = {
            "has_data": first is not None,
            "dates": dates,
            "values": values,
            "first": first,
        }

    # 타임라인은 벤치마크 거래일 우선
    all_dates: set[str] = set()
    for key in ("kospi", "sp500", "nasdaq"):
        b = benchmark_lookup.get(key) or {}
        for d in b.get("dates", []):
            all_dates.add(d)
    if not all_dates:
        for n in portfolio_nodes:
            for d in n.get("dates", []):
                all_dates.add(d)

    sorted_dates = sorted(all_dates)
    if not sorted_dates:
        return {"status": "error", "message": "insufficient market data"}

    series_rows: list[dict[str, Any]] = []
    for d in sorted_dates:
        portfolio_value = 0.0
        for n in portfolio_nodes:
            if not n["has_data"]:
                portfolio_value += n["amount"]
                continue
            cur = _value_on_or_before(n["dates"], n["values"], d)
            if cur is None:
                cur = n["first"]
            factor = cur / n["first"] if n["first"] and n["first"] > 0 else 1.0
            portfolio_value += n["amount"] * factor
        portfolio_return = (portfolio_value / total_value - 1.0) * 100 if total_value > 0 else 0.0

        row = {
            "date": d,
            "portfolio_return_pct": portfolio_return,
            "kospi_return_pct": None,
            "sp500_return_pct": None,
            "nasdaq_return_pct": None,
        }

        for bench_key, out_key in (
            ("kospi", "kospi_return_pct"),
            ("sp500", "sp500_return_pct"),
            ("nasdaq", "nasdaq_return_pct"),
        ):
            b = benchmark_lookup.get(bench_key) or {}
            if not b.get("has_data"):
                continue
            cur = _value_on_or_before(b["dates"], b["values"], d)
            if cur is None:
                cur = b["first"]
            ret = (cur / b["first"] - 1.0) * 100 if b["first"] and b["first"] > 0 else 0.0
            row[out_key] = ret

        series_rows.append(row)

    last_row = series_rows[-1]
    data_coverage = (matched_amount / total_value) if total_value > 0 else 0.0
    result = {
        "status": "success",
        "start": start,
        "end": end,
        "period_days": days,
        "data_coverage": data_coverage,
        "included_positions": len(valid),
        "total_positions": len(aggregated),
        "summary": {
            "portfolio_return_pct": last_row.get("portfolio_return_pct", 0.0),
            "kospi_return_pct": last_row.get("kospi_return_pct"),
            "sp500_return_pct": last_row.get("sp500_return_pct"),
            "nasdaq_return_pct": last_row.get("nasdaq_return_pct"),
        },
        "series": series_rows,
    }
    _BENCHMARK_RESULT_CACHE[cache_key] = (
        copy.deepcopy(result),
        time.time() + BENCHMARK_RESULT_TTL_SECONDS,
    )
    return result
