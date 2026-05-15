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

import logging
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


# ── Symbol mapping ────────────────────────────────────────────────

BOND_PROXY = "273130.KS"  # KODEX 종합채권(AA-이상)액티브


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
