"""Portfolio dividend and fee lookups.

The endpoint uses live yfinance data first:
- dividends: recent dividend/distribution history and current price
- fees: yfinance expense-ratio fields for ETFs/funds

When public data is unavailable, values are explicitly marked as estimated or
missing so the UI does not present fallback numbers as market data.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime, timezone
import math
import os
import re
import threading
import time
from typing import Any

from .historical import map_to_yfinance
from .search_universe import load_expanded_universe

INCOME_FEES_TTL_SECONDS = 6 * 3600
INCOME_FEES_LOOKUP_TIMEOUT_SECONDS = float(os.getenv("INCOME_FEES_LOOKUP_TIMEOUT_SECONDS", "4.0"))
INCOME_FEES_MAX_WORKERS = max(2, int(os.getenv("INCOME_FEES_MAX_WORKERS", "8")))

_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_UNIVERSE_BY_SYMBOL: dict[str, dict[str, Any]] | None = None

FEE_FALLBACKS = {
    "069500": 0.15,
    "122630": 0.64,
    "091160": 0.45,
    "360750": 0.07,
    "133690": 0.07,
    "305720": 0.45,
    "161510": 0.23,
    "152380": 0.05,
    "273130": 0.15,
    "379800": 0.05,
    "QQQ": 0.20,
    "SCHD": 0.06,
    "VOO": 0.03,
    "SOXL": 0.90,
}


def _normalize_symbol(raw: Any) -> str:
    symbol = str(raw or "").strip().upper()
    if re.fullmatch(r"\d{1,6}", symbol):
        return symbol.zfill(6)
    domestic = re.fullmatch(r"(\d{6})[.\-\s]?(KS|KQ|KR)", symbol)
    if domestic:
        return domestic.group(1)
    return symbol[:24]


def _to_float(raw: Any, default: float = 0.0) -> float:
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if math.isnan(value) or math.isinf(value):
        return default
    return value


def _ratio_to_percent(raw: Any) -> float | None:
    value = _to_float(raw, default=float("nan"))
    if math.isnan(value) or value < 0:
        return None
    return value * 100 if value <= 1 else value


def _expense_to_percent(raw: Any) -> float | None:
    value = _to_float(raw, default=float("nan"))
    if math.isnan(value) or value < 0:
        return None
    # Yahoo expense fields are inconsistent:
    # - annualReportExpenseRatio can be a decimal fraction (0.002 -> 0.20%)
    # - netExpenseRatio is often basis points (18 -> 0.18%)
    # - some fields are already percent values (0.18 -> 0.18%)
    if value > 5:
        return value / 100
    if value < 0.01:
        return value * 100
    return value


def _universe_item(symbol: str) -> dict[str, Any] | None:
    global _UNIVERSE_BY_SYMBOL
    if _UNIVERSE_BY_SYMBOL is None:
        _UNIVERSE_BY_SYMBOL = {
            str(item.get("symbol", "")).upper(): item
            for item in load_expanded_universe()
            if item.get("symbol")
        }
    return _UNIVERSE_BY_SYMBOL.get(symbol)


def _infer_type(symbol: str, name: str, type_hint: str = "", info: dict[str, Any] | None = None) -> str:
    raw = (type_hint or "").strip().lower()
    if raw in {"stock", "etf", "fund"}:
        return raw
    quote_type = str((info or {}).get("quoteType") or "").strip().lower()
    if quote_type in {"etf"}:
        return "etf"
    if quote_type in {"mutualfund", "fund"}:
        return "fund"
    item = _universe_item(symbol)
    symbol_type = str((item or {}).get("symbol_type") or "").lower()
    if "etf" in symbol_type:
        return "etf"
    if "fund" in symbol_type:
        return "fund"
    lower_name = name.lower()
    if any(token in lower_name for token in ("etf", "kodex", "tiger", "arirang", "ace ", "sol ", "레버리지", "인덱스")):
        return "etf"
    if "fund" in lower_name or "펀드" in lower_name:
        return "fund"
    return "stock"


def _fast_info_get(fast: Any, *keys: str) -> Any:
    if not fast:
        return None
    for key in keys:
        try:
            if hasattr(fast, "get"):
                value = fast.get(key)
            else:
                value = getattr(fast, key, None)
        except Exception:
            value = None
        if value not in (None, ""):
            return value
    return None


def _extract_price(ticker: Any, info: dict[str, Any]) -> float | None:
    fast = getattr(ticker, "fast_info", None)
    value = _fast_info_get(fast, "lastPrice", "last_price", "regularMarketPrice", "previousClose")
    if value in (None, ""):
        value = (
            info.get("regularMarketPrice")
            or info.get("currentPrice")
            or info.get("previousClose")
            or info.get("navPrice")
        )
    price = _to_float(value, default=float("nan"))
    return None if math.isnan(price) or price <= 0 else price


def _extract_expense_ratio(info: dict[str, Any]) -> tuple[float | None, str]:
    for key in (
        "annualReportExpenseRatio",
        "netExpenseRatio",
        "expenseRatio",
        "totalExpenseRatio",
        "managementFee",
    ):
        pct = _expense_to_percent(info.get(key))
        if pct is not None:
            return pct, f"yfinance:{key}"
    return None, "none"


def _extract_dividend_from_series(ticker: Any, price: float | None) -> tuple[float | None, list[int], str]:
    try:
        dividends = ticker.dividends
    except Exception:
        dividends = None
    if dividends is None:
        return None, [], "none"
    try:
        dividends = dividends.dropna()
    except Exception:
        return None, [], "none"
    if len(dividends) == 0:
        return 0.0, [], "yfinance_dividends"
    try:
        import pandas as pd

        idx = dividends.index
        if getattr(idx, "tz", None) is not None:
            now = pd.Timestamp.now(tz=idx.tz)
        else:
            now = pd.Timestamp(datetime.now(timezone.utc).replace(tzinfo=None))
        last_12 = dividends[idx >= now - pd.Timedelta(days=370)]
        last_24 = dividends[idx >= now - pd.Timedelta(days=740)]
        annual_per_share = _to_float(last_12.sum(), default=0.0)
        months = sorted({int(ts.month) for ts, value in last_24.items() if _to_float(value) > 0})
    except Exception:
        annual_per_share = _to_float(dividends.tail(4).sum(), default=0.0)
        months = []
    if price and price > 0:
        return annual_per_share / price * 100, months, "yfinance_dividends"
    return None, months, "yfinance_dividends"


def _extract_dividend_yield(ticker: Any, info: dict[str, Any], price: float | None) -> tuple[float | None, list[int], str]:
    yield_pct, months, source = _extract_dividend_from_series(ticker, price)
    if yield_pct is not None:
        return yield_pct, months, source
    for key in ("trailingAnnualDividendYield", "dividendYield", "yield"):
        pct = _ratio_to_percent(info.get(key))
        if pct is not None:
            return pct, months, f"yfinance:{key}"
    rate = _to_float(info.get("trailingAnnualDividendRate") or info.get("dividendRate"), default=float("nan"))
    if not math.isnan(rate) and price and price > 0:
        return rate / price * 100, months, "yfinance:dividendRate"
    return None, months, "none"


def _load_symbol_income_fee(symbol: str, name: str, type_hint: str) -> dict[str, Any]:
    yf_symbol = map_to_yfinance(symbol) or symbol
    cache_key = yf_symbol.upper()
    now = time.time()
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
        if cached and cached[0] > now:
            return dict(cached[1])

    try:
        import yfinance as yf

        ticker = yf.Ticker(yf_symbol)
        info = getattr(ticker, "info", None) or {}
    except Exception:
        info = {}
        ticker = None

    instrument_type = _infer_type(symbol, name, type_hint, info)
    price = _extract_price(ticker, info) if ticker is not None else None

    if instrument_type == "stock":
        expense_ratio = 0.0
        expense_source = "direct_stock"
        expense_estimated = False
    else:
        expense_ratio, expense_source = _extract_expense_ratio(info)
        expense_estimated = False
        if expense_ratio is None and symbol in FEE_FALLBACKS:
            expense_ratio = FEE_FALLBACKS[symbol]
            expense_source = "fallback_estimate"
            expense_estimated = True

    if ticker is not None:
        dividend_yield, dividend_months, dividend_source = _extract_dividend_yield(ticker, info, price)
    else:
        dividend_yield, dividend_months, dividend_source = None, [], "none"

    payload = {
        "symbol": symbol,
        "yf_symbol": yf_symbol,
        "instrument_type": instrument_type,
        "price": price,
        "expense_ratio": expense_ratio,
        "expense_source": expense_source,
        "expense_estimated": expense_estimated,
        "dividend_yield": dividend_yield,
        "dividend_source": dividend_source,
        "dividend_estimated": False,
        "dividend_months": dividend_months,
        "data_source": "yfinance" if info or ticker is not None else "none",
    }
    with _CACHE_LOCK:
        _CACHE[cache_key] = (now + INCOME_FEES_TTL_SECONDS, dict(payload))
    return payload


def _fallback_symbol_income_fee(symbol: str, name: str, type_hint: str, source: str = "timeout_fallback") -> dict[str, Any]:
    yf_symbol = map_to_yfinance(symbol) or symbol
    instrument_type = _infer_type(symbol, name, type_hint, {})
    if instrument_type == "stock":
        expense_ratio = 0.0
        expense_source = "direct_stock"
        expense_estimated = False
    elif symbol in FEE_FALLBACKS:
        expense_ratio = FEE_FALLBACKS[symbol]
        expense_source = "fallback_estimate"
        expense_estimated = True
    else:
        expense_ratio = None
        expense_source = "none"
        expense_estimated = False
    return {
        "symbol": symbol,
        "yf_symbol": yf_symbol,
        "instrument_type": instrument_type,
        "price": None,
        "expense_ratio": expense_ratio,
        "expense_source": expense_source,
        "expense_estimated": expense_estimated,
        "dividend_yield": None,
        "dividend_source": source,
        "dividend_estimated": False,
        "dividend_months": [],
        "data_source": source,
    }


def _load_income_fee_batch(valid: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for pos in valid:
        unique.setdefault(pos["ticker"], pos)
    if not unique:
        return {}

    executor = ThreadPoolExecutor(max_workers=min(INCOME_FEES_MAX_WORKERS, len(unique)))
    future_to_symbol = {
        executor.submit(_load_symbol_income_fee, pos["ticker"], pos["name"], pos["type_hint"]): symbol
        for symbol, pos in unique.items()
    }
    done, pending = wait(future_to_symbol, timeout=INCOME_FEES_LOOKUP_TIMEOUT_SECONDS)
    loaded: dict[str, dict[str, Any]] = {}
    for future in done:
        symbol = future_to_symbol[future]
        pos = unique[symbol]
        try:
            loaded[symbol] = future.result()
        except Exception:
            loaded[symbol] = _fallback_symbol_income_fee(pos["ticker"], pos["name"], pos["type_hint"], "lookup_error")
    for future in pending:
        symbol = future_to_symbol[future]
        pos = unique[symbol]
        loaded[symbol] = _fallback_symbol_income_fee(pos["ticker"], pos["name"], pos["type_hint"], "timeout_fallback")
    executor.shutdown(wait=False, cancel_futures=True)
    return loaded


def compute_income_fees(positions: list[dict[str, Any]]) -> dict[str, Any]:
    valid: list[dict[str, Any]] = []
    for raw in positions or []:
        symbol = _normalize_symbol(raw.get("ticker") or raw.get("symbol"))
        amount = _to_float(raw.get("amount") or raw.get("market_value"))
        if not symbol or amount <= 0:
            continue
        item = _universe_item(symbol) or {}
        valid.append({
            "ticker": symbol,
            "name": str(raw.get("name") or raw.get("instrument_name") or item.get("name") or symbol),
            "amount": amount,
            "type_hint": str(raw.get("type_hint") or raw.get("symbol_type") or item.get("symbol_type") or ""),
        })

    meta_by_ticker = _load_income_fee_batch(valid)
    items: list[dict[str, Any]] = []
    for pos in valid:
        meta = meta_by_ticker.get(pos["ticker"]) or _fallback_symbol_income_fee(pos["ticker"], pos["name"], pos["type_hint"])
        expense_ratio = meta["expense_ratio"]
        dividend_yield = meta["dividend_yield"]
        annual_fee = pos["amount"] * (expense_ratio or 0.0) / 100
        annual_dividend = pos["amount"] * (dividend_yield or 0.0) / 100
        items.append({
            **pos,
            "instrument_type": meta["instrument_type"],
            "yf_symbol": meta["yf_symbol"],
            "data_source": meta["data_source"],
            "expense_ratio": expense_ratio,
            "expense_source": meta["expense_source"],
            "expense_estimated": bool(meta["expense_estimated"]),
            "annual_fee": annual_fee,
            "dividend_yield": dividend_yield,
            "dividend_source": meta["dividend_source"],
            "dividend_estimated": bool(meta["dividend_estimated"]),
            "annual_dividend": annual_dividend,
            "dividend_months": meta["dividend_months"],
        })

    total = sum(item["amount"] for item in items)
    annual_fee = sum(item["annual_fee"] for item in items)
    annual_dividend = sum(item["annual_dividend"] for item in items)
    coverage = {
        "fee_actual": sum(1 for item in items if item["expense_ratio"] is not None and not item["expense_estimated"]),
        "fee_estimated": sum(1 for item in items if item["expense_estimated"]),
        "fee_missing": sum(1 for item in items if item["expense_ratio"] is None),
        "dividend_actual": sum(1 for item in items if item["dividend_yield"] is not None and not item["dividend_estimated"]),
        "dividend_estimated": sum(1 for item in items if item["dividend_estimated"]),
        "dividend_missing": sum(1 for item in items if item["dividend_yield"] is None),
    }

    return {
        "success": True,
        "items": items,
        "summary": {
            "total_amount": total,
            "annual_fee": annual_fee,
            "weighted_expense_ratio": annual_fee / total * 100 if total else 0.0,
            "annual_dividend": annual_dividend,
            "portfolio_dividend_yield": annual_dividend / total * 100 if total else 0.0,
            "coverage": coverage,
        },
    }
