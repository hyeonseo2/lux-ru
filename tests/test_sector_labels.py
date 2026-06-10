from backend.sector_labels import is_unknown_sector, normalize_sector, normalize_sector_for_symbol


def test_yfinance_and_krx_sector_inputs_share_canonical_labels():
    assert normalize_sector("Technology") == "IT"
    assert normalize_sector("전기·전자") == "IT"
    assert normalize_sector("Financial Services") == "금융"
    assert normalize_sector("기타금융") == "금융"
    assert normalize_sector("Communication Services") == "커뮤니케이션"
    assert normalize_sector("오락·문화") == "커뮤니케이션"
    assert normalize_sector("Healthcare") == "바이오"
    assert normalize_sector("의료·정밀기기") == "바이오"


def test_symbol_overrides_still_apply_over_broad_sector_inputs():
    assert normalize_sector_for_symbol("005930", "전기·전자") == "반도체"
    assert normalize_sector_for_symbol("NVDA", "Technology") == "반도체"
    assert normalize_sector_for_symbol("006400", "전기·전자") == "2차전지"


def test_unknown_sector_detection_handles_source_variants():
    assert is_unknown_sector(None)
    assert is_unknown_sector("")
    assert is_unknown_sector("Other")
    assert is_unknown_sector("N/A")
    assert is_unknown_sector("기타")
    assert not is_unknown_sector("전기·전자")
