"""Screener engine with SWR (Stale-While-Revalidate) caching and robust filtering."""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Optional

from .seed_data import ALL_INSTRUMENTS
from .sector_labels import normalize_sector_for_symbol
from .historical import map_to_yfinance
from .search_universe import list_search_universe

LOG = logging.getLogger(__name__)

# Lock for thread-safety
_CACHE_LOCK = threading.Lock()

# Cache store: symbol -> {market_cap, pe_ratio, price_change_1m, updated_at}
_SCREENER_CACHE: dict[str, dict[str, Any]] = {}
CACHE_TTL_SECONDS = 24 * 3600  # 1 day TTL
_RESULT_CACHE: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}
_BASE_ROWS_CACHE: tuple[float, list[dict[str, Any]]] | None = None
RESULT_CACHE_TTL_SECONDS = 30
BASE_ROWS_CACHE_TTL_SECONDS = int(os.getenv("SCREENER_BASE_ROWS_CACHE_TTL_SECONDS", "60"))
DEFAULT_RESULT_LIMIT = 80
MAX_RESULT_LIMIT = 200

# Pre-seeded realistic data (fallback & initial seed for SWR)
# format: symbol -> (market_cap_original_currency, pe_ratio, price_change_1m)
_SEED_METRICS: dict[str, tuple[float, Optional[float], float]] = {
    # US Stocks (Market Cap in Billions USD)
    "AAPL": (2900.0, 28.5, 0.042),
    "MSFT": (3100.0, 35.2, -0.015),
    "NVDA": (2200.0, 72.4, 0.185),
    "AMZN": (1850.0, 42.1, 0.028),
    "GOOGL": (2100.0, 25.8, 0.054),
    "META": (1200.0, 24.3, 0.012),
    "TSLA": (550.0, 58.0, -0.089),
    "BRK.B": (880.0, 18.5, 0.005),
    "AVGO": (630.0, 48.2, 0.092),
    "JPM": (570.0, 12.4, 0.018),
    "LLY": (710.0, 115.0, 0.065),
    "V": (520.0, 32.1, 0.009),
    "UNH": (480.0, 21.3, -0.025),
    "MA": (430.0, 35.6, 0.011),
    "XOM": (470.0, 13.2, 0.038),
    "HD": (380.0, 23.4, -0.012),
    "PG": (390.0, 26.8, 0.004),
    "COST": (340.0, 48.9, 0.051),
    "JNJ": (360.0, 15.8, -0.008),
    "ABBV": (310.0, 18.2, 0.014),
    "CRM": (280.0, 38.5, -0.042),
    "NFLX": (270.0, 42.6, 0.078),
    "AMD": (260.0, 68.0, -0.035),
    "ADBE": (220.0, 31.4, -0.022),
    "WMT": (480.0, 28.2, 0.019),
    "PEP": (230.0, 24.5, -0.005),
    "KO": (260.0, 25.2, 0.008),
    "MRK": (300.0, 16.9, 0.021),
    "CSCO": (190.0, 15.4, 0.002),
    "ACN": (210.0, 27.5, -0.018),
    "TMO": (215.0, 32.8, 0.009),
    "ORCL": (330.0, 34.2, 0.115),
    "BAC": (305.0, 11.5, 0.025),
    "CVX": (295.0, 12.8, 0.041),
    "INTC": (135.0, 31.2, -0.142),
    "QCOM": (205.0, 22.4, 0.083),
    "VZ": (168.0, 9.2, 0.005),
    "T": (125.0, 8.8, 0.012),
    "PFE": (155.0, 12.5, -0.035),
    "CMCSA": (160.0, 10.4, -0.008),

    # KR Stocks (Market Cap in Trillions KRW)
    "005930": (450.0, 16.5, -0.012),   # 삼성전자
    "000660": (120.0, 24.8, 0.125),   # SK하이닉스
    "373220": (85.0, 82.5, -0.054),   # LG에너지솔루션
    "005380": (52.0, 6.2, 0.045),     # 현대자동차
    "035420": (28.0, 19.4, -0.028),   # 네이버
    "000270": (44.0, 5.8, 0.032),     # 기아
    "068270": (39.0, 45.2, 0.018),    # 셀트리온
    "035720": (18.0, 38.4, -0.048),   # 카카오
    "105560": (31.0, 6.8, 0.085),     # KB금융
    "055550": (26.0, 5.9, 0.062),     # 신한지주
    "006400": (28.0, 21.4, -0.038),   # 삼성SDI
    "003670": (25.0, 12.2, -0.015),   # 포스코홀딩스
    "051910": (24.0, 15.8, -0.022),   # LG화학
    "028260": (22.0, 10.5, 0.008),    # 삼성물산
    "012330": (21.0, 6.4, 0.012),     # 현대모비스

    # ETFs (Market Cap/AUM in Billions USD for US, Trillions KRW for KR)
    "360750": (3.5, 26.5, 0.024),     # TIGER 미국S&P500
    "133690": (4.2, 34.0, 0.052),     # TIGER 미국나스닥100
    "069500": (5.8, 18.2, -0.008),    # KODEX 200
    "379800": (2.1, 26.5, 0.024),     # KODEX 미국S&P500TR
    "273130": (1.8, None, 0.003),     # KODEX 종합채권
    "SPY": (510.0, 26.5, 0.024),      # SPY
    "QQQ": (250.0, 34.0, 0.052),      # QQQ
    "VOO": (420.0, 26.5, 0.024),      # VOO
    "SCHD": (55.0, 15.8, 0.012),      # SCHD
}


def _seed_lookup() -> dict[str, Any]:
    return {inst.symbol: inst for inst in ALL_INSTRUMENTS.values() if getattr(inst, "symbol", None)}


def _fallback_metrics_for_symbol(symbol: str, country: str) -> dict[str, Any]:
    seed = _SEED_METRICS.get(symbol)
    if seed:
        market_cap, pe_ratio, price_change_1m = seed
    else:
        # Unknown expanded-universe symbols still need deterministic sortable values.
        market_cap = 0.0
        pe_ratio = None
        price_change_1m = 0.0
    return {
        "market_cap": market_cap,
        "pe_ratio": pe_ratio,
        "price_change_1m": price_change_1m,
        "updated_at": time.time(),
        "source": "seed" if seed else "universe",
    }


def _update_symbol_metrics_yfinance(symbol: str) -> Optional[dict[str, Any]]:
    """Fetch real-time metrics for a symbol from yfinance."""
    try:
        import yfinance as yf
    except ImportError:
        LOG.warning("yfinance not installed, using seed metrics for %s", symbol)
        return None

    try:
        yf_symbol = map_to_yfinance(symbol) or symbol
        ticker = yf.Ticker(yf_symbol)
        info = getattr(ticker, "info", None) or {}

        # 1. Market Cap
        # yfinance returns in raw currency (e.g. USD or KRW)
        raw_mcap = info.get("marketCap")
        if not raw_mcap:
            fast = getattr(ticker, "fast_info", None)
            if fast and hasattr(fast, "get"):
                raw_mcap = fast.get("marketCap") or getattr(fast, "marketCap", None)

        mcap = None
        if raw_mcap:
            # We scale: Billions for USD, Trillions for KRW
            if symbol.isdigit() or symbol.endswith(".KS") or symbol.endswith(".KQ") or "360750" in symbol or "133690" in symbol or "069500" in symbol or "379800" in symbol or "273130" in symbol:
                # KRW: scale to Trillion KRW (1e12)
                mcap = float(raw_mcap) / 1e12
            else:
                # USD: scale to Billion USD (1e9)
                mcap = float(raw_mcap) / 1e9

        # 2. P/E Ratio
        pe = info.get("trailingPE") or info.get("forwardPE")
        if pe:
            pe = float(pe)

        # 3. 1M Return
        # Fetch 1 month historical data
        hist = ticker.history(period="35d")
        price_change_1m = 0.0
        if hist is not None and len(hist) > 5 and "Close" in hist:
            # Get closest close price to 30 days ago
            close_prices = hist["Close"].dropna()
            if len(close_prices) >= 2:
                latest = float(close_prices.iloc[-1])
                prev = float(close_prices.iloc[0])
                if prev > 0:
                    price_change_1m = (latest - prev) / prev

        metrics = {}
        if mcap is not None:
            metrics["market_cap"] = round(mcap, 2)
        if pe is not None:
            metrics["pe_ratio"] = round(pe, 2)
        else:
            metrics["pe_ratio"] = None
        metrics["price_change_1m"] = round(price_change_1m, 4)

        return metrics
    except Exception as exc:
        LOG.warning("Failed to fetch yfinance screener metrics for %s: %s", symbol, exc)
        return None


def _background_update_cache(symbol: str) -> None:
    """Target function to run yfinance query in a background thread."""
    metrics = _update_symbol_metrics_yfinance(symbol)
    if metrics:
        with _CACHE_LOCK:
            _SCREENER_CACHE[symbol] = {
                **metrics,
                "updated_at": time.time()
            }
            LOG.info("Screener cache updated in background for symbol %s", symbol)


def get_screener_instrument_metrics(symbol: str) -> dict[str, Any]:
    """Retrieve metrics for a symbol, triggering a background update if stale (SWR)."""
    now = time.time()
    cached = None

    with _CACHE_LOCK:
        cached = _SCREENER_CACHE.get(symbol)

    # If not in cache, initialize with seed metrics
    if not cached:
        country = "KR" if symbol.isdigit() else "US"
        cached = _fallback_metrics_for_symbol(symbol, country)
        with _CACHE_LOCK:
            _SCREENER_CACHE[symbol] = cached

    # Stale-While-Revalidate: Return cached immediately, trigger background thread if expired
    if symbol in _SEED_METRICS and now - cached["updated_at"] > CACHE_TTL_SECONDS:
        # Mark as updated so we don't spawn multiple threads for the same symbol simultaneously
        with _CACHE_LOCK:
            _SCREENER_CACHE[symbol]["updated_at"] = now
        
        # Run background update thread
        t = threading.Thread(target=_background_update_cache, args=(symbol,), daemon=True)
        t.start()

    return cached


def _format_screener_row(item: dict[str, Any], seed_by_symbol: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip().upper()
    if not symbol or symbol.startswith("CASH_") or symbol.startswith("BOND_"):
        return None

    metrics = get_screener_instrument_metrics(symbol)
    seed_inst = seed_by_symbol.get(symbol)
    name_ko = str(item.get("name_ko") or "")
    name_en = str(item.get("name_en") or "")
    name = str(item.get("name") or "")
    country = str(item.get("country") or getattr(seed_inst, "country", "") or ("KR" if symbol.isdigit() else "US"))
    market = str(item.get("market") or getattr(seed_inst, "market", "") or "")
    symbol_type = str(
        item.get("symbol_type")
        or (
            seed_inst.instrument_type.value
            if seed_inst and getattr(seed_inst, "instrument_type", None)
            else "stock"
        )
    ).lower()
    raw_sector = getattr(seed_inst, "sector", "") if seed_inst else ""
    norm_sector = normalize_sector_for_symbol(symbol, raw_sector)
    currency = getattr(seed_inst, "currency", "") if seed_inst else ("KRW" if country == "KR" else "USD")
    mcap = metrics.get("market_cap", 0.0)
    pe = metrics.get("pe_ratio")
    price_change = metrics.get("price_change_1m", 0.0)
    mcap_unit = "조 원" if currency == "KRW" else "억 달러"
    display_name_ko = name_ko or (getattr(seed_inst, "name_ko", "") if seed_inst else "")
    display_name_en = name_en or (getattr(seed_inst, "name_en", "") if seed_inst else "")
    display_name = display_name_ko or display_name_en or name or symbol

    return {
        "instrument_id": str(getattr(seed_inst, "id", "")) if seed_inst else "",
        "symbol": symbol,
        "name_ko": display_name_ko,
        "name_en": display_name_en,
        "name": display_name,
        "market": market,
        "sector": norm_sector,
        "country": country,
        "currency": currency,
        "instrument_type": symbol_type.upper(),
        "market_cap": mcap,
        "market_cap_str": f"{mcap:,.1f}{mcap_unit}",
        "pe_ratio": pe,
        "pe_ratio_str": f"{pe:.1f}" if pe is not None else "N/A",
        "price_change_1m": price_change,
        "price_change_1m_str": f"{price_change * 100:+.2f}%",
        "_search_text": f"{symbol} {display_name_ko} {display_name_en} {name}".lower(),
    }


def _get_screener_base_rows() -> list[dict[str, Any]]:
    """Return enriched screener rows. Filtering/sorting can reuse this cache."""
    global _BASE_ROWS_CACHE

    now = time.time()
    with _CACHE_LOCK:
        if _BASE_ROWS_CACHE and _BASE_ROWS_CACHE[0] > now:
            return [dict(row) for row in _BASE_ROWS_CACHE[1]]

    seed_by_symbol = _seed_lookup()
    rows: list[dict[str, Any]] = []
    for item in list_search_universe():
        row = _format_screener_row(item, seed_by_symbol)
        if row:
            rows.append(row)

    with _CACHE_LOCK:
        _BASE_ROWS_CACHE = (time.time() + BASE_ROWS_CACHE_TTL_SECONDS, [dict(row) for row in rows])
    return rows


def screen_instruments(
    sectors: Optional[list[str]] = None,
    countries: Optional[list[str]] = None,
    instrument_types: Optional[list[str]] = None,
    pe_min: Optional[float] = None,
    pe_max: Optional[float] = None,
    mcap_min: Optional[float] = None,  # scale matching currency
    mcap_max: Optional[float] = None,
    sort_by: str = "market_cap",
    sort_desc: bool = True,
    query: str = "",
    limit: int = DEFAULT_RESULT_LIMIT,
) -> list[dict[str, Any]]:
    """Screen and rank universe of instruments based on filters and real-time metrics."""
    normalized_limit = max(1, min(int(limit or DEFAULT_RESULT_LIMIT), MAX_RESULT_LIMIT))
    cache_key = (
        tuple(sorted(sectors or [])),
        tuple(sorted(countries or [])),
        tuple(sorted(t.lower() for t in (instrument_types or []))),
        pe_min,
        pe_max,
        mcap_min,
        mcap_max,
        sort_by,
        bool(sort_desc),
        query.strip().lower(),
        normalized_limit,
    )
    now = time.time()
    with _CACHE_LOCK:
        cached_result = _RESULT_CACHE.get(cache_key)
        if cached_result and cached_result[0] > now:
            return [dict(item) for item in cached_result[1]]

    results = []
    q_clean = query.strip().lower()
    type_filters = [t.lower() for t in instrument_types] if instrument_types else []

    for item in _get_screener_base_rows():
        if q_clean and q_clean not in str(item.get("_search_text") or ""):
            continue

        # 2. Country filter
        if countries and item.get("country") not in countries:
            continue

        # 3. Instrument type filter (stock / etf)
        if type_filters and str(item.get("instrument_type") or "").lower() not in type_filters:
            continue

        # 4. Sector filter
        if sectors and item.get("sector") not in sectors:
            continue

        # 5. P/E Ratio filter
        pe = item.get("pe_ratio")
        if pe_min is not None and (pe is None or pe < pe_min):
            continue
        if pe_max is not None and (pe is None or pe > pe_max):
            continue

        # 6. Market Cap filter
        mcap = item.get("market_cap", 0.0)
        if mcap_min is not None and mcap < mcap_min:
            continue
        if mcap_max is not None and mcap > mcap_max:
            continue

        results.append({k: v for k, v in item.items() if not k.startswith("_")})

    # Sort results
    def sort_key(item):
        val = item.get(sort_by)
        if val is None:
            # Place None at the end
            return -99999999 if sort_desc else 99999999
        return val

    results.sort(key=sort_key, reverse=sort_desc)
    limited = results[:normalized_limit]
    with _CACHE_LOCK:
        _RESULT_CACHE[cache_key] = (
            time.time() + RESULT_CACHE_TTL_SECONDS,
            [dict(item) for item in limited],
        )
    return limited
