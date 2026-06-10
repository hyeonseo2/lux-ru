from backend import live_data


def test_live_portfolio_uses_krx_industry_when_holdings_sector_is_unknown(monkeypatch):
    monkeypatch.setattr(live_data, "is_krx_etf_symbol", lambda symbol: symbol == "091160")
    monkeypatch.setattr(live_data, "get_krx_etf_name", lambda symbol: "KODEX 반도체")
    monkeypatch.setattr(
        live_data,
        "_krx_holdings_for_ticker",
        lambda symbol: [
            {
                "holding_symbol": "123456",
                "holding_name": "테스트전자",
                "weight": 1.0,
                "sector": "Other",
            }
        ],
    )
    monkeypatch.setattr(live_data, "get_krx_stock_sector", lambda symbol: "전기·전자")

    result = live_data.analyze_live_portfolio([
        {"ticker": "091160", "amount": 1_000_000, "account_type": "taxable"}
    ])

    assert result["sectors"] == {"IT": 1.0}
    assert result["source_summary"]["krx"] == 1
