import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_historical_fetch_prices_negative_caches_missing_symbol(monkeypatch):
    from backend import historical

    historical._PRICE_CACHE.clear()
    if hasattr(historical, "_PRICE_MISS_CACHE"):
        historical._PRICE_MISS_CACHE.clear()

    calls = []

    def fake_fetch(symbols, start, end):
        calls.append(tuple(symbols))
        return {}

    monkeypatch.setattr(historical, "_fetch_series_bulk", fake_fetch)

    assert historical.fetch_prices(["MISSING"], "2024-01-01", "2024-01-10") == {}
    assert historical.fetch_prices(["MISSING"], "2024-01-01", "2024-01-10") == {}
    assert calls == [("MISSING",)]


def test_income_fee_batch_returns_fresh_cache_without_live_loader(monkeypatch):
    from backend import income_fees

    income_fees._CACHE.clear()
    cached_payload = {
        "symbol": "AAPL",
        "yf_symbol": "AAPL",
        "instrument_type": "stock",
        "price": 200.0,
        "expense_ratio": 0.0,
        "expense_source": "direct_stock",
        "expense_estimated": False,
        "dividend_yield": 0.5,
        "dividend_source": "cached-test",
        "dividend_estimated": False,
        "dividend_months": [2, 5, 8, 11],
        "data_source": "cached-test",
    }
    income_fees._CACHE["AAPL"] = (time.time() + 60, dict(cached_payload))

    def fail_live_loader(*args, **kwargs):
        raise AssertionError("fresh cache should bypass live yfinance loader")

    monkeypatch.setattr(income_fees, "_load_symbol_income_fee", fail_live_loader)

    loaded = income_fees._load_income_fee_batch([
        {"ticker": "AAPL", "name": "Apple", "type_hint": "stock"}
    ])

    assert loaded["AAPL"] == cached_payload


def test_krx_unavailable_result_is_cached(monkeypatch):
    from backend import krx_etf

    krx_etf._UNIVERSE_CACHE = None
    calls = {"count": 0}

    def fake_get_pykrx_stock():
        calls["count"] += 1
        return None

    monkeypatch.setattr(krx_etf, "_get_pykrx_stock", fake_get_pykrx_stock)

    assert krx_etf.get_krx_etf_universe() == []
    assert krx_etf.get_krx_etf_universe() == []
    assert calls["count"] == 1


def test_loading_copy_explains_cache_first_wait_state():
    html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "구성종목 조회·분석 중" in html
    assert "캐시 우선" in html
    assert "누락 데이터만 새로 조회" in html
    assert "시계열 데이터를 조회하고 있습니다..." not in html
