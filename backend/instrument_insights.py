"""Instrument-level event and news insights for workflow detail panel."""
from __future__ import annotations

import copy
from datetime import date, datetime, time as dtime, timedelta, timezone
import io
import json
import logging
import os
import re
import threading
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
import zipfile

from .historical import map_to_yfinance

LOG = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
YAHOO_ROOT = "https://finance.yahoo.com"
OPENDART_ROOT = "https://opendart.fss.or.kr/api"
DART_VIEWER_ROOT = "https://dart.fss.or.kr/dsaf001/main.do"
US_SEC_FORMS = {"20-F", "10-K", "10-Q", "8-K", "6-K"}
DART_CORP_MAP_TTL_SECONDS = 24 * 3600
INSIGHTS_SOURCE_CACHE_TTL_SECONDS = int(os.getenv("INSTRUMENT_INSIGHTS_SOURCE_CACHE_TTL_SECONDS", "180"))
INSIGHTS_ERROR_CACHE_TTL_SECONDS = int(os.getenv("INSTRUMENT_INSIGHTS_ERROR_CACHE_TTL_SECONDS", "60"))
INSIGHTS_SOURCE_CACHE_MAX_ENTRIES = int(os.getenv("INSTRUMENT_INSIGHTS_SOURCE_CACHE_MAX_ENTRIES", "128"))

_DART_CORP_MAP_CACHE: dict[str, tuple[dict[str, str], float]] = {}
_DART_CORP_MAP_LOCK = threading.Lock()
_INSIGHTS_SOURCE_CACHE: dict[tuple[Any, ...], tuple[float, Any]] = {}
_INSIGHTS_SOURCE_CACHE_LOCK = threading.Lock()


def _source_cache_get(key: tuple[Any, ...]) -> Any | None:
    now = time.time()
    with _INSIGHTS_SOURCE_CACHE_LOCK:
        cached = _INSIGHTS_SOURCE_CACHE.get(key)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at <= now:
            _INSIGHTS_SOURCE_CACHE.pop(key, None)
            return None
        return copy.deepcopy(value)


def _source_cache_set(key: tuple[Any, ...], value: Any, ttl_seconds: int) -> None:
    ttl = max(1, int(ttl_seconds or 1))
    with _INSIGHTS_SOURCE_CACHE_LOCK:
        now = time.time()
        if len(_INSIGHTS_SOURCE_CACHE) >= max(1, INSIGHTS_SOURCE_CACHE_MAX_ENTRIES):
            expired = [k for k, (expires_at, _) in _INSIGHTS_SOURCE_CACHE.items() if expires_at <= now]
            for expired_key in expired:
                _INSIGHTS_SOURCE_CACHE.pop(expired_key, None)
        if len(_INSIGHTS_SOURCE_CACHE) >= max(1, INSIGHTS_SOURCE_CACHE_MAX_ENTRIES):
            oldest_key = min(_INSIGHTS_SOURCE_CACHE.items(), key=lambda item: item[1][0])[0]
            _INSIGHTS_SOURCE_CACHE.pop(oldest_key, None)
        _INSIGHTS_SOURCE_CACHE[key] = (time.time() + ttl, copy.deepcopy(value))


def _source_cache_ttl(errors: list[str] | None = None, notes: list[str] | None = None) -> int:
    if errors:
        return INSIGHTS_ERROR_CACHE_TTL_SECONDS
    if any(("미설정" in note or "실패" in note) for note in (notes or [])):
        return INSIGHTS_ERROR_CACHE_TTL_SECONDS
    return INSIGHTS_SOURCE_CACHE_TTL_SECONDS


def _window_cache_key_parts(since_kst: datetime, now_kst: datetime) -> tuple[str, str]:
    # Day-bucketed windows keep "recent N days" calls reusable without hiding intraday updates past TTL.
    return (_to_dart_date(since_kst), _to_dart_date(now_kst))


def _normalize_ticker(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    text = re.sub(r"[^A-Z0-9.\-]", "", text)
    return text[:20]


def _is_us_symbol(normalized_ticker: str, yf_symbol: str) -> bool:
    """Best-effort US ticker detection for UI category gating.

    Notes:
      - Korean/local exchange suffixes (.KS/.KQ) are non-US.
      - Known foreign exchange suffixes are non-US.
      - US class-share tickers like BRK.B should remain US.
    """
    t = (normalized_ticker or "").upper().strip()
    y = (yf_symbol or "").upper().strip()
    if not t or not y:
        return False
    if t.isdigit():
        return False
    if y.endswith(".KS") or y.endswith(".KQ"):
        return False

    # Exchange suffix symbols like 7203.T / 0700.HK are treated as non-US.
    # Do NOT blanket-reject every dotted ticker: BRK.B/BF.B are US class shares.
    match = re.search(r"\.([A-Z]{1,5})$", y)
    if match:
        suffix = match.group(1)
        non_us_suffixes = {
            "T", "HK", "SS", "SZ", "L", "F", "PA", "MI", "AS", "BR", "DE", "SW", "ST", "HE", "CO",
            "OL", "VI", "WA", "PR", "MC", "LS", "IR", "TLV", "IS", "AX", "NZ", "TO", "V", "SA", "MX",
            "TW", "SI", "BK", "KL", "JK", "VN", "NS", "BO", "DU", "BE", "HA", "HM", "MU", "SG",
        }
        if suffix in non_us_suffixes:
            return False
    return True


def _http_get_bytes(url: str, params: dict[str, Any], timeout: float = 10.0) -> bytes:
    query = urlencode({k: v for k, v in params.items() if v is not None and v != ""})
    full_url = f"{url}?{query}" if query else url
    req = Request(full_url, headers={"User-Agent": "LUX-RU/1.0"})
    with urlopen(req, timeout=timeout) as resp:  # nosec B310
        return resp.read()


def _http_get_json(url: str, params: dict[str, Any], timeout: float = 10.0) -> dict[str, Any]:
    raw = _http_get_bytes(url, params, timeout=timeout)
    text = raw.decode("utf-8", errors="replace")
    return json.loads(text) if text else {}


def _extract_xml_from_zip_or_raw(raw: bytes) -> bytes:
    if raw[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(raw)) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".xml")]
            if not names:
                raise ValueError("corpCode zip has no xml file")
            return zf.read(names[0])
    return raw


def _get_dart_api_key() -> str:
    key = str(os.getenv("DART_API_KEY") or os.getenv("crtfc_key") or "").strip()
    if key:
        return key
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        return ""
    return str(os.getenv("DART_API_KEY") or os.getenv("crtfc_key") or "").strip()


def _load_dart_corp_map(api_key: str) -> dict[str, str]:
    now = time.time()
    with _DART_CORP_MAP_LOCK:
        cached = _DART_CORP_MAP_CACHE.get(api_key)
        if cached and cached[1] > now:
            return cached[0]

    raw = _http_get_bytes(
        f"{OPENDART_ROOT}/corpCode.xml",
        {"crtfc_key": api_key},
        timeout=12.0,
    )
    xml_bytes = _extract_xml_from_zip_or_raw(raw)
    root = ET.fromstring(xml_bytes)

    mapping: dict[str, str] = {}
    for item in root.findall(".//list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if len(stock_code) == 6 and corp_code:
            mapping[stock_code] = corp_code

    with _DART_CORP_MAP_LOCK:
        _DART_CORP_MAP_CACHE[api_key] = (mapping, now + DART_CORP_MAP_TTL_SECONDS)
    return mapping


def _to_dart_date(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def _classify_dart_report(report_nm: str) -> str | None:
    normalized = re.sub(r"\s+", "", report_nm or "")
    if not normalized:
        return None
    if any(k in normalized for k in ("분기보고서", "반기보고서", "사업보고서")):
        return "filing"
    if "잠정" in normalized and "실적" in normalized:
        return "earnings"
    if "결산실적공시예고" in normalized:
        return "earnings"
    if "실적" in normalized and "공정공시" in normalized:
        return "earnings"
    return None


def _fetch_dart_disclosures(
    ticker: str,
    since_kst: datetime,
    now_kst: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    filings_kr: list[dict[str, Any]] = []
    earnings_kr: list[dict[str, Any]] = []
    notes: list[str] = []
    errors: list[str] = []

    api_key = _get_dart_api_key()
    if not api_key:
        notes.append("DART_API_KEY 미설정으로 한국 공시는 조회하지 못했습니다.")
        return filings_kr, earnings_kr, notes, errors

    try:
        corp_map = _load_dart_corp_map(api_key)
    except Exception as exc:
        LOG.warning("dart corpCode fetch failed: %s", exc)
        errors.append(f"DART 기업코드 조회 실패: {exc}")
        return filings_kr, earnings_kr, notes, errors

    corp_code = corp_map.get(ticker)
    if not corp_code:
        notes.append(f"DART 고유번호 매핑을 찾지 못했습니다: {ticker}")
        return filings_kr, earnings_kr, notes, errors

    try:
        payload = _http_get_json(
            f"{OPENDART_ROOT}/list.json",
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": _to_dart_date(since_kst),
                "end_de": _to_dart_date(now_kst),
                "last_reprt_at": "Y",
                "sort": "date",
                "sort_mth": "desc",
                "page_no": 1,
                "page_count": 100,
            },
            timeout=12.0,
        )
    except Exception as exc:
        LOG.warning("dart list fetch failed for %s/%s: %s", ticker, corp_code, exc)
        errors.append(f"DART 공시 조회 실패: {exc}")
        return filings_kr, earnings_kr, notes, errors

    status = str(payload.get("status") or "")
    message = str(payload.get("message") or "")
    if status == "013":
        notes.append("최근 1개월 DART 공시가 없습니다.")
        return filings_kr, earnings_kr, notes, errors
    if status and status != "000":
        errors.append(f"DART 오류({status}): {message or '알 수 없는 오류'}")
        return filings_kr, earnings_kr, notes, errors

    rows = payload.get("list")
    if not isinstance(rows, list):
        return filings_kr, earnings_kr, notes, errors

    seen: set[tuple[str, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        report_nm = str(row.get("report_nm") or "").strip()
        rcept_no = str(row.get("rcept_no") or "").strip()
        rcept_dt_raw = row.get("rcept_dt")
        dt_kst = _to_kst(_parse_datetime(rcept_dt_raw))
        if not report_nm or not rcept_no or not dt_kst:
            continue
        if dt_kst < since_kst or dt_kst > now_kst:
            continue

        kind = _classify_dart_report(report_nm)
        if not kind:
            continue
        dedupe_key = (kind, rcept_no)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        item = {
            "kind": kind,
            "title": report_nm,
            "occurred_at_kst": dt_kst.isoformat(),
            "source": "DART",
            "url": f"{DART_VIEWER_ROOT}?rcpNo={rcept_no}",
            "corp_name": str(row.get("corp_name") or "").strip(),
        }
        if kind == "filing":
            filings_kr.append(item)
        elif kind == "earnings":
            earnings_kr.append(item)

    return filings_kr, earnings_kr, notes, errors


def _to_kst(dt: datetime | date | None) -> datetime | None:
    if dt is None:
        return None
    if isinstance(dt, date) and not isinstance(dt, datetime):
        dt = datetime.combine(dt, dtime.min)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(KST)


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, dtime.min)
    if isinstance(value, (int, float)):
        ts = float(value)
        if ts > 1_000_000_000_000:
            ts /= 1000.0
        try:
            return datetime.fromtimestamp(ts, tz=timezone.utc)
        except Exception:
            return None

    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{10,13}", text):
        return _parse_datetime(int(text))
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if re.fullmatch(r".*[+-]\d{4}$", text):
        text = text[:-5] + text[-5:-2] + ":" + text[-2:]

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    formats = (
        "%Y-%m-%d",
        "%Y%m%d",
        "%Y/%m/%d",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d %H:%M:%S",
        "%B %d, %Y",
        "%b %d, %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _dig(obj: Any, *path: str) -> Any:
    cur = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _pick_text(obj: dict[str, Any], paths: list[tuple[str, ...]]) -> str:
    for path in paths:
        value = _dig(obj, *path)
        if value is None:
            continue
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                return text
    return ""


def _normalize_url(url: str) -> str:
    text = str(url or "").strip()
    if not text:
        return ""
    if text.startswith("//"):
        return "https:" + text
    if text.startswith("/"):
        return YAHOO_ROOT + text
    return text


def _classify_transcript(title: str, summary: str) -> str | None:
    text = f"{title} {summary}".lower()
    if "transcript" not in text and "스크립트" not in text:
        return None

    earnings_terms = [
        "earnings call",
        "earning call",
        "quarterly call",
        "q1",
        "q2",
        "q3",
        "q4",
        "eps",
    ]
    corporate_terms = [
        "investor day",
        "capital markets day",
        "conference",
        "shareholder meeting",
        "annual meeting",
        "presentation",
        "fireside chat",
        "webcast",
        "event",
    ]

    if any(term in text for term in earnings_terms):
        return "earnings"
    if any(term in text for term in corporate_terms):
        return "corporate"
    return None


def _sort_desc(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda x: x.get("occurred_at_kst", ""), reverse=True)


def _iter_filings(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    if isinstance(raw, dict):
        if isinstance(raw.get("filings"), list):
            return [x for x in raw["filings"] if isinstance(x, dict)]
        return [x for x in raw.values() if isinstance(x, dict)]
    return []


def _fetch_sec_filings_cached(
    ticker_client: Any,
    yf_symbol: str,
    since_kst: datetime,
    now_kst: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    key = ("sec_filings", yf_symbol, *_window_cache_key_parts(since_kst, now_kst))
    cached = _source_cache_get(key)
    if cached is not None:
        return cached

    filings_us: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        sec_filings = _iter_filings(ticker_client.get_sec_filings())
        for filing in sec_filings:
            form = str(filing.get("type") or filing.get("form") or "").upper().strip()
            if form not in US_SEC_FORMS:
                continue
            dt_kst = _to_kst(_parse_datetime(filing.get("date") or filing.get("epochDate")))
            if not dt_kst or dt_kst < since_kst or dt_kst > now_kst:
                continue
            title = str(filing.get("title") or f"{form} filing").strip()
            url = _normalize_url(
                str(filing.get("edgarUrl") or filing.get("link") or filing.get("url") or "").strip()
            )
            filings_us.append({
                "kind": form,
                "title": title,
                "occurred_at_kst": dt_kst.isoformat(),
                "source": "SEC / Yahoo Finance",
                "url": url,
            })
    except Exception as exc:
        LOG.warning("sec_filings fetch failed for %s: %s", yf_symbol, exc)
        errors.append(f"SEC filings unavailable: {exc}")

    result = (filings_us, errors)
    _source_cache_set(key, result, _source_cache_ttl(errors=errors))
    return result


def _fetch_dart_disclosures_cached(
    ticker: str,
    since_kst: datetime,
    now_kst: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str], list[str]]:
    key = ("dart_disclosures", ticker, *_window_cache_key_parts(since_kst, now_kst))
    cached = _source_cache_get(key)
    if cached is not None:
        return cached

    result = _fetch_dart_disclosures(
        ticker=ticker,
        since_kst=since_kst,
        now_kst=now_kst,
    )
    _filings_kr, _earnings_kr, notes, errors = result
    _source_cache_set(key, result, _source_cache_ttl(errors=errors, notes=notes))
    return result


def _fetch_earnings_dates_cached(
    ticker_client: Any,
    yf_symbol: str,
    since_kst: datetime,
    now_kst: datetime,
) -> tuple[list[dict[str, Any]], list[str]]:
    key = ("earnings_dates", yf_symbol, *_window_cache_key_parts(since_kst, now_kst))
    cached = _source_cache_get(key)
    if cached is not None:
        return cached

    earnings_us: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        earnings_df = ticker_client.get_earnings_dates(limit=20, offset=0)
        if earnings_df is not None and hasattr(earnings_df, "iterrows"):
            for idx, row in earnings_df.iterrows():
                dt_kst = _to_kst(_parse_datetime(idx))
                if not dt_kst or dt_kst < since_kst or dt_kst > now_kst:
                    continue
                eps_est = row.get("EPS Estimate") if hasattr(row, "get") else None
                eps_rep = row.get("Reported EPS") if hasattr(row, "get") else None
                surprise = row.get("Surprise(%)") if hasattr(row, "get") else None
                item = {
                    "title": "실적 발표(Earnings)",
                    "occurred_at_kst": dt_kst.isoformat(),
                    "source": "Yahoo Finance Earnings Calendar",
                    "eps_estimate": None if eps_est is None else str(eps_est),
                    "eps_reported": None if eps_rep is None else str(eps_rep),
                    "surprise_pct": None if surprise is None else str(surprise),
                    "url": _normalize_url(f"/calendar/earnings?symbol={yf_symbol}"),
                }
                earnings_us.append(item)
    except Exception as exc:
        LOG.warning("earnings_dates fetch failed for %s: %s", yf_symbol, exc)
        errors.append(f"Earnings calendar unavailable: {exc}")

    result = (earnings_us, errors)
    _source_cache_set(key, result, _source_cache_ttl(errors=errors))
    return result


def _fetch_news_cached(
    ticker_client: Any,
    yf_symbol: str,
    news_limit: int,
    since_kst: datetime,
    now_kst: datetime,
    is_us: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    key = ("news", yf_symbol, int(news_limit), bool(is_us), *_window_cache_key_parts(since_kst, now_kst))
    cached = _source_cache_get(key)
    if cached is not None:
        return cached

    news_items: list[dict[str, Any]] = []
    transcripts_us_earnings: list[dict[str, Any]] = []
    transcripts_us_corporate: list[dict[str, Any]] = []
    errors: list[str] = []

    try:
        raw_news = ticker_client.get_news(count=news_limit, tab="all") or []
        for article in raw_news:
            if not isinstance(article, dict):
                continue
            title = _pick_text(article, [
                ("title",),
                ("content", "title"),
                ("headline",),
            ])
            summary = _pick_text(article, [
                ("summary",),
                ("content", "summary"),
                ("description",),
            ])
            provider = _pick_text(article, [
                ("publisher",),
                ("provider", "displayName"),
                ("content", "provider", "displayName"),
                ("source",),
            ]) or "Yahoo Finance"
            url = _normalize_url(_pick_text(article, [
                ("link",),
                ("url",),
                ("canonicalUrl", "url"),
                ("content", "canonicalUrl", "url"),
                ("content", "clickThroughUrl", "url"),
                ("content", "finance", "url"),
            ]))
            dt_kst = _to_kst(_parse_datetime(
                _dig(article, "providerPublishTime")
                or _dig(article, "pubDate")
                or _dig(article, "publishedAt")
                or _dig(article, "content", "pubDate")
                or _dig(article, "content", "displayTime")
                or _dig(article, "displayTime")
            ))

            if not title and not summary:
                continue
            if dt_kst and (dt_kst < since_kst or dt_kst > now_kst):
                continue

            item = {
                "title": title or summary[:120] or "News",
                "summary": summary,
                "occurred_at_kst": dt_kst.isoformat() if dt_kst else "",
                "source": provider,
                "url": url,
            }
            news_items.append(item)

            if is_us:
                transcript_kind = _classify_transcript(title, summary)
                if transcript_kind == "earnings":
                    transcripts_us_earnings.append({
                        "title": item["title"],
                        "occurred_at_kst": item["occurred_at_kst"],
                        "source": item["source"],
                        "url": item["url"],
                    })
                elif transcript_kind == "corporate":
                    transcripts_us_corporate.append({
                        "title": item["title"],
                        "occurred_at_kst": item["occurred_at_kst"],
                        "source": item["source"],
                        "url": item["url"],
                    })
    except Exception as exc:
        LOG.warning("news fetch failed for %s: %s", yf_symbol, exc)
        errors.append(f"News feed unavailable: {exc}")

    result = (news_items, transcripts_us_earnings, transcripts_us_corporate, errors)
    _source_cache_set(key, result, _source_cache_ttl(errors=errors))
    return result


def get_instrument_insights(ticker: str, days: int = 30, news_limit: int = 3) -> dict[str, Any]:
    """
    Build event/news insight payload for a single ticker.

    Data window is recent `days` from now, filtered in KST.
    """
    normalized = _normalize_ticker(ticker)
    if not normalized:
        return {"status": "error", "message": "ticker is required"}

    try:
        import yfinance as yf
    except Exception as exc:
        LOG.warning("yfinance import failed: %s", exc)
        return {"status": "error", "message": "market data source unavailable"}

    days = max(7, min(int(days or 30), 90))
    news_limit = max(1, min(int(news_limit or 3), 80))
    now_kst = datetime.now(KST)
    since_kst = now_kst - timedelta(days=days)
    yf_symbol = map_to_yfinance(normalized) or normalized
    is_korean = normalized.isdigit() and len(normalized) == 6
    is_us = _is_us_symbol(normalized, yf_symbol)

    filings_us: list[dict[str, Any]] = []
    filings_kr: list[dict[str, Any]] = []
    earnings_us: list[dict[str, Any]] = []
    earnings_kr: list[dict[str, Any]] = []
    transcripts_us_earnings: list[dict[str, Any]] = []
    transcripts_us_corporate: list[dict[str, Any]] = []
    news_items: list[dict[str, Any]] = []
    notes: list[str] = []
    errors: list[str] = []

    ticker_client = yf.Ticker(yf_symbol)

    # SEC filings (US only in Yahoo data)
    if is_us:
        us_filings, us_filing_errors = _fetch_sec_filings_cached(
            ticker_client=ticker_client,
            yf_symbol=yf_symbol,
            since_kst=since_kst,
            now_kst=now_kst,
        )
        filings_us.extend(us_filings)
        errors.extend(us_filing_errors)

    if is_korean:
        kr_filings, kr_earnings, kr_notes, kr_errors = _fetch_dart_disclosures_cached(
            ticker=normalized,
            since_kst=since_kst,
            now_kst=now_kst,
        )
        filings_kr.extend(kr_filings)
        earnings_kr.extend(kr_earnings)
        notes.extend(kr_notes)
        errors.extend(kr_errors)
    elif is_us:
        notes.append("미국 공시는 SEC 20-F/10-K/10-Q/8-K/6-K 기준으로 최근 1개월만 제공합니다.")

    # Earnings dates (US only from Yahoo earnings calendar)
    if is_us:
        us_earnings, us_earnings_errors = _fetch_earnings_dates_cached(
            ticker_client=ticker_client,
            yf_symbol=yf_symbol,
            since_kst=since_kst,
            now_kst=now_kst,
        )
        earnings_us.extend(us_earnings)
        errors.extend(us_earnings_errors)

    # News + transcript classification
    cached_news, cached_earnings_transcripts, cached_corporate_transcripts, news_errors = _fetch_news_cached(
        ticker_client=ticker_client,
        yf_symbol=yf_symbol,
        news_limit=news_limit,
        since_kst=since_kst,
        now_kst=now_kst,
        is_us=is_us,
    )
    news_items.extend(cached_news)
    transcripts_us_earnings.extend(cached_earnings_transcripts)
    transcripts_us_corporate.extend(cached_corporate_transcripts)
    errors.extend(news_errors)

    return {
        "status": "ok",
        "ticker": normalized,
        "yf_symbol": yf_symbol,
        "is_korean": is_korean,
        "is_us": is_us,
        "window": {
            "from_kst": since_kst.isoformat(),
            "to_kst": now_kst.isoformat(),
            "days": days,
        },
        "filings": {
            "us": _sort_desc(filings_us),
            "kr": _sort_desc(filings_kr),
        },
        "earnings": {
            "us": _sort_desc(earnings_us),
            "kr": _sort_desc(earnings_kr),
        },
        "transcripts": {
            "us_earnings": _sort_desc(transcripts_us_earnings),
            "us_corporate": _sort_desc(transcripts_us_corporate),
        },
        "news": _sort_desc(news_items)[:news_limit],
        "notes": notes,
        "errors": errors,
    }
