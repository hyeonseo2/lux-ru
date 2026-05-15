"""Compliance guardrails based on PRD §1.6.

Filters prohibited expressions and adds mandatory disclaimers.
"""
from __future__ import annotations

import re

# ── Prohibited patterns (Korean) ──────────────────────────────

PROHIBITED_PATTERNS = [
    re.compile(r"(이|이것을?|해당\s*종목을?)\s*(사세요|매수하세요|사라|매수해라|사야\s*합니다)"),
    re.compile(r"(파세요|매도하세요|팔아라|매도해라|팔아야\s*합니다)"),
    re.compile(r"수익률이\s*(좋아|높아|개선|향상)\s*(집니다|질\s*것|될\s*것)"),
    re.compile(r"손실\s*위험이?\s*(낮아|줄어|없어)\s*(집니다|질\s*것)"),
    re.compile(r"반드시\s*(오르|상승|수익)"),
    re.compile(r"확실(한|히)\s*(수익|이익|이득)"),
    re.compile(r"(꼭|반드시|무조건)\s*(투자|매수|매도)"),
    re.compile(r"원금\s*보장"),
    re.compile(r"(고수익|대박|떡상)"),
]

# ── Disclaimer ────────────────────────────────────────────────

DISCLAIMER = (
    "\n\n---\n"
    "*본 서비스는 투자자문·일임 서비스가 아닙니다. "
    "표시된 정보는 정보제공 및 시뮬레이션이며, "
    "투자판단과 책임은 사용자 본인에게 있습니다.*"
)

DISCLAIMER_SHORT = (
    "ℹ️ 본 정보는 정보제공 및 시뮬레이션이며 투자자문이 아닙니다."
)


def check_prohibited(text: str) -> list[str]:
    """Check text for prohibited expressions. Returns list of violations."""
    violations = []
    for pattern in PROHIBITED_PATTERNS:
        match = pattern.search(text)
        if match:
            violations.append(f"금지 표현 발견: '{match.group()}'")
    return violations


def sanitize_response(text: str) -> str:
    """Remove prohibited expressions and add disclaimer."""
    for pattern in PROHIBITED_PATTERNS:
        text = pattern.sub("[시뮬레이션 참고]", text)

    # Add disclaimer if not already present
    if "투자자문" not in text:
        text += DISCLAIMER

    return text


def add_coverage_info(text: str, coverage: str = "full", confidence: float = 0.95) -> str:
    """Add coverage and confidence info to text."""
    badge = f"📊 데이터: coverage={coverage}, confidence={confidence:.0%}"
    return f"{badge}\n\n{text}"
