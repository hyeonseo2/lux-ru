"""AI Chat module using OpenAI API.

Implements intent classification and portfolio Q&A with compliance guards.
"""
from __future__ import annotations

import logging
from typing import AsyncGenerator

from .compliance import sanitize_response, DISCLAIMER_SHORT
from .openai_client import OpenAIConfigError, generate_text

logger = logging.getLogger(__name__)

# ── Intent Classification ─────────────────────────────────────

INTENT_SYSTEM = """당신은 한국형 LUX-RU 서비스의 질문 분류기입니다.
사용자 질문을 다음 intent 중 하나로 분류하세요:
- portfolio_xray: 특정 종목의 실제 노출, 비중, 보유 내역 질문
- overlap: ETF 간 중복도, 겹치는 종목 질문
- sector_country: 섹터, 국가, 통화 노출 질문
- cash_product: 예금, 적금, 연금저축 추천 질문
- explanation: 서비스 사용법, 일반 설명 질문
- unknown: 분류 불가

JSON 형식으로만 답하세요: {"intent": "..."}"""


ANSWER_SYSTEM = """당신은 한국형 LUX-RU 서비스의 설명 에이전트입니다.

규칙:
1. 모든 수치는 제공된 분석 결과(tool_result) 안의 값만 사용합니다. 임의로 계산하거나 추정하지 않습니다.
2. ETF 보유내역에는 coverage와 confidence를 반드시 명시합니다.
3. "이 종목을 사세요/파세요" 같은 단정·권유 표현을 절대 쓰지 않습니다.
4. 모든 매매 관련 답변은 "시뮬레이션" 또는 "조정안 예시"로 표현합니다.
5. 사용자 질문이 모호하면 짧게 한 가지 질문으로 명확히 합니다.
6. 한국어로 자연스럽게 답합니다.
7. 금액은 원화(₩) 단위로, 비중은 %로 표시합니다.
8. 답변 마지막에 반드시 다음 문구를 포함합니다:
   "본 정보는 정보제공 및 시뮬레이션이며 투자자문이 아닙니다."
"""


async def generate_ai_response(
    question: str,
    analysis_context: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Generate AI response using OpenAI API with a rule-based fallback."""

    try:
        # Build context from analysis
        context_str = _build_context_string(analysis_context) if analysis_context else "분석 데이터가 없습니다. 먼저 CSV를 업로드하고 분석을 실행해주세요."

        prompt = f"""## 포트폴리오 분석 결과 (tool_result)
{context_str}

## 사용자 질문
{question}

위 분석 결과만을 사용하여 질문에 답해주세요."""

        full_text = generate_text(
            system=ANSWER_SYSTEM,
            user=prompt,
            fast=False,
            max_output_tokens=1400,
        )
        yield sanitize_response(full_text)

    except OpenAIConfigError:
        yield "⚠️ AI 기능을 사용하려면 OPENAI_API_KEY와 OPENAI_MODEL 환경변수를 설정해주세요.\n\n"
        yield _generate_fallback_response(question, analysis_context)
    except Exception as e:
        logger.error("OpenAI API error: %s", e)
        yield f"⚠️ AI 응답 생성 중 오류가 발생했습니다.\n\n"
        yield sanitize_response(_generate_fallback_response(question, analysis_context))


def _build_context_string(analysis: dict) -> str:
    """Build context string from analysis results."""
    parts = []

    # Exposure summary
    if "exposure" in analysis:
        exp = analysis["exposure"]
        parts.append(f"### 포트폴리오 총 평가금액: ₩{exp.get('total_market_value', 0):,.0f}")
        parts.append(f"기준일: {exp.get('as_of_date', 'N/A')}")
        parts.append(f"데이터 신뢰등급: {exp.get('data_grade', 'N/A')}")

        # Top holdings
        if "top_holdings" in exp:
            parts.append("\n### 실제 종목 노출 Top 10:")
            for i, h in enumerate(exp["top_holdings"][:10], 1):
                name = h.get("instrument_name", "Unknown")
                amount = h.get("exposure_amount", 0)
                weight = h.get("exposure_weight", 0)
                conf = h.get("confidence", 0)
                cov = h.get("coverage_min", "unknown")
                parts.append(
                    f"{i}. {name}: ₩{float(amount):,.0f} ({float(weight)*100:.2f}%) "
                    f"[coverage: {cov}, confidence: {float(conf):.0%}]"
                )

        # Sector
        if "by_sector" in exp:
            parts.append("\n### 섹터별 노출:")
            for sector, weight in sorted(exp["by_sector"].items(), key=lambda x: x[1], reverse=True):
                parts.append(f"- {sector}: {weight*100:.1f}%")

        # Country
        if "by_country" in exp:
            parts.append("\n### 국가별 노출:")
            for country, weight in sorted(exp["by_country"].items(), key=lambda x: x[1], reverse=True):
                parts.append(f"- {country}: {weight*100:.1f}%")

    # Overlaps
    if "overlaps" in analysis and analysis["overlaps"]:
        parts.append("\n### ETF 중복 분석:")
        for ov in analysis["overlaps"][:5]:
            parts.append(
                f"- {ov['etf_a_name']} ↔ {ov['etf_b_name']}: "
                f"중복도 {ov['overlap_score']*100:.1f}%, "
                f"공통종목 {ov['common_count']}개"
            )

    # FinLife
    if "finlife_recommendations" in analysis and analysis["finlife_recommendations"]:
        parts.append("\n### FinLife 예적금 추천:")
        for fl in analysis["finlife_recommendations"][:3]:
            parts.append(
                f"- {fl['company']} {fl['product_name']}: "
                f"기본 {fl['base_rate']}% / 최대 {fl['max_rate']}%"
            )

    return "\n".join(parts)


def _generate_fallback_response(question: str, analysis: dict | None) -> str:
    """Generate a rule-based fallback response when AI is unavailable."""
    q_lower = question.lower()

    if analysis and "exposure" in analysis:
        exp = analysis["exposure"]

        # Check for specific stock questions
        for keyword in ["엔비디아", "nvidia", "nvda"]:
            if keyword in q_lower:
                for h in exp.get("top_holdings", []):
                    if "엔비디아" in h.get("instrument_name", "").lower() or \
                       "nvidia" in h.get("instrument_name", "").lower():
                        amount = float(h.get("exposure_amount", 0))
                        weight = float(h.get("exposure_weight", 0))
                        return (
                            f"포트폴리오 전체 기준 엔비디아(NVIDIA) 실제 노출은 "
                            f"약 ₩{amount:,.0f} ({weight*100:.2f}%)입니다.\n\n"
                            f"{DISCLAIMER_SHORT}"
                        )

        # General question
        total = float(exp.get("total_market_value", 0))
        top = exp.get("top_holdings", [])[:5]
        holdings_str = "\n".join(
            f"  {i+1}. {h.get('instrument_name', '?')}: "
            f"₩{float(h.get('exposure_amount', 0)):,.0f} "
            f"({float(h.get('exposure_weight', 0))*100:.2f}%)"
            for i, h in enumerate(top)
        )
        return (
            f"포트폴리오 총 평가금액은 ₩{total:,.0f}이며, "
            f"실제 종목 노출 Top 5는 다음과 같습니다:\n{holdings_str}\n\n"
            f"{DISCLAIMER_SHORT}"
        )

    return f"분석 데이터가 없습니다. 먼저 CSV를 업로드하고 LUX-RU 분석을 실행해주세요.\n\n{DISCLAIMER_SHORT}"
