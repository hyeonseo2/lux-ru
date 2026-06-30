"""KRX ETF universe and portfolio deposit file helpers.

The app treats pykrx as an optional runtime dependency. If pykrx or KRX
access is unavailable, all helpers return empty/fallback values so existing
seed/yfinance/direct-stock flows keep working.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
import math
import os
import re
import threading
import time
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

LOG = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

KST = ZoneInfo("Asia/Seoul")
KRX_ETF_CACHE_TTL_SECONDS = int(os.getenv("KRX_ETF_CACHE_TTL_SECONDS", str(12 * 3600)))
KRX_UNAVAILABLE_CACHE_TTL_SECONDS = int(os.getenv("KRX_UNAVAILABLE_CACHE_TTL_SECONDS", str(5 * 60)))
KRX_STOCK_SECTOR_CACHE_TTL_SECONDS = int(
    os.getenv("KRX_STOCK_SECTOR_CACHE_TTL_SECONDS", str(12 * 3600))
)
STATIC_KR_ETF_CODES = {"360750", "133690", "069500", "091160", "379800", "273130"}
_HOLDING_MARKET_SUFFIXES = {
    "US", "UQ", "UW", "UN", "UP", "UR", "EQUITY",
    "NASDAQ", "NYSE", "NYSEARCA", "ARCA", "AMEX",
    "KS", "KQ", "KR", "JP", "JT", "HK", "LN", "L",
}
_NUMERIC_HOLDING_SUFFIXES = {
    "HK": ("HK", 4),
    "JP": ("T", 4),
    "JT": ("T", 4),
    "T": ("T", 4),
    "TT": ("TW", 4),
    "TW": ("TW", 4),
    "SS": ("SS", 6),
    "SZ": ("SZ", 6),
    "KS": ("", 6),
    "KQ": ("", 6),
    "KR": ("", 6),
}

_UNIVERSE_LOCK = threading.Lock()
_UNIVERSE_CACHE: tuple[float, list[dict[str, str]]] | None = None
_STOCK_SECTOR_LOCK = threading.Lock()
_STOCK_SECTOR_CACHE: tuple[float, dict[str, str]] | None = None


def krx_credentials_configured() -> bool:
    return bool(os.getenv("KRX_ID", "").strip() and os.getenv("KRX_PW", "").strip())


def _get_pykrx_stock():
    if not krx_credentials_configured():
        LOG.info("KRX_ID/KRX_PW not configured; dynamic KRX lookup disabled")
        return None
    try:
        from pykrx import stock  # type: ignore
    except Exception as exc:
        LOG.info("pykrx unavailable for KRX ETF lookup: %s", exc)
        return None
    return stock


def _normalize_code(raw: Any) -> str:
    text = str(raw or "").strip()
    upper = text.upper()
    if re.fullmatch(r"\d{1,6}", upper):
        return upper.zfill(6)
    prefixed = re.fullmatch(r"A(\d{6})", upper)
    if prefixed:
        return prefixed.group(1)
    domestic_suffix = re.fullmatch(r"(\d{6})[.\-\s]?(KS|KQ|KR)", upper)
    if domestic_suffix:
        return domestic_suffix.group(1)
    cleaned = re.sub(r"[^A-Z0-9_\-.]", "", upper)
    return cleaned[:24]


def _normalize_holding_symbol(raw: Any) -> str:
    """Normalize a PDF holding key without forcing every mixed symbol into 6 digits."""
    text = str(raw or "").strip()
    if not text:
        return ""

    if re.fullmatch(r"\d{1,6}", text):
        return text.zfill(6)

    prefixed_code = re.fullmatch(r"[A-Z](\d{6})", text.upper())
    if prefixed_code:
        return prefixed_code.group(1)

    if not re.search(r"[A-Za-z가-힣]", text):
        digits = re.sub(r"\D", "", text)
        if digits:
            return digits.zfill(6)[-6:]

    upper = text.upper().replace("/", ".").replace("_", " ")
    upper = re.sub(r"[()]", " ", upper)
    upper = re.sub(r"[^A-Z0-9.\-\s]", " ", upper)
    numeric_market = re.fullmatch(r"\s*(\d{1,6})\s*[.\-\s]\s*([A-Z]{1,3})\s*", upper)
    if numeric_market:
        market = _NUMERIC_HOLDING_SUFFIXES.get(numeric_market.group(2))
        if market:
            yf_suffix, width = market
            padded = numeric_market.group(1).zfill(width)
            return padded if not yf_suffix else f"{padded}.{yf_suffix}"

    tokens = [t for t in upper.split() if t]
    if len(tokens) >= 2 and re.fullmatch(r"\d{1,6}", tokens[0]):
        market = _NUMERIC_HOLDING_SUFFIXES.get(tokens[1])
        if market:
            yf_suffix, width = market
            padded = tokens[0].zfill(width)
            return padded if not yf_suffix else f"{padded}.{yf_suffix}"

    while len(tokens) > 1 and tokens[-1] in _HOLDING_MARKET_SUFFIXES:
        tokens.pop()

    if len(tokens) >= 2 and len(tokens[1]) == 1 and re.fullmatch(r"[A-Z]", tokens[1]):
        candidate = f"{tokens[0]}.{tokens[1]}"
    elif tokens:
        candidate = tokens[0]
    else:
        candidate = upper

    cleaned = re.sub(r"[^A-Z0-9.\-]", "", candidate)
    if cleaned:
        return cleaned[:24]
    if re.search(r"[가-힣]", text):
        return text[:24]
    return ""


def _infer_holding_country(raw: Any, symbol: str) -> str:
    text = str(raw or "").upper()
    if symbol == "CASH_KRW" or re.fullmatch(r"\d{6}", symbol):
        return "KR"
    if re.search(r"\bHK\b", text):
        return "HK"
    if re.search(r"\b(TT|TW)\b", text) or re.search(r"\.TW\b", str(symbol).upper()):
        return "TW"
    if re.search(r"\b(JP|JT)\b", text):
        return "JP"
    if re.search(r"\bT\b", text) or re.search(r"\.T\b", str(symbol).upper()):
        return "JP"
    if re.search(r"\b(SS|SZ)\b", text) or re.search(r"\.(SS|SZ)\b", str(symbol).upper()):
        return "CN"
    if re.search(r"\b(LN|L)\b", text):
        return "GB"
    if re.search(r"\b(KS|KQ|KR)\b", text):
        return "KR"
    return "US" if re.search(r"[A-Z]", symbol) else "KR"


def _to_float(raw: Any) -> float:
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        if isinstance(raw, float) and math.isnan(raw):
            return 0.0
        return float(raw)
    text = str(raw).strip()
    if not text or text in {"-", "nan", "None"}:
        return 0.0
    text = text.replace(",", "").replace("%", "").replace("원", "")
    text = re.sub(r"[^0-9.\-]", "", text)
    if not text or text in {"-", "."}:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def latest_business_day() -> str:
    """Return the safest recent KRX business-day string (YYYYMMDD)."""
    d = datetime.now(KST)
    if d.hour < 9:
        d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def _candidate_business_days(start: str | None = None, limit: int = 10) -> list[str]:
    if start:
        try:
            d = datetime.strptime(start, "%Y%m%d").replace(tzinfo=KST)
        except ValueError:
            d = datetime.strptime(latest_business_day(), "%Y%m%d").replace(tzinfo=KST)
    else:
        d = datetime.strptime(latest_business_day(), "%Y%m%d").replace(tzinfo=KST)

    out: list[str] = []
    while len(out) < limit:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def get_krx_etf_universe(force_reload: bool = False) -> list[dict[str, str]]:
    """Return KRX ETF symbols as search-universe items."""
    global _UNIVERSE_CACHE

    now = time.time()
    with _UNIVERSE_LOCK:
        if (
            not force_reload
            and _UNIVERSE_CACHE is not None
            and _UNIVERSE_CACHE[0] > now
        ):
            return list(_UNIVERSE_CACHE[1])

    stock = _get_pykrx_stock()
    if stock is None:
        with _UNIVERSE_LOCK:
            _UNIVERSE_CACHE = (now + KRX_UNAVAILABLE_CACHE_TTL_SECONDS, [])
        return []

    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    used_date = ""
    for date in _candidate_business_days():
        try:
            codes = stock.get_etf_ticker_list(date)
        except Exception as exc:
            LOG.warning("KRX ETF ticker list fetch failed for %s: %s", date, exc)
            codes = []

        if not codes:
            continue

        used_date = date
        for raw_code in codes:
            code = _normalize_code(raw_code)
            if not re.fullmatch(r"\d{6}", code) or code in seen:
                continue
            try:
                name = str(stock.get_etf_ticker_name(code) or "").strip()
            except Exception:
                name = ""
            rows.append({
                "symbol": code,
                "name": name or code,
                "name_ko": name or code,
                "name_en": "",
                "market": "KRX-ETF",
                "country": "KR",
                "symbol_type": "etf",
            })
            seen.add(code)
        break

    if rows:
        LOG.info("Loaded %d KRX ETF symbols from %s", len(rows), used_date)

    with _UNIVERSE_LOCK:
        _UNIVERSE_CACHE = (now + KRX_ETF_CACHE_TTL_SECONDS, rows)
    return list(rows)


def get_krx_etf_name(code: str) -> str:
    """Return a KRX ETF display name, falling back to the code."""
    normalized = _normalize_code(code)
    if not re.fullmatch(r"\d{6}", normalized):
        return str(code or "")

    for item in get_krx_etf_universe():
        if item.get("symbol") == normalized:
            return item.get("name_ko") or item.get("name") or normalized

    stock = _get_pykrx_stock()
    if stock is None:
        return normalized
    try:
        return str(stock.get_etf_ticker_name(normalized) or normalized).strip() or normalized
    except Exception:
        return normalized


def is_krx_etf_symbol(code: str) -> bool:
    normalized = _normalize_code(code)
    if normalized in STATIC_KR_ETF_CODES:
        return True
    if not re.fullmatch(r"\d{6}", normalized):
        return False
    return any(item.get("symbol") == normalized for item in get_krx_etf_universe())


def get_krx_stock_sector_map(force_reload: bool = False) -> dict[str, str]:
    """Return KRX listed-stock code -> official KRX industry name.

    KRX ETF PDF holdings contain constituent codes/weights, but not sectors.
    This table provides the missing official `업종명` that sector_labels.py then
    maps onto the yfinance-compatible canonical sector labels.
    """
    global _STOCK_SECTOR_CACHE

    now = time.time()
    with _STOCK_SECTOR_LOCK:
        if (
            not force_reload
            and _STOCK_SECTOR_CACHE is not None
            and _STOCK_SECTOR_CACHE[0] > now
        ):
            return dict(_STOCK_SECTOR_CACHE[1])

    stock = _get_pykrx_stock()
    if stock is None:
        with _STOCK_SECTOR_LOCK:
            _STOCK_SECTOR_CACHE = (now + KRX_UNAVAILABLE_CACHE_TTL_SECONDS, {})
        return {}

    rows: dict[str, str] = {}
    used_date = ""
    for date in _candidate_business_days():
        current: dict[str, str] = {}
        for market in ("KOSPI", "KOSDAQ"):
            try:
                df = stock.get_market_sector_classifications(date, market)
            except Exception as exc:
                LOG.warning("KRX stock sector fetch failed for %s/%s: %s", date, market, exc)
                continue

            if df is None or len(df) == 0 or "업종명" not in getattr(df, "columns", []):
                continue

            for idx, row in df.iterrows():
                code = _normalize_code(idx)
                if not re.fullmatch(r"\d{6}", code):
                    continue
                industry = str(row.get("업종명") or "").strip()
                if industry:
                    current[code] = industry

        if current:
            rows = current
            used_date = date
            break

    if rows:
        LOG.info("Loaded KRX stock sectors for %d symbols from %s", len(rows), used_date)

    with _STOCK_SECTOR_LOCK:
        _STOCK_SECTOR_CACHE = (now + KRX_STOCK_SECTOR_CACHE_TTL_SECONDS, dict(rows))
    return dict(rows)


def get_krx_stock_sector(code: str) -> str | None:
    """Return official KRX industry name for a listed stock code, if available."""
    normalized = _normalize_code(code)
    if not re.fullmatch(r"\d{6}", normalized):
        return None
    return get_krx_stock_sector_map().get(normalized)


def _pick(row: Any, columns: list[str], names: list[str], default: Any = 0) -> Any:
    for name in names:
        if name in columns:
            return row[name]
    return default


@lru_cache(maxsize=512)
def _get_krx_etf_holdings_for_date(code: str, date: str) -> tuple[dict[str, Any], ...]:
    stock = _get_pykrx_stock()
    if stock is None:
        return tuple()

    try:
        df = stock.get_etf_portfolio_deposit_file(code, date)
    except Exception as exc:
        LOG.warning("KRX ETF PDF fetch failed for %s/%s: %s", code, date, exc)
        return tuple()

    if df is None or len(df) == 0:
        return tuple()

    columns = list(getattr(df, "columns", []))
    rows: list[dict[str, Any]] = []
    total_value = 0.0
    for idx, row in df.iterrows():
        code_raw = _normalize_holding_symbol(idx)
        name = str(_pick(row, columns, ["구성종목명", "종목명", "한글종목명"], code_raw)).strip()
        if not code_raw or code_raw == "000000":
            if "현금" in name or "원화" in name or "cash" in name.lower():
                code_raw = "CASH_KRW"
            else:
                continue

        weight = _to_float(_pick(row, columns, ["비중", "구성비중", "비중(%)"], 0)) / 100.0
        shares = _to_float(_pick(row, columns, ["계약수", "주식수", "수량"], 0))
        value = _to_float(_pick(row, columns, ["금액", "평가금액", "평가액"], 0))
        total_value += value
        rows.append({
            "holding_symbol": code_raw,
            "holding_name": name or code_raw,
            "weight": max(0.0, weight),
            "shares": shares,
            "value": value,
            "currency": "KRW",
            "country": _infer_holding_country(idx, code_raw),
            "sector": "Other",
            "source": "krx_pdf",
        })

    if not rows:
        return tuple()

    weight_sum = sum(float(r["weight"]) for r in rows)
    if weight_sum <= 0 and total_value > 0:
        for row in rows:
            row["weight"] = float(row["value"]) / total_value
    elif weight_sum > 0 and abs(weight_sum - 1.0) > 0.02:
        for row in rows:
            row["weight"] = float(row["weight"]) / weight_sum

    return tuple(rows)


def get_krx_etf_holdings(code: str, date: str | None = None) -> list[dict[str, Any]]:
    """Return KRX ETF PDF holdings in live_data's normalized schema."""
    normalized = _normalize_code(code)
    if not re.fullmatch(r"\d{6}", normalized):
        return []
    if not is_krx_etf_symbol(normalized):
        return []

    candidate_dates = [date] if date else _candidate_business_days()
    for candidate in candidate_dates:
        if not candidate:
            continue
        rows = list(_get_krx_etf_holdings_for_date(normalized, candidate))
        if rows:
            return rows
    return []
