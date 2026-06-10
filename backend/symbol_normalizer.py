"""Canonical symbol helpers shared by live look-through flows."""
from __future__ import annotations

from functools import lru_cache
import re
import unicodedata
from typing import Any


_MARKET_SUFFIXES = {
    "US", "UQ", "UW", "UN", "UP", "UR", "N", "O", "A",
    "EQUITY", "COM", "COMMON", "STOCK",
    "NASDAQ", "NYSE", "NYSEARCA", "ARCA", "AMEX", "BATS",
    "KR", "KS", "KQ", "JP", "JT", "HK", "LN", "L", "TO", "CN",
    "SS", "SZ", "SW", "GR", "GY", "DE", "PA", "FP",
}

_COMPACT_SUFFIXES = (
    "USEQUITY", "UQEQUITY", "UWEQUITY", "UNEQUITY",
    "NYSE", "NASDAQ", "NYSEARCA", "ARCA", "AMEX",
    "US", "UQ", "UW", "UN",
)
_NUMERIC_MARKET_SUFFIXES = {
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

_CORPORATE_SUFFIXES = {
    "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
    "LTD", "LIMITED", "PLC", "SA", "AG", "NV", "BV", "SE",
    "HOLDING", "HOLDINGS", "GROUP", "THE",
    "COMMON", "STOCK", "ORDINARY", "SHARE", "SHARES",
    "CLASS", "CL", "ADR", "ADS", "SPONSORED",
}


def _text(raw: Any) -> str:
    return unicodedata.normalize("NFKC", str(raw or "")).strip()


def normalize_ticker(raw: Any) -> str:
    """Return a display-safe ticker without trying to resolve aliases."""
    text = _text(raw).upper()
    text = text.replace("/", ".")
    text = re.sub(r"[^A-Z0-9.\-]", "", text)
    return text[:24]


def _symbol_key(raw: Any) -> str:
    text = normalize_ticker(raw)
    return text.replace("-", ".")


def _alias_key(raw: Any) -> str:
    text = _text(raw).upper()
    text = text.replace("&", " AND ")
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.sub(r"[^A-Z0-9가-힣]+", " ", text)
    tokens = [t for t in text.split() if t and t not in _CORPORATE_SUFFIXES]
    return "".join(tokens)


def _share_class_variants(symbol: str) -> set[str]:
    variants = {symbol}
    if "." in symbol:
        variants.add(symbol.replace(".", "-"))
        variants.add(symbol.replace(".", "/"))
        variants.add(symbol.replace(".", " "))
    if "-" in symbol:
        variants.add(symbol.replace("-", "."))
    if "/" in symbol:
        variants.add(symbol.replace("/", "."))
    return {v for v in variants if v}


def _add_alias(target: dict[str, str | None], key: str, symbol: str, *, prefer: bool = False) -> None:
    if not key:
        return
    existing = target.get(key)
    if existing is None and key in target and not prefer:
        return
    if existing and existing != symbol and not prefer:
        return
    if existing and existing != symbol and prefer:
        target[key] = symbol
        return
    if existing is None and key in target and prefer:
        target[key] = symbol
        return
    target[key] = symbol


@lru_cache(maxsize=1)
def _instrument_indexes() -> tuple[dict[str, str], dict[str, str | None]]:
    """Build symbol/name indexes from seed data and the local expanded universe."""
    symbol_index: dict[str, str] = {}
    alias_index: dict[str, str | None] = {}

    def register(item: dict[str, Any], *, prefer: bool = False) -> None:
        symbol = normalize_ticker(item.get("symbol"))
        if not symbol:
            return

        for variant in _share_class_variants(symbol):
            key = _symbol_key(variant)
            if prefer or key not in symbol_index:
                symbol_index[key] = symbol

        for field in ("symbol", "name", "name_ko", "name_en"):
            value = item.get(field)
            if not value:
                continue
            _add_alias(alias_index, _alias_key(value), symbol, prefer=prefer)
            class_match = re.fullmatch(r"[A-Z]{1,5}\.([A-Z])", symbol)
            if class_match and field != "symbol":
                class_code = class_match.group(1)
                _add_alias(alias_index, _alias_key(f"{value} {class_code}"), symbol, prefer=prefer)
                _add_alias(alias_index, _alias_key(f"{value} Class {class_code}"), symbol, prefer=prefer)
            if field == "symbol":
                _add_alias(alias_index, _symbol_key(value), symbol, prefer=prefer)

    try:
        from .search_universe import build_seed_search_items, load_expanded_universe

        for row in build_seed_search_items():
            register(row, prefer=True)
        for row in load_expanded_universe(force_reload=False):
            register(row, prefer=False)
    except Exception:
        try:
            from .seed_data import ALL_INSTRUMENTS

            for inst in ALL_INSTRUMENTS.values():
                register(
                    {
                        "symbol": inst.symbol,
                        "name": inst.name_ko or inst.name_en or inst.symbol,
                        "name_ko": inst.name_ko,
                        "name_en": inst.name_en,
                    },
                    prefer=True,
                )
        except Exception:
            pass

    return symbol_index, alias_index


def _strip_market_suffix_tokens(tokens: list[str]) -> list[str]:
    out = list(tokens)
    while len(out) > 1 and out[-1] in _MARKET_SUFFIXES:
        out.pop()
    return out


def _format_numeric_market_symbol(code: str, suffix: str) -> str | None:
    market = _NUMERIC_MARKET_SUFFIXES.get(suffix.upper())
    if not market or not re.fullmatch(r"\d{1,6}", code):
        return None
    yf_suffix, width = market
    padded = code.zfill(width)
    return padded if not yf_suffix else f"{padded}.{yf_suffix}"


def _numeric_market_symbol_from_text(raw: str) -> str | None:
    text = raw.upper().strip().replace("/", ".").replace("_", " ")
    match = re.fullmatch(r"\s*(\d{1,6})\s*[.\-\s]\s*([A-Z]{1,3})\s*", text)
    if not match:
        return None
    return _format_numeric_market_symbol(match.group(1), match.group(2))


def _symbol_candidates(raw: Any) -> list[str]:
    text = _text(raw).upper()
    if not text:
        return []

    normalized = text.replace("/", ".").replace("_", " ")
    normalized = re.sub(r"[()]", " ", normalized)
    normalized = re.sub(r"[^A-Z0-9.\-\s]", " ", normalized)
    tokens = [t for t in normalized.split() if t]
    stripped = _strip_market_suffix_tokens(tokens)

    candidates: list[str] = []

    def add(value: str) -> None:
        cleaned = normalize_ticker(value)
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

    numeric_market = _numeric_market_symbol_from_text(text)
    if numeric_market:
        add(numeric_market)

    if stripped:
        if len(stripped) >= 2 and len(stripped[1]) == 1 and re.fullmatch(r"[A-Z]", stripped[1]):
            add(f"{stripped[0]}.{stripped[1]}")
        add(stripped[0])
        add("".join(stripped))

    if tokens:
        if len(tokens) >= 2:
            numeric_market = _format_numeric_market_symbol(tokens[0], tokens[1])
            if numeric_market:
                add(numeric_market)
        add(tokens[0])
        add("".join(tokens))

    compact = normalize_ticker(text)
    add(compact)
    compact_key = compact.replace("-", ".")
    for suffix in _COMPACT_SUFFIXES:
        if compact_key.endswith(suffix) and len(compact_key) > len(suffix) + 1:
            add(compact_key[: -len(suffix)])

    return candidates


def canonicalize_symbol(raw_symbol: Any, raw_name: Any = None) -> str:
    """Resolve equivalent source symbols/names into one portfolio aggregation key."""
    symbol_index, alias_index = _instrument_indexes()

    symbol_candidates = _symbol_candidates(raw_symbol)
    if raw_name:
        symbol_candidates.extend(_symbol_candidates(raw_name))

    for candidate in symbol_candidates:
        match = symbol_index.get(_symbol_key(candidate))
        if match:
            return match

    for candidate in symbol_candidates:
        if re.fullmatch(r"\d{4,6}\.[A-Z]{1,3}", candidate):
            return candidate

    for value in (raw_symbol, raw_name):
        if not value:
            continue
        match = alias_index.get(_alias_key(value))
        if match:
            return match

    for candidate in symbol_candidates:
        key = _symbol_key(candidate)
        for suffix in _COMPACT_SUFFIXES:
            if key.endswith(suffix) and len(key) > len(suffix) + 1:
                stripped = key[: -len(suffix)]
                match = symbol_index.get(stripped)
                if match:
                    return match
                if re.fullmatch(r"[A-Z]{1,5}(?:\.[A-Z])?", stripped):
                    return stripped

    for candidate in symbol_candidates:
        if re.fullmatch(r"\d{6}", candidate):
            return candidate
        if re.fullmatch(r"\d{4,6}\.[A-Z]{1,3}", candidate):
            return candidate
        if re.fullmatch(r"[A-Z]{1,5}(?:[.\-][A-Z])?", candidate):
            return candidate.replace("-", ".")

    return normalize_ticker(raw_symbol or raw_name)
