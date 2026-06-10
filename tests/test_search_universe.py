import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_search_finds_symbol_from_expanded_local_seed(tmp_path, monkeypatch):
    # Arrange: expanded local seed contains symbols not present in core seed
    data_path = tmp_path / "search_universe.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "symbol": "IWM",
                    "name": "iShares Russell 2000 ETF",
                    "name_ko": "",
                    "name_en": "iShares Russell 2000 ETF",
                    "market": "NYSE",
                    "country": "US",
                    "symbol_type": "etf",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEARCH_UNIVERSE_FILE", str(data_path))

    from backend.search_universe import search_instruments

    seed_items = [
        {
            "symbol": "QQQ",
            "name": "Invesco QQQ Trust",
            "name_ko": "QQQ",
            "name_en": "Invesco QQQ Trust",
            "market": "NASDAQ",
            "country": "US",
            "symbol_type": "etf",
        }
    ]

    # Act
    results = search_instruments("IWM", limit=10, seed_items=seed_items)

    # Assert
    assert len(results) >= 1
    assert results[0]["symbol"] == "IWM"


def test_seed_entry_wins_when_symbol_duplicated(tmp_path, monkeypatch):
    data_path = tmp_path / "search_universe.json"
    data_path.write_text(
        json.dumps(
            [
                {
                    "symbol": "QQQ",
                    "name": "QQQ external",
                    "name_ko": "",
                    "name_en": "QQQ external",
                    "market": "NASDAQ",
                    "country": "US",
                    "symbol_type": "etf",
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SEARCH_UNIVERSE_FILE", str(data_path))

    from backend.search_universe import search_instruments

    seed_items = [
        {
            "symbol": "QQQ",
            "name": "QQQ seed",
            "name_ko": "QQQ시드",
            "name_en": "QQQ seed",
            "market": "NASDAQ",
            "country": "US",
            "symbol_type": "etf",
        }
    ]

    results = search_instruments("QQQ", limit=10, seed_items=seed_items)

    assert results
    assert results[0]["symbol"] == "QQQ"
    assert results[0]["name_ko"] == "QQQ시드"


def test_empty_query_returns_empty_list(tmp_path, monkeypatch):
    data_path = tmp_path / "search_universe.json"
    data_path.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("SEARCH_UNIVERSE_FILE", str(data_path))

    from backend.search_universe import search_instruments

    results = search_instruments("", limit=10, seed_items=[])
    assert results == []
