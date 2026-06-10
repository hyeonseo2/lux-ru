#!/usr/bin/env python3
"""Build a large local search universe JSON for autocomplete.

Outputs:
- backend/data/search_universe.json

Sources:
- US symbols (NASDAQ/NYSE/AMEX) from public GitHub mirror
- KR listed companies from KRX KIND download page
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

OUT_PATH = Path(__file__).resolve().parents[1] / "backend" / "data" / "search_universe.json"

US_SOURCES = {
    "NASDAQ": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nasdaq/nasdaq_full_tickers.json",
    "NYSE": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/nyse/nyse_full_tickers.json",
    "AMEX": "https://raw.githubusercontent.com/rreichel3/US-Stock-Symbols/main/amex/amex_full_tickers.json",
}

US_ETF_SCREENER_URL = "https://api.nasdaq.com/api/screener/etf?download=true"

KRX_URL = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download&searchType=13"

# Instruments that are generally not intended for this search UX
NOISE_NAME_KEYWORDS = [
    "WARRANT",
    "RIGHT",
    "UNITS",
    "UNIT",
    "PREFERRED",
    "DEPOSITARY",
    "NOTES",
    "BOND",
    "ETF SERIES",
]

ETF_NAME_KEYWORDS = [
    "ETF",
    "ETN",
    "INDEX FUND",
    "TRUST",
]

VALID_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,23}$")


def _normalize_symbol(raw: Any) -> str:
    symbol = str(raw or "").strip().upper()
    symbol = symbol.replace("/", ".")
    symbol = symbol.replace(" ", "")
    return symbol


def _is_noisy_name(name: str) -> bool:
    upper = name.upper()
    return any(token in upper for token in NOISE_NAME_KEYWORDS)


def _guess_symbol_type(name: str) -> str:
    upper = name.upper()
    if any(token in upper for token in ETF_NAME_KEYWORDS):
        return "etf"
    return "stock"


def _load_us_universe(session: requests.Session) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    for market, url in US_SOURCES.items():
        resp = session.get(url, timeout=40)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, list):
            continue

        for row in payload:
            if not isinstance(row, dict):
                continue
            symbol = _normalize_symbol(row.get("symbol"))
            if not symbol or not VALID_SYMBOL_RE.match(symbol):
                continue

            name_en = str(row.get("name") or "").strip()
            if not name_en:
                continue
            if _is_noisy_name(name_en):
                continue

            if symbol in seen:
                continue
            seen.add(symbol)

            rows.append(
                {
                    "symbol": symbol,
                    "name": name_en,
                    "name_ko": "",
                    "name_en": name_en,
                    "market": market,
                    "country": "US",
                    "symbol_type": _guess_symbol_type(name_en),
                }
            )

    return rows


def _load_us_etf_universe(session: requests.Session) -> list[dict[str, Any]]:
    resp = session.get(US_ETF_SCREENER_URL, timeout=40)
    resp.raise_for_status()

    payload = resp.json()
    rows = (
        payload.get("data", {})
        .get("data", {})
        .get("rows", [])
    )
    if not isinstance(rows, list):
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue

        symbol = _normalize_symbol(row.get("symbol"))
        if not symbol or not VALID_SYMBOL_RE.match(symbol):
            continue
        if symbol in seen:
            continue

        name_en = str(row.get("companyName") or row.get("name") or "").strip()
        if not name_en:
            continue

        seen.add(symbol)
        out.append(
            {
                "symbol": symbol,
                "name": name_en,
                "name_ko": "",
                "name_en": name_en,
                "market": "US-ETF",
                "country": "US",
                "symbol_type": "etf",
            }
        )

    return out


def _load_krx_universe(session: requests.Session) -> list[dict[str, Any]]:
    resp = session.get(KRX_URL, timeout=40)
    resp.raise_for_status()
    resp.encoding = "euc-kr"

    soup = BeautifulSoup(resp.text, "html.parser")
    rows = soup.select("table tr")

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    market_map = {
        "코스피": "KRX",
        "유가": "KRX",
        "코스닥": "KOSDAQ",
        "코넥스": "KONEX",
    }

    # Header: 회사명, 시장구분, 종목코드, ...
    for tr in rows[1:]:
        cols = [td.get_text(strip=True) for td in tr.find_all("td")]
        if len(cols) < 3:
            continue

        name_ko = str(cols[0]).strip()
        market_ko = str(cols[1]).strip()
        symbol = str(cols[2]).strip()

        if not re.fullmatch(r"\d{6}", symbol):
            continue
        if symbol in seen:
            continue
        seen.add(symbol)

        out.append(
            {
                "symbol": symbol,
                "name": name_ko or symbol,
                "name_ko": name_ko,
                "name_en": "",
                "market": market_map.get(market_ko, market_ko or "KRX"),
                "country": "KR",
                "symbol_type": "stock",
            }
        )

    return out


def _latest_krx_business_days(limit: int = 10) -> list[str]:
    d = datetime.now(ZoneInfo("Asia/Seoul"))
    if d.hour < 9:
        d -= timedelta(days=1)

    out: list[str] = []
    while len(out) < limit:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d -= timedelta(days=1)
    return out


def _load_krx_etf_universe() -> list[dict[str, Any]]:
    try:
        from pykrx import stock  # type: ignore
    except Exception as exc:
        print(f"skip KRX ETF universe: pykrx unavailable ({exc})")
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for date in _latest_krx_business_days():
        try:
            codes = stock.get_etf_ticker_list(date)
        except Exception as exc:
            print(f"skip KRX ETF list {date}: {exc}")
            codes = []
        if not codes:
            continue

        for raw_code in codes:
            symbol = str(raw_code or "").strip().zfill(6)
            if not re.fullmatch(r"\d{6}", symbol):
                continue
            if symbol in seen:
                continue
            try:
                name = str(stock.get_etf_ticker_name(symbol) or "").strip()
            except Exception:
                name = ""
            out.append({
                "symbol": symbol,
                "name": name or symbol,
                "name_ko": name or symbol,
                "name_en": "",
                "market": "KRX-ETF",
                "country": "KR",
                "symbol_type": "etf",
            })
            seen.add(symbol)
        break

    return out


def build_search_universe() -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (LUX-RU search-universe builder)",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://www.nasdaq.com/market-activity",
    })

    us = _load_us_universe(session)
    us_etf = _load_us_etf_universe(session)
    kr = _load_krx_universe(session)
    kr_etf = _load_krx_etf_universe()

    merged: dict[str, dict[str, Any]] = {}

    # KR first (Korean search UX), then US stock, then US ETF.
    for item in kr + kr_etf + us + us_etf:
        sym = item["symbol"]
        if sym not in merged:
            merged[sym] = item

    rows = list(merged.values())
    rows.sort(key=lambda x: (x["country"], x["symbol"]))
    return rows


def main() -> None:
    rows = build_search_universe()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")

    kr_count = sum(1 for x in rows if x.get("country") == "KR")
    us_count = sum(1 for x in rows if x.get("country") == "US")
    print(f"saved: {OUT_PATH}")
    print(f"total={len(rows)} kr={kr_count} us={us_count}")


if __name__ == "__main__":
    main()
