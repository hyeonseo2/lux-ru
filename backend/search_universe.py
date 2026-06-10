"""Search universe loader and matcher for large local symbol autocomplete."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

from .krx_etf import get_krx_etf_universe
from .seed_data import ALL_INSTRUMENTS

DEFAULT_SEARCH_UNIVERSE_FILE = Path(__file__).parent / "data" / "search_universe.json"

_CACHE_LOCK = threading.Lock()
_CACHED_PATH: str | None = None
_CACHED_MTIME: float | None = None
_CACHED_ITEMS: list[dict[str, Any]] | None = None


def _normalize_symbol(raw: Any) -> str:
    symbol = str(raw or "").strip().upper()
    return symbol[:24]


def _normalize_text(raw: Any) -> str:
    return str(raw or "").strip()


def _score_symbol_match(query: str, symbol: str, display_name: str) -> int:
    if not query:
        return 99
    q = query.strip().lower()
    s = symbol.strip().lower()
    d = display_name.strip().lower()

    if s == q:
        return 0
    if s.startswith(q):
        return 1
    if q in s:
        return 2
    if d:
        if d.startswith(q):
            return 3
        if q in d:
            return 4
    return 5


def _normalize_item(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = _normalize_symbol(row.get("symbol"))
    if not symbol:
        return None

    name_ko = _normalize_text(row.get("name_ko"))
    name_en = _normalize_text(row.get("name_en"))
    name = _normalize_text(row.get("name")) or name_ko or name_en or symbol

    market = _normalize_text(row.get("market"))
    country = _normalize_text(row.get("country"))
    symbol_type = _normalize_text(row.get("symbol_type") or row.get("type") or "stock").lower()

    return {
        "symbol": symbol,
        "name": name,
        "name_ko": name_ko,
        "name_en": name_en,
        "market": market,
        "country": country,
        "symbol_type": symbol_type,
    }


def _read_universe_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []

    if not isinstance(payload, list):
        return []

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        item = _normalize_item(raw)
        if not item:
            continue
        symbol = item["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        out.append(item)
    return out


def load_expanded_universe(force_reload: bool = False) -> list[dict[str, Any]]:
    """Load additional symbol universe from local JSON file.

    File path precedence:
    1) env SEARCH_UNIVERSE_FILE
    2) backend/data/search_universe.json
    """
    global _CACHED_PATH, _CACHED_MTIME, _CACHED_ITEMS

    configured = os.getenv("SEARCH_UNIVERSE_FILE", "").strip()
    path = Path(configured) if configured else DEFAULT_SEARCH_UNIVERSE_FILE
    cache_key = str(path.resolve()) if path.exists() else str(path)

    mtime: float | None
    try:
        mtime = path.stat().st_mtime
    except Exception:
        mtime = None

    with _CACHE_LOCK:
        if (
            not force_reload
            and _CACHED_ITEMS is not None
            and _CACHED_PATH == cache_key
            and _CACHED_MTIME == mtime
        ):
            return _CACHED_ITEMS

        items = _read_universe_from_file(path)
        _CACHED_PATH = cache_key
        _CACHED_MTIME = mtime
        _CACHED_ITEMS = items
        return items


def build_seed_search_items() -> list[dict[str, Any]]:
    """Convert current core ALL_INSTRUMENTS to search item schema."""
    items: list[dict[str, Any]] = []
    for inst in ALL_INSTRUMENTS.values():
        symbol = _normalize_symbol(inst.symbol)
        if not symbol:
            continue
        name_ko = _normalize_text(inst.name_ko)
        name_en = _normalize_text(inst.name_en)
        display_name = name_ko or name_en or symbol
        items.append(
            {
                "symbol": symbol,
                "name": display_name,
                "name_ko": name_ko,
                "name_en": name_en,
                "market": _normalize_text(inst.market),
                "country": _normalize_text(inst.country),
                "symbol_type": (
                    inst.instrument_type.value
                    if getattr(inst, "instrument_type", None)
                    else "stock"
                ),
            }
        )
    return items


def _merge_universe_items(seed_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in seed_items:
        item = _normalize_item(raw)
        if not item:
            continue
        symbol = item["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        merged.append(item)

    for item in get_krx_etf_universe(force_reload=False):
        normalized = _normalize_item(item)
        if not normalized:
            continue
        symbol = normalized["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        merged.append(normalized)

    for item in load_expanded_universe(force_reload=False):
        symbol = item["symbol"]
        if symbol in seen:
            continue
        seen.add(symbol)
        merged.append(item)

    return merged


def list_search_universe(
    seed_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return merged seed + expanded search universe in normalized schema."""
    if seed_items is None:
        seed_items = build_seed_search_items()
    return _merge_universe_items(seed_items)


def search_instruments(
    query: str,
    limit: int = 20,
    seed_items: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Search symbols by ticker/name across seed + expanded local universe."""
    q = str(query or "").strip().lower()
    if not q:
        return []

    if seed_items is None:
        seed_items = build_seed_search_items()

    universe = list_search_universe(seed_items)

    hits: list[dict[str, Any]] = []
    for item in universe:
        symbol = item["symbol"]
        name_ko = item.get("name_ko", "")
        name_en = item.get("name_en", "")
        name = item.get("name", "")

        candidates = [symbol, name_ko, name_en, name]
        if not any(q in str(x).lower() for x in candidates if x):
            continue

        display = name_ko or name_en or name or symbol
        score = _score_symbol_match(q, symbol, str(display))
        hits.append(
            {
                "symbol": symbol,
                "name": str(display),
                "name_ko": str(name_ko or ""),
                "name_en": str(name_en or ""),
                "symbol_type": str(item.get("symbol_type", "stock") or "stock"),
                "market": str(item.get("market", "") or ""),
                "country": str(item.get("country", "") or ""),
                "score": score,
            }
        )

    hits.sort(key=lambda x: (x["score"], len(x["symbol"]), x["name"].lower()))
    return hits[: max(1, limit)]
