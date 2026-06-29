"""Dynamic ETF allocation suggestions using market data."""
from __future__ import annotations

from datetime import date, timedelta
import math
import time
from typing import Any

from .historical import fetch_prices, map_to_yfinance
from .income_fees import compute_income_fees

REBALANCE_TTL_SECONDS = 6 * 3600
_REBALANCE_CACHE: dict[tuple[Any, ...], tuple[dict[str, Any], float]] = {}

ETF_UNIVERSE: list[dict[str, Any]] = [
    {"ticker": "379800", "name": "KODEX 미국S&P500TR", "role": "global", "sector": "글로벌", "color": "#7dd3fc"},
    {"ticker": "360750", "name": "TIGER 미국S&P500", "role": "global", "sector": "글로벌", "color": "#7dd3fc"},
    {"ticker": "VOO", "name": "Vanguard S&P 500 ETF", "role": "global", "sector": "글로벌", "color": "#7dd3fc"},
    {"ticker": "069500", "name": "KODEX 200", "role": "korea", "sector": "국내대형", "color": "#2563eb"},
    {"ticker": "273130", "name": "KODEX 종합채권", "role": "bond", "sector": "채권", "color": "#64748b"},
    {"ticker": "SCHD", "name": "Schwab US Dividend Equity ETF", "role": "dividend", "sector": "배당", "color": "#10b981"},
    {"ticker": "161510", "name": "PLUS 고배당주", "role": "dividend", "sector": "배당", "color": "#10b981"},
    {"ticker": "QQQ", "name": "Invesco QQQ Trust", "role": "growth", "sector": "성장", "color": "#a78bfa"},
    {"ticker": "133690", "name": "TIGER 미국나스닥100", "role": "growth", "sector": "성장", "color": "#a78bfa"},
]

TECH_SECTORS = {"반도체", "IT", "커뮤니케이션", "2차전지", "성장"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(out) or math.isinf(out):
        return default
    return out


def _returns(values: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev > 0 and cur > 0:
            out.append(cur / prev - 1.0)
    return out


def _annualized_vol(values: list[float]) -> float | None:
    rs = _returns(values)
    if len(rs) < 2:
        return None
    mean = sum(rs) / len(rs)
    var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
    return math.sqrt(max(0.0, var)) * math.sqrt(252) * 100


def _max_drawdown(values: list[float]) -> float:
    if not values:
        return 0.0
    peak = values[0]
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst * 100


def _price_metrics(tickers: list[str], period_days: int) -> dict[str, dict[str, Any]]:
    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=period_days)
    start = start_date.isoformat()
    end = end_date.isoformat()
    symbols = sorted({map_to_yfinance(ticker) or ticker for ticker in tickers})
    prices = fetch_prices(symbols, start, end)
    out: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        yf_symbol = map_to_yfinance(ticker) or ticker
        series = prices.get(yf_symbol)
        if not series or len(series) < 30:
            continue
        dates = sorted(series.keys())
        values = [float(series[d]) for d in dates if _safe_float(series[d]) > 0]
        if len(values) < 30 or values[0] <= 0:
            continue
        out[ticker] = {
            "yf_symbol": yf_symbol,
            "return_pct": (values[-1] / values[0] - 1.0) * 100,
            "annual_volatility_pct": _annualized_vol(values),
            "max_drawdown_pct": _max_drawdown(values),
            "start": dates[0],
            "end": dates[-1],
            "sample_count": len(values),
        }
    return out


def _fee_dividend_metrics(universe: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    data = compute_income_fees([
        {"ticker": item["ticker"], "name": item["name"], "amount": 1_000_000, "type_hint": "etf"}
        for item in universe
    ])
    return {str(item.get("ticker")).upper(): item for item in data.get("items", [])}


def _candidate_rows(period_days: int = 365) -> list[dict[str, Any]]:
    tickers = [item["ticker"] for item in ETF_UNIVERSE]
    price_by_ticker = _price_metrics(tickers, period_days)
    fee_by_ticker = _fee_dividend_metrics(ETF_UNIVERSE)
    rows: list[dict[str, Any]] = []
    for item in ETF_UNIVERSE:
        ticker = item["ticker"]
        price = price_by_ticker.get(ticker)
        if not price or price.get("annual_volatility_pct") is None:
            continue
        fee = fee_by_ticker.get(ticker, {})
        rows.append({
            **item,
            **price,
            "expense_ratio": fee.get("expense_ratio"),
            "expense_estimated": bool(fee.get("expense_estimated")),
            "expense_source": fee.get("expense_source"),
            "dividend_yield": fee.get("dividend_yield"),
            "dividend_source": fee.get("dividend_source"),
            "data_source": "yfinance_daily_close",
        })
    return rows


def _score_candidate(row: dict[str, Any], role: str, top_sector: str, defensive: bool) -> float:
    ret = _safe_float(row.get("return_pct"))
    vol = _safe_float(row.get("annual_volatility_pct"), 99.0)
    fee = _safe_float(row.get("expense_ratio"), 0.35)
    div = _safe_float(row.get("dividend_yield"))
    mdd = abs(_safe_float(row.get("max_drawdown_pct")))
    score = 0.0
    if role == "bond":
        score = 80 - vol * 2.4 - fee * 8 + max(ret, -5) * 0.6 - mdd * 0.6
    elif role == "dividend":
        score = 55 + div * 5 + ret * 0.4 - vol * 0.9 - fee * 7
    elif role == "growth":
        score = 50 + ret * 0.8 - vol * 0.65 - fee * 5
        if top_sector in TECH_SECTORS:
            score -= 18
    elif role == "korea":
        score = 52 + ret * 0.45 - vol * 0.75 - fee * 6
        if top_sector in {"반도체", "2차전지"}:
            score -= 8
    else:
        score = 58 + ret * 0.55 - vol * 0.65 - fee * 6 - mdd * 0.2
    if defensive and role in {"bond", "dividend"}:
        score += 8
    return score


def _target_role_weights(
    analysis: dict[str, Any],
    profile: dict[str, Any],
    aggressive: bool,
    defensive: bool,
) -> dict[str, float]:
    top_weight = _safe_float(analysis.get("top_weight"))
    hhi = _safe_float(analysis.get("hhi"))
    vol = _safe_float(analysis.get("risk_volatility"), 18.0)
    top_ticker = str(analysis.get("top_ticker") or "")
    top_sector = str(analysis.get("top_sector") or "")
    domestic_top = top_ticker.isdigit()
    tech_top = top_sector in TECH_SECTORS

    defense_need = 0.0
    defense_need += _clamp((vol - 18) / 35, 0, 1) * 0.32
    defense_need += _clamp((top_weight - 35) / 45, 0, 1) * 0.28
    defense_need += _clamp((hhi - 1200) / 3200, 0, 1) * 0.22
    defense_need += 0.18 if defensive else 0
    defense_need = _clamp(defense_need, 0, 1)

    bond = _clamp((0.10 if aggressive else 0.22) + defense_need * 0.38, 0.08, 0.68)
    dividend = _clamp((0.08 if aggressive else 0.16) + defense_need * 0.12, 0.05, 0.30)
    growth = 0.18 if aggressive else 0.04
    if tech_top:
        growth *= 0.35
    global_equity = 0.42 if domestic_top else 0.32
    korea = 0.10 if domestic_top else 0.18

    weights = {
        "bond": bond,
        "global": global_equity,
        "dividend": dividend,
        "korea": korea,
        "growth": growth,
    }
    total = sum(v for v in weights.values() if v > 0)
    return {k: v / total for k, v in weights.items() if v > 0.015}


def _reason(row: dict[str, Any], role: str) -> str:
    role_text = {
        "bond": "변동성 완충",
        "global": "글로벌 분산",
        "dividend": "배당·방어 보강",
        "korea": "국내 대표지수 분산",
        "growth": "성장 노출 보완",
    }.get(role, "분산 보강")
    fee = row.get("expense_ratio")
    fee_text = f", 보수 {_safe_float(fee):.2f}%" if fee is not None else ""
    if row.get("expense_estimated"):
        fee_text += " 추정"
    div = row.get("dividend_yield")
    div_text = f", 배당 {_safe_float(div):.1f}%" if div is not None else ""
    return (
        f"{role_text} · 최근 1년 수익률 {_safe_float(row.get('return_pct')):+.1f}%, "
        f"변동성 {_safe_float(row.get('annual_volatility_pct')):.1f}%{fee_text}{div_text}"
    )


def compute_dynamic_rebalance_plan(
    sell_amount: float,
    analysis: dict[str, Any] | None = None,
    profile: dict[str, Any] | None = None,
    aggressive: bool = False,
    defensive: bool = False,
    period_days: int = 365,
) -> dict[str, Any]:
    amount = max(0.0, _safe_float(sell_amount))
    analysis = analysis or {}
    profile = profile or {}
    days = max(180, min(int(period_days or 365), 1095))
    cache_key = (
        round(amount, 2),
        round(_safe_float(analysis.get("top_weight")), 2),
        round(_safe_float(analysis.get("hhi")), 2),
        str(analysis.get("top_ticker") or ""),
        str(analysis.get("top_sector") or ""),
        str(profile.get("risk") or ""),
        str(profile.get("bal") or ""),
        bool(aggressive),
        bool(defensive),
        days,
    )
    now = time.time()
    cached = _REBALANCE_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return dict(cached[0])

    if amount <= 0:
        return {"success": True, "buy_actions": [], "candidates": [], "message": "sell amount is zero"}

    candidates = _candidate_rows(days)
    top_sector = str(analysis.get("top_sector") or "")
    target_weights = _target_role_weights(analysis, profile, aggressive, defensive)

    selected: list[dict[str, Any]] = []
    used: set[str] = set()
    for role, weight in sorted(target_weights.items(), key=lambda item: item[1], reverse=True):
        role_candidates = [row for row in candidates if row["role"] == role and row["ticker"] not in used]
        if not role_candidates:
            continue
        best = max(role_candidates, key=lambda row: _score_candidate(row, role, top_sector, defensive))
        used.add(best["ticker"])
        selected.append({**best, "target_weight": weight})

    if not selected:
        result = {
            "success": True,
            "buy_actions": [],
            "candidates": [],
            "message": "실제 시장 데이터가 충분한 ETF 후보를 찾지 못했습니다.",
            "data_source": "yfinance_daily_close",
        }
        _REBALANCE_CACHE[cache_key] = (dict(result), now + 60)
        return result

    total_weight = sum(item["target_weight"] for item in selected)
    buy_actions: list[dict[str, Any]] = []
    allocated = 0
    for idx, item in enumerate(selected):
        if idx == len(selected) - 1:
            action_amount = round(amount - allocated)
        else:
            action_amount = round(amount * item["target_weight"] / total_weight)
            allocated += action_amount
        if action_amount <= 0:
            continue
        ratio = action_amount / amount if amount else 0
        buy_actions.append({
            "ticker": item["ticker"],
            "name": item["name"],
            "reason": _reason(item, item["role"]),
            "ratio": ratio,
            "amount": action_amount,
            "sector": item["sector"],
            "color": item["color"],
            "role": item["role"],
            "metrics": {
                "return_pct": item.get("return_pct"),
                "annual_volatility_pct": item.get("annual_volatility_pct"),
                "max_drawdown_pct": item.get("max_drawdown_pct"),
                "expense_ratio": item.get("expense_ratio"),
                "expense_estimated": item.get("expense_estimated"),
                "dividend_yield": item.get("dividend_yield"),
                "yf_symbol": item.get("yf_symbol"),
            },
        })

    result = {
        "success": True,
        "buy_actions": buy_actions,
        "candidates": candidates,
        "target_role_weights": target_weights,
        "data_source": "yfinance_daily_close + yfinance_fundamentals",
        "period_days": days,
    }
    _REBALANCE_CACHE[cache_key] = (dict(result), now + REBALANCE_TTL_SECONDS)
    return result
