"""Single source of truth for sector label normalization.

영문 GICS 섹터명 → 한국어 UI 라벨로 매핑.
백엔드/프런트엔드 어디서든 동일한 결과가 나오도록 이 파일을 유일한 출처로 사용합니다.
프런트엔드는 API 응답의 `sector_label` 필드를 그대로 사용해야 하며,
별도의 매핑 테이블을 유지하지 않습니다.
"""
from __future__ import annotations

import re
from typing import Iterable

# ── Canonical sector label map ─────────────────────────────────
# 정책: GICS "Information Technology"는 소프트웨어/하드웨어/반도체를 모두 포함하는
# 광역 섹터라서 통째로 "반도체"로 매핑하면 마이크로소프트·어도비·시스코 같은 소프트웨어
# 종목까지 반도체로 표시됨. 따라서 "Information Technology"의 기본 매핑은 "IT"이고,
# 실제 반도체 사업이 본업인 종목(NVDA, 005930 등)은 SEMICONDUCTOR_TICKERS 오버라이드로
# "반도체"로 격상.
SECTOR_ALIAS: dict[str, str] = {
    # yfinance 표준 어휘 (Ticker(...).info["sector"]가 실제 반환하는 값)
    "Technology": "IT",
    "Communication Services": "커뮤니케이션",
    "Healthcare": "바이오",
    "Financial Services": "금융",
    "Consumer Cyclical": "소비재",
    "Consumer Defensive": "소비재",
    "Basic Materials": "소재",
    "Industrials": "산업재",
    "Energy": "에너지",
    "Utilities": "유틸리티",
    "Real Estate": "부동산",
    # S&P GICS 원본 (호환용 — 일부 외부 데이터가 이 어휘를 사용)
    "Information Technology": "IT",
    "Communication": "커뮤니케이션",
    "Consumer Discretionary": "소비재",
    "Consumer Staples": "소비재",
    "Health Care": "바이오",
    "Financials": "금융",
    "Materials": "소재",
    # 기타 비표준 값 — 시드 전용
    "Fixed Income": "채권",
    "Bonds": "채권",
    "Cash": "현금",
    "Other": "기타",
    # 이미 한국어로 들어오는 경우 — 항등 매핑(존재 확인용)
    "반도체": "반도체",
    "IT": "IT",
    "커뮤니케이션": "커뮤니케이션",
    "바이오": "바이오",
    "금융": "금융",
    "2차전지": "2차전지",
    "소비재": "소비재",
    "소재": "소재",
    "산업재": "산업재",
    "에너지": "에너지",
    "유틸리티": "유틸리티",
    "부동산": "부동산",
    "채권": "채권",
    "현금": "현금",
    "기타": "기타",
}

# KRX `get_market_sector_classifications()`의 업종명은 yfinance sector와
# 체계가 다르므로, 화면에는 yfinance-compatible canonical 라벨로 맞춘다.
KRX_INDUSTRY_ALIAS: dict[str, str] = {
    # IT / 반도체
    "반도체": "반도체",
    "전기·전자": "IT",
    "전기전자": "IT",
    "일반전기전자": "IT",
    "IT H/W": "IT",
    "IT HW": "IT",
    "IT부품": "IT",
    "통신장비": "IT",
    "정보기기": "IT",
    "소프트웨어": "IT",
    "컴퓨터서비스": "IT",
    # Communication Services
    "커뮤니케이션": "커뮤니케이션",
    "통신": "커뮤니케이션",
    "통신업": "커뮤니케이션",
    "통신서비스": "커뮤니케이션",
    "통신방송서비스": "커뮤니케이션",
    "방송서비스": "커뮤니케이션",
    "인터넷": "커뮤니케이션",
    "디지털컨텐츠": "커뮤니케이션",
    "오락·문화": "커뮤니케이션",
    "오락문화": "커뮤니케이션",
    "출판·매체복제": "커뮤니케이션",
    "출판매체복제": "커뮤니케이션",
    "서비스업": "커뮤니케이션",
    # Healthcare
    "의약품": "바이오",
    "제약": "바이오",
    "의료·정밀기기": "바이오",
    "의료정밀": "바이오",
    "의료정밀기기": "바이오",
    # Financials
    "금융": "금융",
    "금융업": "금융",
    "기타금융": "금융",
    "은행": "금융",
    "증권": "금융",
    "보험": "금융",
    # Consumer
    "유통": "소비재",
    "유통업": "소비재",
    "음식료·담배": "소비재",
    "음식료품": "소비재",
    "담배": "소비재",
    "섬유·의류": "소비재",
    "섬유의류": "소비재",
    "섬유의복": "소비재",
    # Materials
    "소재": "소재",
    "화학": "소재",
    "비금속": "소재",
    "비금속광물": "소재",
    "금속": "소재",
    "철강·금속": "소재",
    "철강금속": "소재",
    "종이·목재": "소재",
    "종이목재": "소재",
    # Industrials
    "산업재": "산업재",
    "기계·장비": "산업재",
    "기계장비": "산업재",
    "기계": "산업재",
    "건설": "산업재",
    "건설업": "산업재",
    "운송": "산업재",
    "운송장비·부품": "산업재",
    "운송장비부품": "산업재",
    "운수장비": "산업재",
    "운송창고": "산업재",
    "운수창고업": "산업재",
    "운수창고": "산업재",
    "제조": "산업재",
    "제조업": "산업재",
    "기타제조": "산업재",
    "일반서비스": "산업재",
    "기타서비스": "산업재",
    # Energy / Utilities / REITs / fixed income
    "에너지": "에너지",
    "전기·가스": "유틸리티",
    "전기가스업": "유틸리티",
    "부동산": "부동산",
    "리츠": "부동산",
    "채권": "채권",
    "현금": "현금",
}

UNKNOWN_SECTOR_VALUES = {"", "other", "unknown", "none", "n/a", "na", "기타"}


def _fold_sector_key(raw: str) -> str:
    """Normalize sector spelling differences from KRX/yfinance sources."""
    return re.sub(r"[\s·ㆍ/\\_\-()&]+", "", raw).lower()


_KRX_INDUSTRY_ALIAS_FOLDED = {
    _fold_sector_key(key): value for key, value in KRX_INDUSTRY_ALIAS.items()
}

# 반도체 사업이 본업인 종목 (티커/단축코드 단위 오버라이드).
# 여기에 등록되면 raw_sector가 무엇이든 "반도체"로 분류됨.
SEMICONDUCTOR_TICKERS: set[str] = {
    # US 반도체
    "NVDA", "AMD", "AVGO", "INTC", "QCOM", "MU", "TXN", "ADI", "MRVL",
    "AMAT", "LRCX", "KLAC", "ASML", "TSM",
    # KR 반도체
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
    "042700",  # 한미반도체
    "000990",  # DB하이텍
    "058470",  # 리노공업
    "095340",  # ISC
    "403870",  # HPSP
    "357780",  # 솔브레인
    "240810",  # 원익IPS
    "005290",  # 동진쎄미켐
    "108320",  # LX세미콘
    "039030",  # 이오테크닉스
    "036930",  # 주성엔지니어링
}

# 2차전지·소재 본업 오버라이드 (Materials 외에 명시 케이스가 필요할 때).
BATTERY_TICKERS: set[str] = {
    "373220",  # LG에너지솔루션
    "051910",  # LG화학
    "006400",  # 삼성SDI
}

DEFAULT_LABEL = "기타"


def is_unknown_sector(raw: str | None) -> bool:
    """Return whether a raw sector value carries no useful classification."""
    return _fold_sector_key(str(raw or "")) in UNKNOWN_SECTOR_VALUES


def normalize_sector(raw: str | None) -> str:
    """Return canonical Korean sector label for any input form.

    None/빈 문자열/매핑 없는 값은 모두 "기타"로 정리.
    티커 정보를 모르는 경로(시뮬레이션 페르소나 등)에서 사용.
    """
    if not raw:
        return DEFAULT_LABEL
    key = str(raw).strip()
    if not key:
        return DEFAULT_LABEL
    if key in SECTOR_ALIAS:
        return SECTOR_ALIAS[key]
    if key in SECTOR_ALIAS.values():
        return key
    folded_key = _fold_sector_key(key)
    if folded_key in _KRX_INDUSTRY_ALIAS_FOLDED:
        return _KRX_INDUSTRY_ALIAS_FOLDED[folded_key]
    return DEFAULT_LABEL


def normalize_sector_for_symbol(symbol: str | None, raw_sector: str | None) -> str:
    """Symbol-aware sector normalization.

    실제 반도체/2차전지 종목은 raw_sector(GICS)가 일반적인 IT/Materials이어도
    적절한 한국어 라벨로 격상. 그 외에는 normalize_sector와 동일.
    """
    if symbol:
        sym = str(symbol).strip().upper()
        if sym in SEMICONDUCTOR_TICKERS:
            return "반도체"
        if sym in BATTERY_TICKERS:
            return "2차전지"
    return normalize_sector(raw_sector)


def normalize_sector_map(weights: dict[str, float]) -> dict[str, float]:
    """Aggregate a sector→weight map under canonical labels."""
    out: dict[str, float] = {}
    for raw, w in weights.items():
        label = normalize_sector(raw)
        out[label] = out.get(label, 0.0) + float(w)
    return out


def known_labels() -> Iterable[str]:
    """Set of canonical labels that the UI may receive."""
    return set(SECTOR_ALIAS.values())
