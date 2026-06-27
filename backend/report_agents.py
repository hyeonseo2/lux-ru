"""Synthesis report generation for interactive diagnosis games."""
from __future__ import annotations

import json

from .compliance import sanitize_response
from .game_models import GameWiki, SynthesisReport
from .openai_client import OpenAIConfigError, generate_text

SYNTHESIS_SYSTEM_PROMPT = """당신은 LUX-RU의 종합 리밸런싱 리포트 작성 에이전트입니다.
입력으로 제공된 게임 위키와 포트폴리오 분석 요약만 사용하세요.
원시 게임 로그가 아니라 위키에 정리된 근거만 읽습니다.
실제 매수/매도 권유를 하지 말고, 조정안 예시와 검토 포인트로 표현하세요.
한국어 마크다운으로 작성하고 다음 섹션을 포함하세요:
## 종합 리밸런싱 리포트
### 핵심 진단
### 포트폴리오 X-Ray 요약
### 행동 성향 요약
### 자기 인식과 실제 행동의 괴리
### 성향과 포트폴리오의 충돌
### 조정안 예시
### 유의사항
규칙:
- 게임별 원시 로그를 요구하지 말고 제공된 위키만 종합합니다.
- 각 위키의 인상적 순간과 성향 지표를 근거로 사용합니다.
- 워런 버핏형, 불나방형 같은 유형화는 비유로만 사용하고 단정하지 않습니다.
"""


def _fallback_report(session_id: str, wikis: list[GameWiki], portfolio_analysis: dict | None) -> str:
    total = portfolio_analysis.get("total_value") if isinstance(portfolio_analysis, dict) else 0
    hhi = portfolio_analysis.get("hhi") if isinstance(portfolio_analysis, dict) else 0
    max_exp = portfolio_analysis.get("max_exposure") if isinstance(portfolio_analysis, dict) else None
    wiki_lines = "\n".join(f"- {wiki.title}: 근거 이벤트 {wiki.evidence_count}건" for wiki in wikis)
    top_name = max_exp.get("name") if isinstance(max_exp, dict) else "확인 필요"
    top_pct = max_exp.get("pct") if isinstance(max_exp, dict) else None
    top_text = f"{top_name} {top_pct:.1f}%" if isinstance(top_pct, (int, float)) else top_name

    return f"""## 종합 리밸런싱 리포트

### 핵심 진단
게임 위키 {len(wikis)}개와 포트폴리오 X-Ray 결과를 바탕으로 성향과 보유 구조의 충돌 여부를 점검했습니다.

### 포트폴리오 X-Ray 요약
- 총 평가액: {int(total or 0):,}원
- 집중도 HHI: {hhi}
- 최대 실질 노출: {top_text}

### 행동 성향 요약
{wiki_lines or "- 아직 생성된 게임 위키가 없습니다."}

### 자기 인식과 실제 행동의 괴리
게임 위키가 늘어나면 스스로 믿는 투자 스타일과 실제 선택 로그의 차이를 비교해 볼 수 있습니다.

### 성향과 포트폴리오의 충돌
게임에서 방어적 또는 충동적 반응이 확인된 경우, 단일 종목 또는 단일 섹터 과집중은 체감 변동성을 키울 수 있습니다.

### 조정안 예시
- 최대 실질 노출 비중을 먼저 확인하고 목표 상한을 정합니다.
- 신규 매매보다 기존 집중 노출을 줄이는 분산 규칙을 우선 검토합니다.
- 게임에서 드러난 지연, 추격, 관망 패턴을 실행 규칙으로 보완합니다.

### 유의사항
이 리포트는 정보제공 및 시뮬레이션이며 투자자문이 아닙니다.
"""


def generate_synthesis_report(
    *,
    session_id: str,
    wikis: list[GameWiki],
    portfolio_analysis: dict | None,
) -> SynthesisReport:
    fallback = _fallback_report(session_id, wikis, portfolio_analysis)
    payload = {
        "portfolio_analysis": portfolio_analysis or {},
        "game_wikis": [wiki.model_dump(mode="json") for wiki in wikis],
    }
    markdown = fallback
    try:
        generated = generate_text(
            system=SYNTHESIS_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            fast=False,
            max_output_tokens=1800,
        )
        if "## 종합 리밸런싱 리포트" in generated:
            markdown = generated
    except (OpenAIConfigError, Exception):
        markdown = fallback

    return SynthesisReport(
        session_id=session_id,
        markdown=sanitize_response(markdown),
        source_game_ids=[wiki.game_id for wiki in wikis],
    )
