"""Single source of truth for sector label normalization.

영문 GICS 섹터명 → 한국어 UI 라벨로 매핑.
백엔드/프런트엔드 어디서든 동일한 결과가 나오도록 이 파일을 유일한 출처로 사용합니다.
프런트엔드는 API 응답의 `sector_label` 필드를 그대로 사용해야 하며,
별도의 매핑 테이블을 유지하지 않습니다.
"""
from __future__ import annotations

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
    "Communication Services": "IT",
    "Healthcare": "바이오",
    "Financial Services": "금융",
    "Consumer Cyclical": "기타",
    "Consumer Defensive": "기타",
    "Basic Materials": "2차전지",
    "Industrials": "기타",
    "Energy": "기타",
    "Utilities": "기타",
    "Real Estate": "기타",
    # S&P GICS 원본 (호환용 — 일부 외부 데이터가 이 어휘를 사용)
    "Information Technology": "IT",
    "Communication": "IT",
    "Consumer Discretionary": "기타",
    "Consumer Staples": "기타",
    "Health Care": "바이오",
    "Financials": "금융",
    "Materials": "2차전지",
    # 기타 비표준 값 — 시드 전용
    "Fixed Income": "기타",
    "Bonds": "기타",
    "Cash": "기타",
    "Other": "기타",
    # 이미 한국어로 들어오는 경우 — 항등 매핑(존재 확인용)
    "반도체": "반도체",
    "IT": "IT",
    "바이오": "바이오",
    "금융": "금융",
    "2차전지": "2차전지",
    "기타": "기타",
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
}

# 2차전지·소재 본업 오버라이드 (Materials 외에 명시 케이스가 필요할 때).
BATTERY_TICKERS: set[str] = {
    "373220",  # LG에너지솔루션
    "051910",  # LG화학
    "006400",  # 삼성SDI
}

DEFAULT_LABEL = "기타"


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
    return SECTOR_ALIAS.get(key, key if key in SECTOR_ALIAS.values() else DEFAULT_LABEL)


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
