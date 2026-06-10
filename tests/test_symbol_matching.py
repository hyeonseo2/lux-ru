from backend import live_data
from backend.krx_etf import _infer_holding_country, _normalize_code, _normalize_holding_symbol
from backend.symbol_normalizer import canonicalize_symbol


def _stock_node(result, symbol):
    return next(n for n in result["nodes"] if n["id"] == f"Stock_{symbol}")


def test_canonicalize_common_overseas_holding_variants():
    assert canonicalize_symbol("NVDA US Equity", "NVIDIA Corp") == "NVDA"
    assert canonicalize_symbol("NVIDIA Corp", "NVIDIA Corp") == "NVDA"
    assert canonicalize_symbol("BRK-B", "Berkshire Hathaway Inc Class B") == "BRK.B"
    assert canonicalize_symbol("Berkshire Hathaway Inc Class B", "Berkshire Hathaway Inc Class B") == "BRK.B"
    assert canonicalize_symbol("005930", "삼성전자") == "005930"
    assert canonicalize_symbol("700 HK", "Tencent Holdings") == "0700.HK"
    assert canonicalize_symbol("700.HK", "Tencent Holdings") == "0700.HK"
    assert canonicalize_symbol("2330 TT", "Taiwan Semiconductor Manufacturing Company Ltd.") == "2330.TW"


def test_krx_holding_symbol_preserves_name_and_numeric_exchange_suffixes():
    assert _normalize_holding_symbol("삼성전자") == "삼성전자"
    assert _normalize_holding_symbol("700 HK") == "0700.HK"
    assert _normalize_holding_symbol("700.HK") == "0700.HK"
    assert _normalize_holding_symbol("0700 HK") == "0700.HK"
    assert _normalize_holding_symbol("2330 TT") == "2330.TW"
    assert _normalize_holding_symbol("2330.TW") == "2330.TW"
    assert _normalize_holding_symbol("005930 KS") == "005930"


def test_krx_code_normalizer_does_not_rewrite_foreign_numeric_tickers():
    assert _normalize_code("005930") == "005930"
    assert _normalize_code("5930") == "005930"
    assert _normalize_code(5930) == "005930"
    assert _normalize_code("660") == "000660"
    assert _normalize_code("69500") == "069500"
    assert _normalize_code("A005930") == "005930"
    assert _normalize_code("005930.KS") == "005930"
    assert _normalize_code("005930 KQ") == "005930"
    assert _normalize_code("0700.HK") == "0700.HK"
    assert _normalize_code("2330.TW") == "2330.TW"
    assert _normalize_code("7203.T") == "7203.T"


def test_krx_holding_country_inference_handles_numeric_foreign_suffixes():
    assert _infer_holding_country("700 HK", "0700.HK") == "HK"
    assert _infer_holding_country("2330 TT", "2330.TW") == "TW"
    assert _infer_holding_country("2330.TW", "2330.TW") == "TW"
    assert _infer_holding_country("7203 T", "7203.T") == "JP"
    assert _infer_holding_country("7203 JT", "7203.T") == "JP"
    assert _infer_holding_country("600519 SS", "600519.SS") == "CN"
    assert _infer_holding_country("000001 SZ", "000001.SZ") == "CN"


def test_domestic_etf_foreign_holding_matches_direct_us_stock(monkeypatch):
    monkeypatch.setattr(live_data, "is_krx_etf_symbol", lambda symbol: symbol == "360750")
    monkeypatch.setattr(live_data, "get_krx_etf_name", lambda symbol: "TIGER 미국S&P500")
    monkeypatch.setattr(
        live_data,
        "_krx_holdings_for_ticker",
        lambda symbol: [
            {
                "holding_symbol": "NVDA US Equity",
                "holding_name": "NVIDIA Corp",
                "weight": 1.0,
                "sector": "Other",
            }
        ],
    )
    monkeypatch.setattr(live_data, "_get_holdings_from_crawler", lambda symbol: [])

    result = live_data.analyze_live_portfolio(
        [
            {"ticker": "360750", "amount": 1_000_000, "account_type": "taxable"},
            {"ticker": "NVDA", "amount": 500_000, "account_type": "taxable"},
        ]
    )

    assert _stock_node(result, "NVDA")["val"] == 1_500_000
    assert not any(n["id"] in {"Stock_NVDAUS", "Stock_NVIDIA"} for n in result["nodes"])


def test_us_etf_name_holding_matches_direct_us_stock(monkeypatch):
    monkeypatch.setattr(live_data, "is_krx_etf_symbol", lambda symbol: False)
    monkeypatch.setattr(
        live_data,
        "_get_holdings_from_crawler",
        lambda symbol: [
            {
                "holding_symbol": "NVIDIA Corp",
                "holding_name": "NVIDIA Corp",
                "weight": 1.0,
                "sector": "Other",
            }
        ]
        if symbol == "QQQ"
        else [],
    )

    result = live_data.analyze_live_portfolio(
        [
            {"ticker": "QQQ", "amount": 1_000_000, "account_type": "pension_saving"},
            {"ticker": "NVDA", "amount": 500_000, "account_type": "taxable"},
        ]
    )

    assert _stock_node(result, "NVDA")["val"] == 1_500_000
    assert not any(n["id"] == "Stock_NVIDIACORP" for n in result["nodes"])


def test_domestic_stock_name_holding_matches_direct_stock(monkeypatch):
    monkeypatch.setattr(live_data, "is_krx_etf_symbol", lambda symbol: symbol == "091160")
    monkeypatch.setattr(live_data, "get_krx_etf_name", lambda symbol: "KODEX 반도체")
    monkeypatch.setattr(
        live_data,
        "_krx_holdings_for_ticker",
        lambda symbol: [
            {
                "holding_symbol": "삼성전자",
                "holding_name": "삼성전자",
                "weight": 1.0,
                "sector": "전기·전자",
            }
        ],
    )
    monkeypatch.setattr(live_data, "_get_holdings_from_crawler", lambda symbol: [])

    result = live_data.analyze_live_portfolio(
        [
            {"ticker": "091160", "amount": 1_000_000, "account_type": "taxable"},
            {"ticker": "005930", "amount": 500_000, "account_type": "taxable"},
        ]
    )

    assert _stock_node(result, "005930")["val"] == 1_500_000
    assert not any(n["id"] == "Stock_" for n in result["nodes"])


def test_numeric_foreign_holding_matches_direct_foreign_stock(monkeypatch):
    monkeypatch.setattr(live_data, "is_krx_etf_symbol", lambda symbol: symbol == "360750")
    monkeypatch.setattr(live_data, "get_krx_etf_name", lambda symbol: "TIGER 미국S&P500")
    monkeypatch.setattr(
        live_data,
        "_krx_holdings_for_ticker",
        lambda symbol: [
            {
                "holding_symbol": "0700.HK",
                "holding_name": "Tencent Holdings",
                "weight": 1.0,
                "sector": "Communication Services",
            }
        ],
    )
    monkeypatch.setattr(live_data, "_get_holdings_from_crawler", lambda symbol: [])

    result = live_data.analyze_live_portfolio(
        [
            {"ticker": "360750", "amount": 1_000_000, "account_type": "taxable"},
            {"ticker": "700.HK", "amount": 500_000, "account_type": "taxable"},
        ]
    )

    assert _stock_node(result, "0700.HK")["val"] == 1_500_000
