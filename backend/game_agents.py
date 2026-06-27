"""Rule-based and OpenAI-backed agents for diagnosis games."""
from __future__ import annotations

import json
from collections import Counter

from .compliance import sanitize_response
from .game_models import GameEvent, GameId, GameWiki, TraitSignal
from .openai_client import OpenAIConfigError, generate_text

TRAIT_LABELS = {
    "risk_tolerance": "위험 감수도",
    "diversification": "분산 선호",
    "behavior_bias": "행동 성향",
    "time_horizon": "단기/장기",
    "sector_tags": "선호 섹터",
    "stability_growth": "안정/공격성",
}

GAME_CATALOG: list[dict] = [
    {
        "game_id": "buy_sell",
        "name": "손절/존버 매매 반응 게임",
        "persona": "군중 트레이더",
        "mode": "hybrid",
        "estimated_minutes": 3,
        "description": "옆에서 부추기는 트레이더 군중의 자극에 매수, 매도, 관망 반응을 기록합니다.",
        "status": "available",
    },
    {
        "game_id": "balance",
        "name": "밸런스 선택 게임",
        "persona": "짓궂은 양자택일 진행자",
        "mode": "turn",
        "estimated_minutes": 2,
        "description": "양자택일 압박과 자유 답변으로 분산, 안정, 성장 성향을 읽습니다.",
        "status": "available",
    },
    {
        "game_id": "saju",
        "name": "투자 사주 도사 게임",
        "persona": "수염을 쓰다듬는 투자 도사",
        "mode": "turn",
        "estimated_minutes": 3,
        "description": "사주풍 은유 질문으로 자기 인식, 선호 섹터, 장기/단기 성향의 괴리를 관찰합니다.",
        "status": "available",
    },
]


def _sanitize_inline(text: str) -> str:
    """Apply prohibited-expression cleanup without adding a long footer."""
    return sanitize_response(text).split("\n\n---", 1)[0].strip()

GM_SYSTEM_PROMPT = """당신은 LUX-RU의 투자 성향 진단 게임 진행자입니다.
규칙:
- 한국어로 한두 문장만 답합니다.
- 실제 매수/매도 권유가 아니라 가상 시뮬레이션 진행 멘트로만 말합니다.
- 사용자의 행동, 반응 시간, 현재 게임 맥락에만 근거합니다.
- 단정적 수익 예측, 원금 보장, 특정 종목 권유 표현은 쓰지 않습니다.
"""

CONVERSATION_SYSTEM_PROMPT = """당신은 LUX-RU의 대화형 투자 성향 진단 게임 진행자입니다.
사용자의 자유 입력을 읽고 다음 턴으로 자연스럽게 이어가세요.
규칙:
- 한국어로 2문장 이내로 답합니다.
- 첫 문장은 사용자의 선택을 짧게 반영합니다.
- 마지막 문장은 다음 판단을 유도하는 질문이어야 합니다.
- 직전 대화에서 이미 물은 질문이나 같은 선택지를 반복하지 않습니다.
- 특히 밸런스 게임에서는 "안정성, 수익성, 분산 중 무엇" 같은 기준 질문을 반복하지 말고, 사용자가 답한 기준을 급락장, 급등장, 목표 비중, 뉴스 확인 같은 새 상황에 적용하게 만듭니다.
- 제공된 persona를 말투에 반영하되 과장하지 않습니다.
- 실제 투자 권유, 수익 예측, 원금 보장, 특정 종목 매수/매도 지시는 금지합니다.
- 가상 시뮬레이션과 성향 관찰 맥락으로만 말합니다.
"""

WIKI_SYSTEM_PROMPT = """당신은 LUX-RU의 게임 위키 작성 에이전트입니다.
게임 로그를 읽고 표준 마크다운 위키를 작성하세요.
반드시 포함할 섹션:
## [게임명] 성향 위키
### 게임 요약
### 관찰된 핵심 행동
### 성향 지표
| 지표 | 점수(-5~+5) | 근거 |
### 인상적 순간
### 리밸런싱 반영 신호
규칙:
- 제공된 로그 밖의 숫자를 만들지 않습니다.
- 6개 공통 지표(위험 감수도, 분산 선호, 행동 성향, 단기/장기, 선호 섹터, 안정/공격성)를 모두 다룹니다.
- 실제 매수/매도 권유를 하지 않습니다.
- 조정안은 예시 또는 검토 포인트로 표현합니다.
"""


def game_meta(game_id: GameId) -> dict:
    return next((game for game in GAME_CATALOG if game["game_id"] == game_id), {
        "game_id": game_id,
        "name": str(game_id),
        "persona": "진단 진행자",
        "mode": "turn",
    })


def start_message(game_id: GameId) -> str:
    if game_id == "buy_sell":
        return "군중 트레이더들이 술렁입니다. 가격이 흔들릴 때 매수, 매도, 관망 중 무엇이 먼저 튀어나오는지 보겠습니다."
    if game_id == "balance":
        return "밸런스 진행자가 양자택일을 들이밉니다. 오래 설명하기보다 먼저 끌리는 쪽을 고르고 이유를 말해 주세요."
    if game_id == "saju":
        return "투자 사주 도사가 판을 펼쳤습니다. 당신이 스스로 믿는 투자 기질과 실제 반응이 같은지 보겠습니다."
    return "진단 게임을 시작합니다. 모든 결과는 투자 권유가 아닌 성향 분석 시뮬레이션입니다."


def fallback_gm_message(game_id: GameId, action: str | None, context: dict | None = None) -> str:
    context = context or {}
    price_change = float(context.get("price_change_pct") or 0)
    elapsed = int(context.get("elapsed_ms") or 0)

    if game_id == "buy_sell":
        if action == "SELL" and price_change < 0:
            return "손실 구간에서 빠르게 청산했습니다. 이 반응은 손실 확정 회피보다 방어 규칙 쪽에 가까운 신호입니다."
        if action == "HOLD" and price_change < -5:
            return "급락 구간에서 버티는 선택입니다. 존버인지 원칙 보유인지 반응 시간을 함께 보겠습니다."
        if action == "BUY" and price_change > 4:
            return "상승 구간에서 진입했습니다. 추격 반응인지 계획된 진입인지 다음 행동으로 확인하겠습니다."
        if elapsed > 5000:
            return "결정 시간이 길어지고 있습니다. 관망이 전략인지 의사결정 지연인지 로그에 남기겠습니다."
        return "현재 선택을 기록했습니다. 다음 가격 변화에서 반응 패턴을 이어서 보겠습니다."

    if game_id == "balance":
        if elapsed > 4000:
            return "선택까지 시간이 걸렸습니다. 두 가치 사이의 우선순위 충돌이 있는 신호로 기록하겠습니다."
        return "선택을 기록했습니다. 같은 방향의 선택이 반복되는지 이어서 보겠습니다."

    if game_id == "saju":
        if action and any(key in str(action) for key in ("기술", "AI", "반도체")):
            return "도사의 수염이 반짝입니다. 성장 서사에 끌리는 기질이 보이지만 흔들릴 때의 손놀림도 함께 봐야겠습니다."
        if action and any(key in str(action) for key in ("배당", "현금", "채권", "안정")):
            return "안정의 기운을 먼저 잡는군요. 겉으로는 차분하지만 급한 장세에서 같은 선택을 하는지 보겠습니다."
        return "괘는 아직 흐릿합니다. 스스로 믿는 투자 성향과 실제 선택이 같은지 한 번 더 묻겠습니다."

    return "행동을 기록했습니다. 게임 종료 후 표준 위키로 정리하겠습니다."


def _keyword_in(text: str, keywords: tuple[str, ...]) -> bool:
    normalized = text.lower().replace(" ", "")
    return any(keyword in normalized for keyword in keywords)


def _balance_followup(message: str, context: dict | None = None) -> str:
    """Progress balance-game conversation instead of repeating the same axis question."""
    context = context or {}
    text = message.strip()
    round_no = int(context.get("round") or 1)
    last_turn = context.get("last_turn") or {}
    last_text = f"{last_turn.get('userMessage', '')} {last_turn.get('reply', '')}"

    if _keyword_in(text, ("안정", "손실", "방어", "잠", "변동성완화")):
        return (
            "안정성을 앞세운 건 손실 구간에서 심리적 안전판을 먼저 둔다는 신호입니다. "
            "그럼 급락장에서 목표 비중까지 기계적으로 조정할지, 뉴스를 더 확인하고 미룰지 둘 중 하나만 고르세요."
        )
    if _keyword_in(text, ("수익", "성장", "기회", "빠른", "시세", "공격")):
        return (
            "수익성을 앞세운 건 기회 포착 욕구가 강하다는 뜻입니다. "
            "확신 종목이 단기 급락하면 비중을 줄일 건가요, 아니면 원래 논리가 유지되는 한 버틸 건가요?"
        )
    if _keyword_in(text, ("분산", "etf", "여러", "나누", "비중")):
        return (
            "분산을 고른 건 한 번의 확신보다 흔들림을 줄이는 구조를 더 믿는다는 신호입니다. "
            "대신 강한 상승장에서 단일 종목보다 덜 오를 때도 그 규칙을 유지할 수 있나요?"
        )
    if _keyword_in(text, ("뉴스", "확인", "나중", "고민", "유보", "미루")):
        return (
            "정보를 더 확인하려는 태도는 신중하지만, 때로는 결정 지연으로 바뀔 수 있습니다. "
            "그럼 사전에 정한 리밸런싱 규칙이 있으면 그대로 실행할지, 그래도 한 번 더 미룰지 골라보세요."
        )
    if round_no >= 3 or _keyword_in(last_text, ("급락장", "목표비중", "뉴스")):
        return (
            "좋습니다, 이제 기준 자체보다 실행 방식을 보겠습니다. "
            "실제 포트폴리오에서 과집중 자산을 줄이는 규칙을 받아들일 수 있나요, 아니면 핵심 종목은 끝까지 남겨야 하나요?"
        )
    return (
        "그 기준은 기록했습니다. "
        "이제 실제 장면으로 바꿔서, 급락장에서 바로 규칙을 실행할지 아니면 정보를 더 보고 미룰지 선택해 보세요."
    )


def infer_conversation_action(game_id: GameId, message: str, context: dict | None = None) -> tuple[str, TraitSignal]:
    """Infer a coarse game action and trait signal from free-form text."""
    context = context or {}
    price_change = float(context.get("price_change_pct") or 0)
    text = message.strip()

    if game_id == "buy_sell":
        if _keyword_in(text, ("매수", "추매", "더살", "산다", "진입", "담아", "buy")):
            action = "BUY"
        elif _keyword_in(text, ("매도", "팔", "손절", "정리", "청산", "sell")):
            action = "SELL"
        elif _keyword_in(text, ("관망", "기다", "존버", "보유", "유지", "hold")):
            action = "HOLD"
        else:
            action = "CHAT"

        if action == "SELL" and price_change < 0:
            return action, TraitSignal(risk_tolerance=-3, behavior_bias=-1, time_horizon=3, stability_growth=-2)
        if action == "HOLD" and price_change < -5:
            return action, TraitSignal(risk_tolerance=2, behavior_bias=3, time_horizon=-1, stability_growth=2)
        if action == "BUY" and price_change > 4:
            return action, TraitSignal(risk_tolerance=3, behavior_bias=3, time_horizon=4, stability_growth=4)
        if action == "BUY":
            return action, TraitSignal(risk_tolerance=2, behavior_bias=1, stability_growth=2)
        if action == "SELL":
            return action, TraitSignal(risk_tolerance=-2, time_horizon=2, stability_growth=-1)
        if action == "HOLD":
            return action, TraitSignal(diversification=-1, behavior_bias=1, time_horizon=-2)
        return action, TraitSignal(behavior_bias=1)

    if game_id == "saju":
        sector_tags: list[str] = []
        if _keyword_in(text, ("기술", "ai", "반도체", "나스닥", "성장")):
            sector_tags.append("기술/성장")
        if _keyword_in(text, ("배당", "금융", "현금", "채권", "방어")):
            sector_tags.append("배당/방어")
        if _keyword_in(text, ("헬스", "바이오", "제약")):
            sector_tags.append("헬스케어")
        if _keyword_in(text, ("장기", "느긋", "버핏", "가치")):
            return text or "SAJU", TraitSignal(
                risk_tolerance=-1,
                diversification=-1,
                behavior_bias=-2,
                time_horizon=-4,
                stability_growth=-1,
                sector_tags=sector_tags,
            )
        if _keyword_in(text, ("단기", "빠른", "불나방", "급등", "추격", "한방")):
            return text or "SAJU", TraitSignal(
                risk_tolerance=3,
                diversification=2,
                behavior_bias=4,
                time_horizon=4,
                stability_growth=3,
                sector_tags=sector_tags,
            )
        return text or "SAJU", TraitSignal(behavior_bias=1, sector_tags=sector_tags)

    if _keyword_in(text, ("분산", "etf", "안정", "장기", "규칙", "기계")):
        return text, TraitSignal(diversification=-3, stability_growth=-2, risk_tolerance=-1, time_horizon=-2)
    if _keyword_in(text, ("단일", "확신", "성장", "기회", "빠른", "수익")):
        return text, TraitSignal(diversification=3, stability_growth=3, risk_tolerance=2, time_horizon=2)
    if _keyword_in(text, ("뉴스", "나중", "고민", "확인")):
        return text, TraitSignal(behavior_bias=3, time_horizon=2)
    return text or "CHAT", TraitSignal(behavior_bias=1)


def generate_gm_message(game_id: GameId, action: str | None, context: dict | None = None) -> tuple[str, str]:
    fallback = fallback_gm_message(game_id, action, context)
    user_payload = {
        "game_id": game_id,
        "action": action,
        "context": context or {},
        "fallback_style": fallback,
    }
    try:
        text = generate_text(
            system=GM_SYSTEM_PROMPT,
            user=json.dumps(user_payload, ensure_ascii=False),
            fast=True,
            max_output_tokens=180,
        )
        return _sanitize_inline(text), "openai"
    except (OpenAIConfigError, Exception):
        return fallback, "rule_pool"


def generate_conversation_reply(
    game_id: GameId,
    message: str,
    action: str,
    context: dict | None = None,
) -> tuple[str, str]:
    context = context or {}
    fallback = fallback_gm_message(game_id, action, context)
    if game_id == "buy_sell":
        fallback = f"{fallback} 같은 상황이 한 번 더 온다면 같은 결정을 반복하시겠습니까?"
    elif game_id == "balance":
        fallback = _balance_followup(message, context)
    elif game_id == "saju":
        fallback = f"{fallback} 스스로는 장기 가치투자형이라고 보십니까, 아니면 기회가 보이면 바로 움직이는 쪽입니까?"

    user_payload = {
        "game": game_meta(game_id),
        "game_id": game_id,
        "user_message": message,
        "inferred_action": action,
        "context": context,
        "fallback_style": fallback,
    }
    try:
        text = generate_text(
            system=CONVERSATION_SYSTEM_PROMPT,
            user=json.dumps(user_payload, ensure_ascii=False),
            fast=True,
            max_output_tokens=220,
        )
        cleaned = _sanitize_inline(text)
        if game_id == "balance" and all(word in cleaned for word in ("안정성", "수익성", "분산")):
            return fallback, "rule_pool"
        return cleaned, "openai"
    except (OpenAIConfigError, Exception):
        return fallback, "rule_pool"


def _clamp_score(value: int) -> int:
    return max(-5, min(5, int(value)))


def aggregate_trait_signal(events: list[GameEvent]) -> TraitSignal:
    totals = {
        "risk_tolerance": 0,
        "diversification": 0,
        "behavior_bias": 0,
        "time_horizon": 0,
        "stability_growth": 0,
    }
    sector_tags: list[str] = []
    for event in events:
        sig = event.signal
        totals["risk_tolerance"] += sig.risk_tolerance
        totals["diversification"] += sig.diversification
        totals["behavior_bias"] += sig.behavior_bias
        totals["time_horizon"] += sig.time_horizon
        totals["stability_growth"] += sig.stability_growth
        sector_tags.extend(sig.sector_tags)

    return TraitSignal(
        risk_tolerance=_clamp_score(round(totals["risk_tolerance"] / max(len(events), 1))),
        diversification=_clamp_score(round(totals["diversification"] / max(len(events), 1))),
        behavior_bias=_clamp_score(round(totals["behavior_bias"] / max(len(events), 1))),
        time_horizon=_clamp_score(round(totals["time_horizon"] / max(len(events), 1))),
        stability_growth=_clamp_score(round(totals["stability_growth"] / max(len(events), 1))),
        sector_tags=[tag for tag, _ in Counter(sector_tags).most_common(5)],
    )


def _fallback_wiki(game_id: GameId, events: list[GameEvent], trait_summary: TraitSignal) -> str:
    game_name = next((g["name"] for g in GAME_CATALOG if g["game_id"] == game_id), str(game_id))
    actions = Counter(event.action or event.event_type for event in events)
    notable = max(events, key=lambda event: event.reaction_latency_ms or 0, default=None)
    action_summary = ", ".join(f"{key} {count}회" for key, count in actions.most_common(6)) or "기록 없음"
    notable_text = (
        f"{notable.turn}턴: {notable.context or notable.action or notable.event_type}"
        if notable else "아직 뚜렷한 하이라이트가 없습니다."
    )
    rows = [
        ("위험 감수도", trait_summary.risk_tolerance, "게임 행동 로그의 위험 선택 신호 평균"),
        ("분산 선호", trait_summary.diversification, "선택지와 행동 로그의 분산/집중 신호 평균"),
        ("행동 성향", trait_summary.behavior_bias, "군중 자극, 관망, 충동 반응 신호 평균"),
        ("단기/장기", trait_summary.time_horizon, "반응 시간과 매매/선택 속도 신호 평균"),
        ("선호 섹터", 0, ", ".join(trait_summary.sector_tags) or "게임 내 명시적 섹터 선호 신호 없음"),
        ("안정/공격성", trait_summary.stability_growth, "안정 선호와 성장 추구 신호 평균"),
    ]
    table = "\n".join(f"| {label} | {score} | {basis} |" for label, score, basis in rows)
    return f"""## [{game_name}] 성향 위키

### 게임 요약
- 총 이벤트 {len(events)}건
- 주요 행동: {action_summary}

### 관찰된 핵심 행동
- 행동 로그를 기준으로 반응 속도, 선택 방향, 반복 행동을 기록했습니다.
- OpenAI API가 설정되지 않았거나 호출이 실패한 경우라 규칙 기반 위키를 생성했습니다.

### 성향 지표
| 지표 | 점수(-5~+5) | 근거 |
| --- | ---: | --- |
{table}

### 인상적 순간
- {notable_text}

### 리밸런싱 반영 신호
- 이 결과는 실제 매수/매도 지시가 아니라 현재 포트폴리오의 집중도와 함께 검토할 성향 신호입니다.
"""


def generate_game_wiki(session_id: str, game_id: GameId, events: list[GameEvent]) -> GameWiki:
    trait_summary = aggregate_trait_signal(events)
    fallback = _fallback_wiki(game_id, events, trait_summary)
    payload = {
        "game": game_meta(game_id),
        "game_id": game_id,
        "events": [event.model_dump(mode="json") for event in events],
        "trait_summary": trait_summary.model_dump(mode="json"),
    }
    markdown = fallback
    try:
        generated = generate_text(
            system=WIKI_SYSTEM_PROMPT,
            user=json.dumps(payload, ensure_ascii=False),
            fast=False,
            max_output_tokens=1400,
        )
        if "### 성향 지표" in generated and "### 리밸런싱 반영 신호" in generated:
            markdown = generated
    except (OpenAIConfigError, Exception):
        markdown = fallback

    return GameWiki(
        session_id=session_id,
        game_id=game_id,
        title=f"[{game_meta(game_id)['name']}] 성향 위키",
        markdown=sanitize_response(markdown),
        trait_summary=trait_summary,
        evidence_count=len(events),
    )
