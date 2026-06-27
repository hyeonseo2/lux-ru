# LUX-RU 대화형 AI 진단 게임 구현 기획서

## 1. 목적

현재 LUX-RU는 두 개의 사용자 진입점을 가진다.

1. 기존 LUX-RU 룩스루 분석 서비스
2. 진단-검사-솔루션 4단계 데모 서비스

이번 추가 개발은 시작화면에 세 번째 진입점인 `대화형 AI 진단 게임`을 추가하고, 회의록 기반 추가개발 요건서의 핵심 구조인 `게임 GM 에이전트 -> 구조화 로그 -> 게임별 위키 -> 종합 리포트` 파이프라인을 구현하는 것이다.

목표는 기존 룩스루 분석 엔진을 유지하면서, 사용자의 실제 행동 반응을 투자 성향 진단 데이터로 수집하고, OpenAI API가 이를 표준 위키와 최종 리밸런싱 리포트로 변환하는 신규 경험을 제공하는 것이다.

## 2. 제품 포지셔닝

### 2.1 시작화면 서비스 3분할

시작화면은 다음 3개 카드로 구성한다.

1. `LUX-RU 오리지널`
   - 기존 네트워크 그래프, 대시보드, 챗 중심의 룩스루 분석 서비스
   - 라우트: `/original`

2. `진단-솔루션 위저드`
   - 현재 `LUX-RU_demo.html` 기반 4단계 데모
   - 포트폴리오 입력, 룩스루 분석, 성향 검사, 리밸런싱 솔루션
   - 라우트: `/diagnosis-solution`, `/demo`

3. `대화형 AI 진단 게임`
   - 이번 신규 기획 반영 영역
   - 게임형 행동 진단, GM 반응, 로그 타임라인, 게임 위키, 종합 리포트
   - 신규 라우트: `/interactive-diagnosis`

### 2.2 세 번째 서비스의 핵심 가치

기존 성향 검사는 사용자가 직접 답하는 설문 중심이다. 신규 서비스는 사용자의 선택, 반응 시간, 매수/매도 타이밍, AI 자극에 대한 반응을 행동 로그로 기록한다.

이를 통해 다음 인사이트를 만든다.

- 사용자가 말하는 투자 성향과 실제 행동의 차이
- 급락, 군중 자극, 기회비용 압박 등 상황별 의사결정 패턴
- 현재 포트폴리오의 실제 노출과 행동 성향의 충돌 여부
- 성향 근거가 추적 가능한 리밸런싱 리포트

## 3. 현재 코드 자산과 활용 방안

### 3.1 재사용할 자산

- FastAPI 엔트리포인트: `main.py`
- 룩스루 분석 API: `backend/routers/portfolio.py`
- 실시간 입력 분석 엔진: `backend/live_data.py`
- 기존 AI 챗 모듈: `backend/ai_chat.py`
- 컴플라이언스 필터: `backend/compliance.py`
- 백테스트/벤치마크 비교: `backend/historical.py`
- 4단계 위저드 UI와 게임 프로토타입: `LUX-RU_demo.html`

### 3.2 보강이 필요한 영역

- 게임 이벤트 공통 스키마
- 세션별 게임 로그 저장소
- 게임별 GM 에이전트 응답 API
- 게임별 위키 생성 API
- 종합 리포트 생성 API
- OpenAI API 공통 클라이언트
- 기존 Gemini 기반 챗 모듈의 OpenAI API 전환
- 시작화면 세 번째 카드와 신규 라우트
- 신규 대화형 게임 전용 프론트 페이지
- 영속 저장이 필요한 경우 DB 테이블 및 마이그레이션

### 3.3 LLM Provider 결정

신규 대화형 진단 게임의 LLM 호출은 Gemini가 아니라 OpenAI API로 통일한다.

구현 원칙:

- 환경변수는 `OPENAI_API_KEY`를 사용한다.
- 모델명은 코드에 고정하지 않고 `OPENAI_MODEL`, `OPENAI_FAST_MODEL`로 분리한다.
- 긴 위키/종합 리포트 생성은 `OPENAI_MODEL`을 사용한다.
- 게임 중 짧은 GM 멘트는 `OPENAI_FAST_MODEL`을 사용하거나 규칙 기반 멘트 풀로 대체한다.
- OpenAI API 호출부는 `backend/openai_client.py` 하나로 모은다.
- 기존 `GOOGLE_API_KEY`, `GEMINI_MODEL`, `google-generativeai` 의존성은 신규 기능에서 사용하지 않는다.
- `requirements.txt`에는 OpenAI Python SDK 의존성을 추가한다.
- `.env.example`에는 `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_FAST_MODEL` 예시를 추가한다.
- 기존 `backend/ai_chat.py`는 OpenAI API 기반으로 교체하거나, 새 `backend/openai_chat.py`로 이관한 뒤 라우터가 새 모듈을 보게 한다.

## 4. 목표 아키텍처

```text
사용자
  |
  v
시작화면
  |
  +-- /original
  +-- /diagnosis-solution
  +-- /interactive-diagnosis
          |
          v
   대화형 게임 UI
          |
          +-- 포트폴리오 X-Ray 분석 호출
          +-- 게임 이벤트 기록
          +-- GM 멘트 생성 또는 규칙 기반 멘트 선택
          +-- 게임 종료
          |
          v
   게임 로그 저장소
          |
          v
   게임별 위키 생성 에이전트
          |
          v
   표준 게임 위키들
          |
          +-- 포트폴리오 분석 결과
          +-- 백테스트/시장 데이터
          |
          v
   종합 에이전트
          |
          v
   최종 리밸런싱 리포트
```

핵심 원칙은 종합 에이전트가 원시 로그를 직접 읽지 않는 것이다. 각 게임의 원시 로그는 먼저 표준 위키로 정리되고, 종합 단계는 위키와 포트폴리오 분석 결과만 사용한다.

## 5. 기능 범위

### 5.1 MVP 범위

MVP는 빠르게 시연 가능한 수준을 목표로 한다.

- 시작화면 3번째 카드 추가
- `/interactive-diagnosis` 신규 페이지 추가
- 세션 생성 및 유지
- 포트폴리오 입력 또는 기존 샘플 포트폴리오 사용
- 게임 2종 우선 구현
  - 손절/존버 매매 반응 게임
  - 밸런스 선택 게임
- 공통 게임 이벤트 로그 저장
- 게임별 위키 생성
- 종합 리포트 생성
- 컴플라이언스 필터 적용

### 5.2 MVP 이후 확장 범위

- 사주/만세력 투자 리듬 게임 서버 연동
- 투자대가 상담형 대화 게임
- 행동재무 편향 진단 게임
- 게임 플러그인 레지스트리 정식화
- PostgreSQL 영속 저장
- 리포트 PDF/HTML 내보내기
- 게임별 A/B 프롬프트 실험
- 사용자의 자기 인식 입력과 실제 행동 로그의 괴리 분석

## 6. 사용자 흐름

### 6.1 진입

1. 사용자가 시작화면에서 `대화형 AI 진단 게임` 카드를 선택한다.
2. `/interactive-diagnosis` 페이지로 이동한다.
3. 신규 페이지는 다음 영역으로 구성된다.
   - 좌측: 게임 목록과 진행 상태
   - 중앙: 현재 게임 플레이 영역
   - 우측: 실시간 로그, 성향 점수, 생성된 위키

### 6.2 포트폴리오 연결

1. 사용자가 직접 종목과 금액을 입력하거나 샘플 포트폴리오를 선택한다.
2. 기존 `/api/portfolio/analyze_real`을 호출한다.
3. 결과를 세션에 저장한다.
4. 게임 질문과 리포트에서 포트폴리오의 최대 실질 노출, 섹터 쏠림, HHI를 활용한다.

### 6.3 게임 플레이

1. 사용자가 게임을 선택한다.
2. 게임 시작 이벤트가 서버에 기록된다.
3. 사용자 선택, 클릭, 매수/매도, 대기 시간, GM 멘트, 라운드 종료가 모두 공통 이벤트로 기록된다.
4. 빠른 반응이 필요한 게임은 규칙 기반 멘트 풀을 우선 사용하고, 핵심 장면에서만 OpenAI API를 호출한다.
5. 턴제 게임은 매 턴 OpenAI API 또는 규칙 기반 대체 응답을 사용할 수 있다.

### 6.4 위키 생성

1. 게임 종료 시 `POST /api/games/{game_id}/finish`를 호출한다.
2. 서버는 해당 게임 로그를 읽고 게임별 표준 위키를 생성한다.
3. 위키는 다음 섹션을 반드시 포함한다.
   - 게임 요약
   - 관찰된 핵심 행동
   - 6개 성향 지표 점수와 근거
   - 인상적 순간
   - 리밸런싱에 반영할 신호

### 6.5 종합 리포트

1. 사용자가 `종합 리포트 생성`을 누른다.
2. 서버는 게임 위키들, 포트폴리오 X-Ray 결과, 백테스트 결과를 모은다.
3. 종합 에이전트가 최종 리포트를 작성한다.
4. 컴플라이언스 필터를 거쳐 응답한다.

## 7. 데이터 모델

### 7.1 공통 성향 지표

모든 게임은 결과를 다음 6개 지표로 환산한다.

```python
TRAIT_KEYS = [
    "risk_tolerance",      # 위험 감수도
    "diversification",     # 분산 선호
    "behavior_bias",       # 행동 성향/편향
    "time_horizon",        # 단기/장기
    "sector_preference",   # 선호 섹터
    "stability_growth",    # 안정/공격성
]
```

점수 범위는 `-5`부터 `+5`까지로 통일한다.

- 음수: 방어적, 안정적, 회피적, 장기적, 분산 선호 쪽 신호
- 양수: 공격적, 집중적, 단기적, 추종적, 변동성 선호 쪽 신호
- 0: 중립 또는 근거 부족

`sector_preference`는 단일 숫자만으로 표현하기 어렵기 때문에 점수 외에 `sector_tags`를 별도로 둔다.

### 7.2 Pydantic 모델 초안

신규 파일 후보: `backend/game_models.py`

```python
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


GameId = Literal[
    "buy_sell",
    "balance",
    "risk",
    "bias",
    "master",
    "saju",
]


EventType = Literal[
    "game_start",
    "gm_message",
    "user_choice",
    "user_action",
    "hesitation",
    "round_start",
    "round_end",
    "game_end",
]


class TraitSignal(BaseModel):
    risk_tolerance: int = Field(default=0, ge=-5, le=5)
    diversification: int = Field(default=0, ge=-5, le=5)
    behavior_bias: int = Field(default=0, ge=-5, le=5)
    time_horizon: int = Field(default=0, ge=-5, le=5)
    stability_growth: int = Field(default=0, ge=-5, le=5)
    sector_tags: list[str] = Field(default_factory=list)


class GameEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    game_id: GameId
    turn: int = 0
    event_type: EventType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    action: str | None = None
    context: str = ""
    reaction_latency_ms: int | None = None
    signal: TraitSignal = Field(default_factory=TraitSignal)
    payload: dict[str, Any] = Field(default_factory=dict)


class GameWiki(BaseModel):
    session_id: str
    game_id: GameId
    title: str
    markdown: str
    trait_summary: TraitSignal
    evidence_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SynthesisReport(BaseModel):
    session_id: str
    markdown: str
    source_game_ids: list[GameId]
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 7.3 인메모리 저장소 초안

MVP에서는 현재 `_sessions` 구조와 유사하게 인메모리 저장소로 시작한다.

신규 파일 후보: `backend/game_store.py`

```python
_game_sessions = {
    session_id: {
        "portfolio_analysis": dict | None,
        "events": list[GameEvent],
        "wikis": dict[game_id, GameWiki],
        "synthesis_report": SynthesisReport | None,
    }
}
```

운영 또는 장기 데모에서는 PostgreSQL 테이블로 옮긴다.

### 7.4 DB 테이블 확장안

신규 SQLAlchemy 모델 후보: `backend/db_models.py`

- `GameEventDB`
  - `id`
  - `session_id`
  - `game_id`
  - `turn`
  - `event_type`
  - `action`
  - `context`
  - `reaction_latency_ms`
  - `signal_json`
  - `payload_json`
  - `created_at`

- `GameWikiDB`
  - `id`
  - `session_id`
  - `game_id`
  - `title`
  - `markdown`
  - `trait_summary_json`
  - `created_at`

- `SynthesisReportDB`
  - `id`
  - `session_id`
  - `markdown`
  - `source_game_ids_json`
  - `created_at`

## 8. API 설계

신규 라우터 후보: `backend/routers/games.py`

### 8.1 세션 초기화

```http
POST /api/games/session
```

요청:

```json
{
  "session_id": "optional-client-id",
  "positions": [
    {
      "ticker": "005930",
      "amount": 10000000,
      "account_type": "taxable"
    }
  ]
}
```

응답:

```json
{
  "success": true,
  "session_id": "luxru-game-abc123",
  "portfolio_analysis": {}
}
```

### 8.2 게임 목록 조회

```http
GET /api/games/catalog
```

응답:

```json
{
  "games": [
    {
      "game_id": "buy_sell",
      "name": "손절/존버 매매 반응 게임",
      "mode": "hybrid",
      "estimated_minutes": 3,
      "status": "available"
    }
  ]
}
```

### 8.3 게임 시작

```http
POST /api/games/{game_id}/start
```

요청:

```json
{
  "session_id": "luxru-game-abc123",
  "context": {
    "target_symbol": "NVDA"
  }
}
```

응답:

```json
{
  "success": true,
  "game_id": "buy_sell",
  "turn": 1,
  "gm_message": "가상 시뮬레이션입니다. 첫 라운드를 시작합니다.",
  "state": {}
}
```

### 8.4 이벤트 기록

```http
POST /api/games/{game_id}/events
```

요청:

```json
{
  "session_id": "luxru-game-abc123",
  "turn": 7,
  "event_type": "user_action",
  "action": "SELL",
  "context": "차트 -8% 급락 직후",
  "reaction_latency_ms": 1400,
  "signal": {
    "risk_tolerance": -2,
    "behavior_bias": 3,
    "time_horizon": 4
  },
  "payload": {
    "price_change_pct": -8.0,
    "round": 3
  }
}
```

응답:

```json
{
  "success": true,
  "event_id": "..."
}
```

### 8.5 GM 응답 생성

```http
POST /api/games/{game_id}/gm
```

요청:

```json
{
  "session_id": "luxru-game-abc123",
  "turn": 3,
  "last_action": "HOLD",
  "context": {
    "price_change_pct": -6.2,
    "elapsed_ms": 3200
  }
}
```

응답:

```json
{
  "success": true,
  "mode": "rule_pool",
  "message": "방금 급락 구간입니다. 계속 버틸지, 규칙대로 정리할지 선택해야 합니다."
}
```

### 8.6 게임 종료 및 위키 생성

```http
POST /api/games/{game_id}/finish
```

요청:

```json
{
  "session_id": "luxru-game-abc123"
}
```

응답:

```json
{
  "success": true,
  "wiki": {
    "game_id": "buy_sell",
    "title": "[손절/존버 게임] 성향 위키",
    "markdown": "## ...",
    "trait_summary": {}
  }
}
```

### 8.7 종합 리포트 생성

신규 라우터 후보: `backend/routers/reports.py`

```http
POST /api/reports/synthesis
```

요청:

```json
{
  "session_id": "luxru-game-abc123",
  "include_backtest": true
}
```

응답:

```json
{
  "success": true,
  "report": {
    "markdown": "## 종합 리밸런싱 리포트...",
    "source_game_ids": ["buy_sell", "balance"]
  }
}
```

## 9. OpenAI 에이전트 설계

신규 파일 후보:

- `backend/openai_client.py`
- `backend/game_agents.py`
- `backend/report_agents.py`

### 9.1 OpenAI API 공통 클라이언트

OpenAI 호출은 각 라우터나 에이전트에서 직접 하지 않고 `backend/openai_client.py`로 집중한다.

역할:

- `OPENAI_API_KEY` 로딩
- `OPENAI_MODEL`, `OPENAI_FAST_MODEL` 선택
- 공통 timeout, retry, logging 처리
- JSON 출력 파싱 헬퍼 제공
- API 키 미설정/호출 실패 시 fallback 경로 제공
- 컴플라이언스 필터 적용 전 원문과 적용 후 결과를 분리해 추적 가능하게 반환

초안:

```python
from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
OPENAI_FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", OPENAI_MODEL)


def get_openai_client() -> OpenAI | None:
    if not OPENAI_API_KEY:
        return None
    return OpenAI(api_key=OPENAI_API_KEY)


def generate_text(
    *,
    system: str,
    user: str,
    fast: bool = False,
    max_output_tokens: int = 1200,
) -> str:
    client = get_openai_client()
    model = OPENAI_FAST_MODEL if fast else OPENAI_MODEL
    if not client or not model:
        raise RuntimeError("OpenAI API is not configured.")

    response = client.responses.create(
        model=model,
        instructions=system,
        input=user,
        max_output_tokens=max_output_tokens,
    )
    return response.output_text
```

실제 구현에서는 예외를 라우터까지 그대로 노출하지 않고, 게임 진행이 끊기지 않도록 fallback 메시지 또는 규칙 기반 결과를 반환한다.

### 9.2 GM 에이전트

역할:

- 사용자의 현재 행동에 반응하는 짧은 멘트 생성
- 게임 페르소나 유지
- 투자 권유가 아닌 시뮬레이션 상황으로만 발화
- 빠른 게임에서는 규칙 기반 멘트 풀 우선

게임별 전략:

- `buy_sell`
  - 기본은 규칙 기반 멘트 풀
  - 급락, 연속 손실, 장시간 미결정 같은 핵심 장면에서만 OpenAI API 호출
  - 호출 모델은 `OPENAI_FAST_MODEL`을 사용

- `balance`, `risk`, `bias`
  - 턴제라 OpenAI API로 짧은 단발 생성 가능
  - MVP에서는 스트리밍보다 단발 응답을 우선한다.

- `saju`
  - 원문 개인정보를 저장하지 않고 파생 지표 기반 해석만 사용

### 9.3 위키 작성 에이전트

입력:

- 게임별 구조화 이벤트 목록
- 게임 메타데이터
- 누적 성향 신호

출력:

표준 마크다운 위키.

```markdown
## [게임명] 성향 위키

### 게임 요약

### 관찰된 핵심 행동

### 성향 지표

| 지표 | 점수(-5~+5) | 근거 |
| --- | ---: | --- |

### 인상적 순간

### 리밸런싱 반영 신호
```

OpenAI 호출 전략:

- 모델은 `OPENAI_MODEL`을 사용한다.
- 입력은 구조화 이벤트 전체를 넣되, 과도하게 긴 로그는 서버에서 요약 후 전달한다.
- 출력 포맷은 마크다운으로 제한한다.
- 후처리로 성향 지표 테이블이 누락되면 fallback 위키를 생성한다.
- 최종 반환 전 `sanitize_response()`를 적용한다.

### 9.4 종합 에이전트

입력:

- 게임별 위키
- 포트폴리오 X-Ray 분석 결과
- 백테스트/벤치마크 결과

금지:

- 원시 게임 로그 직접 참조
- 임의 수치 생성
- 단정적 매수/매도 권유

출력:

- 자기 인식과 실제 행동의 괴리
- 현재 포트폴리오 노출 리스크
- 성향에 맞는 리밸런싱 원칙
- 조정안 예시
- 백테스트 기반 근거
- 면책 문구

OpenAI 호출 전략:

- 모델은 `OPENAI_MODEL`을 사용한다.
- 원시 게임 로그는 절대 입력하지 않는다.
- 입력은 게임별 위키, 포트폴리오 분석 결과, 백테스트 요약으로 제한한다.
- 출력은 최종 사용자에게 바로 보여줄 마크다운으로 받는다.
- 컴플라이언스 필터를 적용한 결과만 API 응답으로 반환한다.

### 9.5 프롬프트 관리

프롬프트는 코드 문자열에 흩뿌리지 않고 `backend/prompts.py` 또는 `backend/prompts/`에 모은다.

권장 분리:

- `GM_SYSTEM_PROMPTS`
- `WIKI_SYSTEM_PROMPT`
- `SYNTHESIS_SYSTEM_PROMPT`
- `COMPLIANCE_SUFFIX`

프롬프트 공통 규칙:

- 한국어로 답한다.
- 투자 권유가 아니라 시뮬레이션 분석으로 표현한다.
- 제공된 로그와 분석 결과 밖의 수치를 만들지 않는다.
- 사용자의 행동 근거를 명시한다.
- 최종 리포트에는 투자자문이 아니라는 면책 문구를 포함한다.

## 10. 프론트엔드 설계

### 10.1 시작화면 수정

대상 파일:

- `static/landing.html`
- 관련 CSS가 분리되어 있다면 `static/css/style.css`

작업:

- 기존 2개 카드 레이아웃을 3개 카드로 확장
- 세 번째 카드 CTA를 `/interactive-diagnosis`로 연결
- 모바일에서 1열, 태블릿 이상에서 3열 배치

### 10.2 신규 페이지

신규 파일 후보:

- `static/interactive.html`
- `static/js/interactive.js`
- `static/css/interactive.css`

또는 초기 MVP에서는 단일 `LUX-RU_interactive.html`로 시작할 수 있다. 다만 장기적으로는 정적 파일 분리를 권장한다.

### 10.3 페이지 레이아웃

```text
+-------------------------------------------------------------+
| 상단: LUX-RU 대화형 AI 진단 게임 / 세션 상태 / 리포트 생성 |
+----------------------+----------------------+---------------+
| 게임 목록             | 게임 플레이 영역      | 로그/위키 패널 |
| - 포트폴리오 연결     | - GM 메시지           | - 이벤트 로그  |
| - 손절/존버           | - 선택 버튼/차트      | - 성향 점수    |
| - 밸런스 게임         | - 결과 카드           | - 게임 위키    |
| - 사주 분석           |                      | - 종합 리포트  |
+----------------------+----------------------+---------------+
```

### 10.4 클라이언트 상태

```javascript
const state = {
  sessionId: null,
  portfolioAnalysis: null,
  catalog: [],
  activeGameId: null,
  gameStates: {},
  events: [],
  wikis: {},
  synthesisReport: null
};
```

### 10.5 기존 데모 코드 이관

`LUX-RU_demo.html`의 다음 로직을 참고하되, 신규 페이지에서는 서버 이벤트 전송을 중심으로 재작성한다.

- 게임 목록: `AGENTS`
- 손절/존버 게임: `tradeGame`, `roundResults`
- 결과 분류: `classifyTradeResult`
- 리밸런싱 신호: `tradeRebalanceSignal`, `sajuRebalanceSignal`

## 11. 게임별 구현 계획

### 11.1 손절/존버 매매 반응 게임

우선 구현 대상.

수집 이벤트:

- 게임 시작
- 라운드 시작
- 가격 급등/급락 이벤트
- GM 멘트 노출
- 매수 클릭
- 매도 클릭
- 타임아웃
- 라운드 종료
- 게임 종료

주요 지표:

- 평균 보유 시간
- 매수하지 않은 라운드 수
- 자동 청산 수
- 최악 손익 구간 반응
- 수익/손실 구간 매도 속도
- 충동성
- 존버 편향
- 손절 규칙 실행력

서버 기록 예시:

```json
{
  "game_id": "buy_sell",
  "event_type": "user_action",
  "action": "SELL",
  "context": "라운드 3, 손익률 -6.4%, GM이 군중 자극 멘트 출력 후",
  "reaction_latency_ms": 1320,
  "signal": {
    "risk_tolerance": -2,
    "behavior_bias": 3,
    "time_horizon": 4,
    "stability_growth": -1
  }
}
```

### 11.2 밸런스 선택 게임

MVP 두 번째 구현 대상.

수집 이벤트:

- 질문 노출
- 선택지 선택
- 반응 시간
- 선택 전 변경/망설임
- GM 멘트

주요 지표:

- 분산 선호
- 단기/장기 성향
- 안정/공격성
- 집중 투자 선호

### 11.3 사주/만세력 투자 리듬 분석

MVP 이후 구현.

주의:

- 생년월일과 출생시간 원문 저장은 피한다.
- 서버에는 계산된 오행 분포, 십성 요약, 파생 성향 지표만 기록한다.
- UI에는 개인정보 처리 방침을 명확히 표시한다.

### 11.4 행동재무 편향 진단

MVP 이후 구현.

주요 지표:

- 손실회피
- 확증편향
- 군중심리
- 처분효과
- 과잉확신

## 12. 컴플라이언스 원칙

모든 OpenAI API 출력은 `backend/compliance.py`의 `sanitize_response()`를 통과해야 한다.

적용 대상:

- GM 멘트
- 게임 결과 설명
- 게임별 위키
- 종합 리포트

표현 원칙:

- `매수하세요`, `매도하세요`, `반드시`, `원금 보장`, `확실한 수익` 금지
- `가상 시뮬레이션`, `조정안 예시`, `검토 포인트`, `리밸런싱 원칙` 표현 사용
- 최종 리포트에는 면책 문구 포함

## 13. 테스트 계획

### 13.1 백엔드 단위 테스트

신규 테스트 파일 후보:

- `tests/test_game_models.py`
- `tests/test_game_store.py`
- `tests/test_game_wiki_pipeline.py`
- `tests/test_synthesis_report.py`

테스트 항목:

- `GameEvent` 스키마 검증
- 성향 점수 범위 검증
- 이벤트 저장 및 조회
- 게임 종료 시 위키 생성
- `OPENAI_API_KEY`가 없을 때 fallback 동작
- 컴플라이언스 필터 적용
- 종합 리포트가 원시 로그 없이 위키만 사용하는지 검증

### 13.2 API 테스트

테스트 항목:

- 세션 생성
- 게임 시작
- 이벤트 기록
- GM 응답
- 게임 종료
- 위키 조회
- 종합 리포트 생성

### 13.3 프론트 수동 QA

체크리스트:

- 시작화면 카드 3개가 데스크톱/모바일에서 깨지지 않는지
- `/interactive-diagnosis` 라우트 접근 가능 여부
- 게임 이벤트가 실시간 로그 패널에 표시되는지
- 게임 종료 후 위키가 생성되는지
- 종합 리포트가 생성되는지
- `OPENAI_API_KEY` 미설정 환경에서도 데모 진행이 가능한지

## 14. 구현 단계

### Phase 0. OpenAI API 호출 계층 준비

목표:

- 신규 대화형 진단 게임에서 사용할 OpenAI API 호출 기반을 먼저 고정한다.

작업:

- `requirements.txt`에 OpenAI Python SDK 추가
- `.env.example`에 `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_FAST_MODEL` 추가
- `backend/config.py`에 OpenAI 설정 추가
- `backend/openai_client.py` 추가
- `backend/ai_chat.py` 또는 `backend/routers/chat.py`의 기존 AI 호출 경로를 OpenAI 기반으로 전환할지, 신규 기능에만 별도 `openai_client`를 사용할지 결정
- API 키 미설정 fallback 규칙 구현

완료 기준:

- OpenAI API 키가 있으면 텍스트 생성 헬퍼가 동작한다.
- OpenAI API 키가 없어도 신규 게임 데모는 규칙 기반 fallback으로 진행된다.
- Gemini 관련 설정은 신규 기능 경로에서 사용되지 않는다.

### Phase 1. 진입점과 화면 골격

목표:

- 시작화면 3번째 카드 추가
- `/interactive-diagnosis` 라우트 추가
- 신규 페이지 기본 레이아웃 구현

작업:

- `static/landing.html` 수정
- `main.py`에 신규 라우트 추가
- `static/interactive.html` 추가
- `static/js/interactive.js` 추가
- 기본 샘플 세션 UI 구현

완료 기준:

- 시작화면에서 3번째 카드가 보인다.
- 클릭 시 신규 페이지가 열린다.
- 신규 페이지에서 게임 목록, 플레이 영역, 로그 패널이 보인다.

### Phase 2. 게임 로그 API

목표:

- 공통 이벤트 스키마와 인메모리 저장소 구현

작업:

- `backend/game_models.py` 추가
- `backend/game_store.py` 추가
- `backend/routers/games.py` 추가
- `main.py`에 games 라우터 등록
- 이벤트 기록 API 구현
- 테스트 추가

완료 기준:

- 프론트에서 이벤트를 전송하면 서버 세션에 누적된다.
- 이벤트 목록을 조회할 수 있다.

### Phase 3. 손절/존버 게임 서버 연동

목표:

- 기존 클라이언트 게임 로직을 서버 이벤트 로그 방식으로 연결

작업:

- 신규 페이지에 손절/존버 게임 구현
- 매수/매도/타임아웃/라운드 종료 이벤트 전송
- 규칙 기반 GM 멘트 풀 구현
- 핵심 장면 OpenAI API 호출 옵션 구현

완료 기준:

- 게임 5라운드가 진행된다.
- 모든 주요 행동이 서버 이벤트로 기록된다.
- 실시간 로그 패널에서 이벤트를 확인할 수 있다.

### Phase 4. 게임 위키 생성

목표:

- 게임 로그를 표준 위키로 변환

작업:

- `backend/game_agents.py` 추가
- 위키 템플릿 구현
- OpenAI API 기반 위키 생성 구현
- `OPENAI_API_KEY` 미설정 fallback 구현
- 컴플라이언스 필터 연결
- 위키 조회 UI 구현

완료 기준:

- 손절/존버 게임 종료 후 위키가 생성된다.
- 위키에 요약, 핵심 행동, 성향 지표, 인상적 순간이 포함된다.

### Phase 5. 밸런스 게임 추가

목표:

- 두 번째 게임을 플러그인 방식으로 추가

작업:

- 게임 catalog에 `balance` 추가
- 선택 이벤트와 반응 시간 기록
- 게임별 scoring 구현
- 위키 생성 연결

완료 기준:

- 손절/존버와 밸런스 게임 각각 위키가 생성된다.

### Phase 6. 종합 리포트

목표:

- 게임 위키와 포트폴리오 분석을 합쳐 최종 리밸런싱 리포트 생성

작업:

- `backend/routers/reports.py` 추가
- `backend/report_agents.py` 추가
- 포트폴리오 분석 결과 연결
- 백테스트 API 선택 연동
- 종합 리포트 UI 구현

완료 기준:

- 게임 위키 1개 이상과 포트폴리오 분석 결과로 종합 리포트가 생성된다.
- 원시 로그 없이 위키만 종합 에이전트 입력으로 사용된다.

### Phase 7. 영속화와 운영 보강

목표:

- 데모 이상의 안정성 확보

작업:

- DB 테이블 추가
- Alembic 마이그레이션 추가
- 세션 만료 정책
- 개인정보 저장 최소화
- 리포트 내보내기

완료 기준:

- 서버 재시작 후에도 필요한 리포트 데이터가 유지된다.

## 15. 예상 파일 변경 목록

신규:

- `INTERACTIVE_AI_DIAGNOSIS_IMPLEMENTATION_PLAN.md`
- `static/interactive.html`
- `static/js/interactive.js`
- `static/css/interactive.css`
- `backend/openai_client.py`
- `backend/openai_chat.py`
- `backend/game_models.py`
- `backend/game_store.py`
- `backend/game_agents.py`
- `backend/report_agents.py`
- `backend/routers/games.py`
- `backend/routers/reports.py`
- `tests/test_game_models.py`
- `tests/test_game_store.py`
- `tests/test_game_routes.py`
- `tests/test_report_routes.py`

수정:

- `main.py`
- `static/landing.html`
- `requirements.txt`
- `.env.example`
- `backend/config.py`
- `backend/ai_chat.py` 또는 `backend/routers/chat.py`
- `backend/routers/__init__.py`
- `backend/db_models.py` 또는 마이그레이션 파일
- `README.md` 또는 배포 안내 문서

## 16. 주요 리스크와 대응

### 16.1 LLM 비용과 응답 지연

리스크:

- 게임 중 매 턴 OpenAI API를 호출하면 비용과 지연이 커진다.

대응:

- 손절/존버 게임은 규칙 기반 멘트 풀을 기본값으로 사용한다.
- 핵심 순간에만 OpenAI API를 호출한다.
- `OPENAI_API_KEY`가 없거나 호출이 실패하면 fallback 멘트를 사용한다.

### 16.2 투자 권유 오해

리스크:

- 게임 GM 멘트나 종합 리포트가 매수/매도 권유로 오해될 수 있다.

대응:

- 모든 출력은 컴플라이언스 필터를 통과시킨다.
- UI와 프롬프트에 `가상 시뮬레이션` 표현을 고정한다.
- 최종 리포트는 `조정안 예시`와 `검토 포인트` 중심으로 작성한다.

### 16.3 개인정보 처리

리스크:

- 사주 게임에서 생년월일과 출생시간이 민감하게 느껴질 수 있다.

대응:

- MVP에서는 사주 게임을 서버 연동 대상에서 제외하거나 파생 지표만 저장한다.
- 원문 저장 금지 옵션을 기본값으로 둔다.

### 16.4 기존 데모와 중복

리스크:

- `/demo`와 신규 `/interactive-diagnosis`가 유사해 보일 수 있다.

대응:

- `/demo`는 완성형 4단계 솔루션 위저드로 유지한다.
- 신규 페이지는 로그, 위키, 종합 에이전트 파이프라인을 전면에 보여준다.

## 17. 우선순위 결론

가장 먼저 구현할 것은 OpenAI API 호출 계층을 고정하는 것이다. 그 다음 시작화면 3번째 카드와 신규 라우트를 추가한다. 이후 손절/존버 게임을 서버 로그 기반으로 연결하고, 게임 위키 생성까지 붙이면 이번 기획의 핵심 차별점이 드러난다.

추천 MVP 순서는 다음과 같다.

1. OpenAI API 호출 계층과 fallback 규칙 구현
2. 시작화면 3번째 카드와 `/interactive-diagnosis` 페이지 추가
3. 공통 게임 이벤트 스키마와 저장 API 구현
4. 손절/존버 게임 이벤트 로깅
5. 손절/존버 게임 위키 생성
6. 밸런스 게임 추가
7. 종합 리포트 생성
8. DB 영속화 및 나머지 게임 확장

이 순서로 진행하면 기존 서비스 안정성을 건드리지 않고, 신규 기획을 독립된 세 번째 서비스로 빠르게 검증할 수 있다.
