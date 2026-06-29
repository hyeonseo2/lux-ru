"""Market-data based portfolio risk metrics.

The diagnosis UI uses this module for volatility and beta. It deliberately
does not use static per-symbol risk tables; all return metrics come from
yfinance daily close history through ``historical.fetch_prices``.
"""
from __future__ import annotations

from datetime import date, timedelta
import math
import time
from typing import Any, Optional

from .historical import BENCHMARK_SYMBOLS, BOND_PROXY, fetch_prices, map_to_yfinance

DEFENSIVE_SECTORS = {"채권", "현금", "Cash", "Bond"}
RISK_RESULT_TTL_SECONDS = 6 * 3600
_RISK_RESULT_CACHE: dict[tuple[Any, ...], tuple[dict[str, Any], float]] = {}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    m = _mean(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(max(0.0, var))


def _covariance(xs: list[float], ys: list[float]) -> Optional[float]:
    n = min(len(xs), len(ys))
    if n < 2:
        return None
    x = xs[:n]
    y = ys[:n]
    mx = _mean(x)
    my = _mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / (n - 1)


def _value_on_or_before(series: dict[str, float], target_date: str) -> Optional[float]:
    if target_date in series:
        return series[target_date]
    prior = [d for d in series.keys() if d <= target_date]
    if not prior:
        return None
    return series[max(prior)]


def _return_series_from_values(values: list[float]) -> list[float]:
    returns: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev > 0 and cur > 0:
            returns.append(cur / prev - 1.0)
    return returns


def _annualized_volatility(returns: list[float]) -> Optional[float]:
    std = _sample_std(returns)
    if std is None:
        return None
    return std * math.sqrt(252) * 100


def _max_drawdown(values: list[float]) -> Optional[float]:
    if len(values) < 2:
        return None
    peak = values[0]
    worst = 0.0
    for v in values:
        if v > peak:
            peak = v
        if peak > 0:
            worst = min(worst, v / peak - 1.0)
    return worst * 100


def _candidate_symbols(ticker: str) -> list[str]:
    t = str(ticker or "").strip().upper()
    if not t:
        return []
    if t.startswith("BOND_") or t.startswith("CASH_"):
        return [BOND_PROXY]
    if t.isdigit() and len(t) == 6:
        # KOSPI first, KOSDAQ second. yfinance returns data for only the valid one.
        return [f"{t}.KS", f"{t}.KQ"]
    mapped = map_to_yfinance(t)
    return [mapped] if mapped else []


def _benchmark_type(ticker: str, sector: str | None = None) -> str:
    t = str(ticker or "").strip().upper()
    s = str(sector or "").strip()
    if t.startswith("BOND_") or t.startswith("CASH_") or s in DEFENSIVE_SECTORS:
        return "bond"
    if t.isdigit():
        return "kospi"
    return "sp500"


def _benchmark_label(mix: dict[str, float]) -> str:
    active = [(k, v) for k, v in mix.items() if v > 0.01]
    if not active:
        return "시장"
    names = {"kospi": "KOSPI", "sp500": "S&P 500", "bond": "채권"}
    if len(active) == 1:
        return names.get(active[0][0], active[0][0])
    return " / ".join(f"{names.get(k, k)} {v * 100:.0f}%" for k, v in active)


def _risk_style(score: float) -> dict[str, str]:
    if score >= 68:
        return {
            "label": "공격형",
            "chip": "warn",
            "tone": "실제 가격 변동성과 집중 노출이 큰 편입니다.",
        }
    if score >= 42:
        return {
            "label": "중립형",
            "chip": "blue",
            "tone": "실제 변동성과 방어 노출이 혼재합니다.",
        }
    return {
        "label": "수비형",
        "chip": "good",
        "tone": "실제 가격 변동성이 상대적으로 낮거나 방어 노출이 높습니다.",
    }


def _cache_key(
    exposures: list[dict[str, Any]],
    gross_value: float,
    hhi: float,
    leverage_ratio: float,
    period_days: int,
) -> tuple[Any, ...]:
    normalized = tuple(
        (str(e.get("ticker", "")).upper(), round(float(e.get("amount", 0) or 0), 2))
        for e in sorted(exposures, key=lambda item: str(item.get("ticker", "")))
    )
    return (
        period_days,
        round(gross_value, 2),
        round(hhi, 2),
        round(leverage_ratio, 4),
        normalized,
    )


def compute_market_risk(
    exposures: list[dict[str, Any]],
    total_value: float | None = None,
    gross_value: float | None = None,
    hhi: float | None = None,
    leverage_ratio: float | None = None,
    period_days: int = 365,
) -> dict[str, Any]:
    """Compute annualized volatility and beta from real daily close history."""
    days = max(90, min(int(period_days or 365), 1825))
    cleaned: list[dict[str, Any]] = []
    for raw in exposures or []:
        ticker = str(raw.get("ticker", "")).strip().upper()
        try:
            amount = float(raw.get("amount", 0) or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if ticker and amount > 0:
            cleaned.append({
                "ticker": ticker,
                "amount": amount,
                "name": str(raw.get("name") or ticker),
                "sector": raw.get("sector"),
                "levered": bool(raw.get("levered")),
            })

    if not cleaned:
        return {"status": "error", "message": "no valid exposures"}

    gross = float(gross_value or sum(e["amount"] for e in cleaned) or 0)
    total = float(total_value or gross or 0)
    if gross <= 0:
        return {"status": "error", "message": "invalid gross value"}

    hhi_value = float(hhi if hhi is not None else sum((e["amount"] / gross * 100) ** 2 for e in cleaned))
    leverage = float(leverage_ratio or (gross / total if total > 0 else 1.0))

    key = _cache_key(cleaned, gross, hhi_value, leverage, days)
    now = time.time()
    cached = _RISK_RESULT_CACHE.get(key)
    if cached and cached[1] > now:
        return dict(cached[0])

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days)
    start = start_date.isoformat()
    end = end_date.isoformat()

    symbol_candidates: dict[str, list[str]] = {e["ticker"]: _candidate_symbols(e["ticker"]) for e in cleaned}
    bench_symbols = {
        "kospi": BENCHMARK_SYMBOLS["kospi"],
        "sp500": BENCHMARK_SYMBOLS["sp500"],
        "nasdaq": BENCHMARK_SYMBOLS["nasdaq"],
        "bond": BOND_PROXY,
    }
    fetch_symbols = sorted({
        sym
        for candidates in symbol_candidates.values()
        for sym in candidates
    } | set(bench_symbols.values()))
    prices = fetch_prices(fetch_symbols, start, end)

    nodes: list[dict[str, Any]] = []
    unmatched: list[str] = []
    matched_amount = 0.0
    benchmark_amounts = {"kospi": 0.0, "sp500": 0.0, "bond": 0.0}

    for e in cleaned:
        chosen = None
        series = None
        for sym in symbol_candidates.get(e["ticker"], []):
            candidate = prices.get(sym)
            if candidate and len(candidate) >= 20:
                chosen = sym
                series = candidate
                break
        if not chosen or not series:
            unmatched.append(e["ticker"])
            continue
        dates = sorted(series.keys())
        first = series[dates[0]]
        if first <= 0:
            unmatched.append(e["ticker"])
            continue
        matched_amount += e["amount"]
        bench_type = _benchmark_type(e["ticker"], e.get("sector"))
        benchmark_amounts[bench_type] = benchmark_amounts.get(bench_type, 0.0) + e["amount"]
        nodes.append({
            **e,
            "yf_symbol": chosen,
            "series": series,
            "dates": dates,
            "first": first,
        })

    coverage = matched_amount / gross if gross > 0 else 0.0
    if not nodes or coverage < 0.2:
        result = {
            "status": "insufficient_data",
            "message": "실제 가격 데이터가 부족해 리스크를 계산하지 못했습니다.",
            "period_days": days,
            "start": start,
            "end": end,
            "data_coverage": coverage,
            "matched_exposure_count": len(nodes),
            "total_exposure_count": len(cleaned),
            "unmatched_tickers": unmatched[:20],
        }
        _RISK_RESULT_CACHE[key] = (dict(result), now + RISK_RESULT_TTL_SECONDS)
        return result

    all_dates = sorted({d for n in nodes for d in n["dates"]})
    portfolio_values: list[float] = []
    portfolio_dates: list[str] = []
    for d in all_dates:
        value = 0.0
        for n in nodes:
            cur = _value_on_or_before(n["series"], d)
            if cur is None:
                cur = n["first"]
            value += n["amount"] * (cur / n["first"] if n["first"] > 0 else 1.0)
        if value > 0:
            portfolio_dates.append(d)
            portfolio_values.append(value)

    portfolio_returns = _return_series_from_values(portfolio_values)
    annual_vol = _annualized_volatility(portfolio_returns)
    max_dd = _max_drawdown(portfolio_values)

    benchmark_total = sum(benchmark_amounts.values()) or matched_amount
    benchmark_mix = {k: (v / benchmark_total if benchmark_total else 0.0) for k, v in benchmark_amounts.items()}
    if not any(benchmark_mix.values()):
        benchmark_mix["sp500"] = 1.0

    benchmark_values: list[float] = []
    active_benchmarks = {
        key: prices.get(sym)
        for key, sym in bench_symbols.items()
        if benchmark_mix.get(key, 0.0) > 0 and prices.get(sym)
    }
    for d in portfolio_dates:
        value = 0.0
        used_weight = 0.0
        for key_name, series in active_benchmarks.items():
            dates = sorted(series.keys())
            if not dates or series[dates[0]] <= 0:
                continue
            cur = _value_on_or_before(series, d)
            if cur is None:
                cur = series[dates[0]]
            weight = benchmark_mix.get(key_name, 0.0)
            value += weight * (cur / series[dates[0]])
            used_weight += weight
        if used_weight > 0:
            benchmark_values.append(value / used_weight)
        else:
            benchmark_values.append(1.0)
    benchmark_returns = _return_series_from_values(benchmark_values)

    paired_len = min(len(portfolio_returns), len(benchmark_returns))
    beta = None
    if paired_len >= 20:
        cov = _covariance(portfolio_returns[-paired_len:], benchmark_returns[-paired_len:])
        var = _covariance(benchmark_returns[-paired_len:], benchmark_returns[-paired_len:])
        if cov is not None and var and var > 0:
            beta = cov / var

    benchmark_vols: dict[str, dict[str, Any]] = {}
    benchmark_names = {
        "kospi": "KOSPI",
        "sp500": "S&P 500",
        "nasdaq": "NASDAQ",
        "bond": "채권형 ETF",
    }
    for key_name, sym in bench_symbols.items():
        series = prices.get(sym)
        if not series or len(series) < 20:
            continue
        values = [series[d] for d in sorted(series.keys()) if series[d] > 0]
        vol = _annualized_volatility(_return_series_from_values(values))
        if vol is not None:
            benchmark_vols[key_name] = {
                "name": benchmark_names[key_name],
                "symbol": sym,
                "annual_volatility_pct": vol,
            }

    if annual_vol is None:
        result = {
            "status": "insufficient_data",
            "message": "수익률 표본이 부족해 변동성을 계산하지 못했습니다.",
            "period_days": days,
            "start": start,
            "end": end,
            "data_coverage": coverage,
            "matched_exposure_count": len(nodes),
            "total_exposure_count": len(cleaned),
            "unmatched_tickers": unmatched[:20],
        }
        _RISK_RESULT_CACHE[key] = (dict(result), now + RISK_RESULT_TTL_SECONDS)
        return result

    top3_pct = sum(e["amount"] for e in sorted(cleaned, key=lambda item: item["amount"], reverse=True)[:3]) / gross * 100
    defensive_pct = sum(e["amount"] for e in cleaned if str(e.get("sector") or "") in DEFENSIVE_SECTORS) / gross * 100
    levered_pct = sum(
        e["amount"]
        for e in cleaned
        if bool(e.get("levered")) or (leverage > 1.05 and str(e.get("sector") or "") not in DEFENSIVE_SECTORS)
    ) / gross * 100

    beta_value = float(beta if beta is not None else 1.0)
    score = _clamp(
        (annual_vol - 6) * 1.8
        + max(0.0, beta_value - 1.0) * 18
        + max(0.0, hhi_value - 900) / 30
        + max(0.0, leverage - 1.0) * 35
        + top3_pct * 0.16
        - defensive_pct * 0.15,
        0,
        100,
    )

    result = {
        "status": "success",
        "period_days": days,
        "start": start,
        "end": end,
        "annual_volatility_pct": annual_vol,
        "beta": beta,
        "max_drawdown_pct": max_dd,
        "risk_score": score,
        "style": _risk_style(score),
        "benchmark_label": _benchmark_label(benchmark_mix),
        "benchmark_mix": benchmark_mix,
        "benchmarks": benchmark_vols,
        "data_coverage": coverage,
        "matched_exposure_count": len(nodes),
        "total_exposure_count": len(cleaned),
        "unmatched_tickers": unmatched[:20],
        "top3_pct": top3_pct,
        "defensive_pct": defensive_pct,
        "levered_pct": levered_pct,
        "hhi": hhi_value,
        "leverage_ratio": leverage,
        "data_source": "yfinance_daily_close",
    }
    _RISK_RESULT_CACHE[key] = (dict(result), now + RISK_RESULT_TTL_SECONDS)
    return result
