"""Real-market paths for the buy/sell diagnosis mini game."""
from __future__ import annotations

from datetime import date, timedelta
import math
import re
import time
from typing import Any, Optional

from .historical import fetch_prices, map_to_yfinance
from .search_universe import search_instruments

TRADE_GAME_TTL_SECONDS = 6 * 3600
_TRADE_GAME_CACHE: dict[tuple[Any, ...], tuple[dict[str, Any], float]] = {}

ALIASES: dict[str, tuple[str, str, str]] = {
    "삼성전자": ("005930", "삼성전자", "KRW"),
    "삼전": ("005930", "삼성전자", "KRW"),
    "sk하이닉스": ("000660", "SK하이닉스", "KRW"),
    "하이닉스": ("000660", "SK하이닉스", "KRW"),
    "테슬라": ("TSLA", "Tesla", "USD"),
    "엔비디아": ("NVDA", "NVIDIA", "USD"),
    "nvidia": ("NVDA", "NVIDIA", "USD"),
    "비트코인": ("BTC-USD", "Bitcoin", "USD"),
    "bitcoin": ("BTC-USD", "Bitcoin", "USD"),
    "btc": ("BTC-USD", "Bitcoin", "USD"),
    "qqq": ("QQQ", "QQQ", "USD"),
}


def _norm_query(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


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


def _currency_for(symbol: str) -> str:
    return "KRW" if symbol.isdigit() else "USD"


def resolve_trade_instrument(query: str = "", ticker: str = "") -> dict[str, str]:
    raw_ticker = str(ticker or "").strip().upper()
    raw_query = str(query or "").strip()
    normalized_query = _norm_query(raw_query)

    if raw_ticker:
        symbol = raw_ticker
        alias = ALIASES.get(_norm_query(raw_ticker))
        return {
            "symbol": alias[0] if alias else symbol,
            "name": alias[1] if alias else raw_query or symbol,
            "currency": alias[2] if alias else _currency_for(symbol),
        }

    alias = ALIASES.get(normalized_query)
    if alias:
        return {"symbol": alias[0], "name": alias[1], "currency": alias[2]}

    upper = raw_query.upper()
    if upper and re.fullmatch(r"[A-Z0-9.\-]{1,20}", upper):
        if upper in {"BTC", "BTCUSD"}:
            upper = "BTC-USD"
        return {"symbol": upper, "name": raw_query or upper, "currency": _currency_for(upper)}

    if raw_query:
        hits = search_instruments(raw_query, limit=5)
        if hits:
            hit = hits[0]
            symbol = str(hit.get("symbol") or "").upper()
            name = str(hit.get("name_ko") or hit.get("name_en") or hit.get("name") or symbol)
            currency = "KRW" if str(hit.get("country") or "").upper() == "KR" or symbol.isdigit() else "USD"
            return {"symbol": symbol, "name": name, "currency": currency}

    return {"symbol": "005930", "name": "삼성전자", "currency": "KRW"}


def _symbol_candidates(symbol: str) -> list[str]:
    s = str(symbol or "").strip().upper()
    if not s:
        return []
    if s in {"BTC", "BTCUSD"}:
        return ["BTC-USD"]
    if s == "BTC-USD":
        return [s]
    if s.isdigit() and len(s) == 6:
        return [f"{s}.KS", f"{s}.KQ"]
    mapped = map_to_yfinance(s)
    return [mapped] if mapped else [s]


def _returns(values: list[float]) -> list[float]:
    out: list[float] = []
    for prev, cur in zip(values, values[1:]):
        if prev > 0 and cur > 0:
            out.append(cur / prev - 1.0)
    return out


def _annualized_vol(values: list[float]) -> float:
    rs = _returns(values)
    if len(rs) < 2:
        return 0.0
    mean = sum(rs) / len(rs)
    var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
    return math.sqrt(max(var, 0.0)) * math.sqrt(252) * 100


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


def _window_metrics(dates: list[str], values: list[float], start_idx: int, length: int) -> dict[str, Any]:
    window_values = values[start_idx:start_idx + length]
    window_dates = dates[start_idx:start_idx + length]
    total_return = (window_values[-1] / window_values[0] - 1.0) * 100 if window_values[0] > 0 else 0.0
    rs = _returns(window_values)
    abs_move = sum(abs(x) for x in rs) * 100
    return {
        "start_idx": start_idx,
        "start": window_dates[0],
        "end": window_dates[-1],
        "prices": window_values,
        "total_return_pct": total_return,
        "abs_move_pct": abs_move,
        "annual_volatility_pct": _annualized_vol(window_values),
        "max_drawdown_pct": _max_drawdown(window_values),
    }


def _pick_windows(dates: list[str], values: list[float]) -> list[dict[str, Any]]:
    length = min(14, max(6, len(values) // 8))
    windows = [_window_metrics(dates, values, i, length) for i in range(0, len(values) - length + 1)]
    if not windows:
        return []

    selected: list[tuple[str, str, dict[str, Any]]] = []

    def add_unique(key: str, label: str, ordered: list[dict[str, Any]]) -> None:
        for item in ordered:
            if all(abs(item["start_idx"] - prev["start_idx"]) >= length for _, _, prev in selected):
                selected.append((key, label, item))
                return
        selected.append((key, label, ordered[0]))

    volatile = sorted(windows, key=lambda x: x["abs_move_pct"] - abs(x["total_return_pct"]) * 0.35, reverse=True)
    down = sorted(windows, key=lambda x: x["total_return_pct"])
    up = sorted(windows, key=lambda x: x["total_return_pct"], reverse=True)

    add_unique("news_sensitivity", "실제 변동성 구간", volatile)
    add_unique("downtrend_response", "실제 하락 구간", down)
    add_unique("uptrend_response", "실제 상승 구간", up)
    return [{"key": key, "label": label, **item} for key, label, item in selected[:3]]


def _event_text(name: str, item: dict[str, Any], idx: int) -> str:
    ret = item["total_return_pct"]
    abs_move = item["abs_move_pct"]
    if idx == 0:
        return f"{name} {item['start']}~{item['end']} 구간 재생. 변동폭 합계 {abs_move:.1f}%."
    if ret < -3:
        return f"하락 압력이 컸던 구간입니다 ({ret:.1f}%)."
    if ret > 3:
        return f"반등 흐름이 강했던 구간입니다 ({ret:+.1f}%)."
    return f"방향보다 흔들림이 컸던 구간입니다 ({ret:+.1f}%)."


def build_trade_game_data(query: str = "", ticker: str = "", period_days: int = 1095) -> dict[str, Any]:
    instrument = resolve_trade_instrument(query, ticker)
    symbol = instrument["symbol"]
    candidates = _symbol_candidates(symbol)
    days = max(180, min(int(period_days or 1095), 1825))
    cache_key = (symbol, tuple(candidates), days)
    now = time.time()
    cached = _TRADE_GAME_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return dict(cached[0])

    end_date = date.today() + timedelta(days=1)
    start_date = end_date - timedelta(days=days)
    start = start_date.isoformat()
    end = end_date.isoformat()
    prices = fetch_prices(candidates, start, end)

    chosen = None
    series = None
    for candidate in candidates:
        data = prices.get(candidate)
        if data and len(data) >= 40:
            chosen = candidate
            series = data
            break

    if not chosen or not series:
        result = {
            "success": False,
            "message": "실제 가격 데이터가 부족해 손절·존버 게임을 시작할 수 없습니다.",
            "symbol": symbol,
            "name": instrument["name"],
            "yf_symbol": chosen,
            "data_source": "yfinance_daily_close",
        }
        _TRADE_GAME_CACHE[cache_key] = (dict(result), now + 60)
        return result

    dates = sorted(series.keys())
    values = [float(series[d]) for d in dates if _safe_float(series[d]) > 0]
    dates = [d for d in dates if _safe_float(series[d]) > 0]
    windows = _pick_windows(dates, values)
    scenarios: list[dict[str, Any]] = []
    for idx, item in enumerate(windows):
        prices_out = [round(float(v), 4) for v in item["prices"]]
        scenarios.append({
            "key": item["key"],
            "label": item["label"],
            "start": item["start"],
            "end": item["end"],
            "prices": prices_out,
            "base_price": prices_out[0],
            "total_return_pct": item["total_return_pct"],
            "abs_move_pct": item["abs_move_pct"],
            "annual_volatility_pct": item["annual_volatility_pct"],
            "max_drawdown_pct": item["max_drawdown_pct"],
            "events": [
                {"offset": 0.18, "category": "real_market", "headline": _event_text(instrument["name"], item, 0)},
                {"offset": 0.50, "category": "real_market", "headline": _event_text(instrument["name"], item, 1)},
                {"offset": 0.78, "category": "real_market", "headline": f"실제 종가 흐름 기준 최종 변동성 {item['annual_volatility_pct']:.1f}%."},
            ],
        })

    result = {
        "success": True,
        "symbol": symbol,
        "name": instrument["name"],
        "currency": instrument["currency"],
        "yf_symbol": chosen,
        "period_days": days,
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "data_source": "yfinance_daily_close",
    }
    _TRADE_GAME_CACHE[cache_key] = (dict(result), now + TRADE_GAME_TTL_SECONDS)
    return result
