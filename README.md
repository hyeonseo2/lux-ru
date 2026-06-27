# LUX-RU

> **"내가 진짜로 보유한 종목은 무엇인가?"** — ETF · 펀드를 끝까지 풀어, 실질 노출을 한 장의 그래프로 보여주는 Look-Through Risk & Return Unit

증권사 앱에서 보는 "내 보유 종목"은 거짓말을 하지 않지만, 진실을 모두 말해주지도 않습니다.
**TIGER 미국S&P500** 1,000만 원과 **SPY** 5,000달러를 함께 들고 있다면 — 사용자는 "두 가지 상품에 분산 투자 중"이라고 생각하지만, 실제로는 **같은 500개 종목에 두 번 베팅**하고 있는 셈입니다.

LUX-RU는 이런 ETF/펀드 껍데기를 **재귀적으로 분해(Look-through)** 해서, 실제 기초 종목 단위의 노출 금액을 계산하고 네트워크 그래프로 시각화합니다.

---

## ✨ 핵심: Look-through 분석 엔진

> 한 줄 요약 — *"ETF 이름이 아니라, ETF가 보유한 진짜 종목 단위로 포트폴리오를 본다."*

### Look-through란?
일반 증권사 화면이 보여주는 것: `KODEX 200 1,000만 원 보유` ✅
Look-through가 보여주는 것:
```
KODEX 200 1,000만 원
 ├─ 삼성전자  290만 원 (29.0%)
 ├─ SK하이닉스 70만 원 (7.0%)
 ├─ LG에너지솔루션 45만 원
 ├─ 현대차 35만 원
 └─ ... 196개 종목으로 분해
```

여러 ETF/계좌에 걸쳐 이 분해를 수행한 뒤 **동일 종목을 합산**하면, 사용자도 몰랐던 실질 집중이 드러납니다.

### 분해 엔진의 동작 (`backend/lookthrough.py`)
1. **재귀 분해** — Position → ETF/펀드 → (다른 펀드일 수도 있음) → 최종 stock/bond/cash까지 트리를 내려갑니다. 최대 깊이 4단계.
2. **순환 방지** — 펀드가 다른 펀드를 보유하는 fund-of-funds 구조에서도 무한 루프 차단(`visited` 집합).
3. **가중치 검증** — ETF 구성 가중치 합이 1.0 ± 0.005를 벗어나면 신뢰도를 자동으로 0.70으로 cap.
4. **잔여 처리** — 미공시 비중은 "미분류/기타"로 분리 표시(숨기지 않습니다).
5. **신뢰도 추적** — 각 leaf 노드마다 데이터 출처(`issuer_csv`, `seed_data`, `benchmark`...)와 coverage(`full`/`partial`/`proxy`)를 보존하여 최종 A~E 등급 산출.
6. **다중 통화 환산** — USD 자산은 yfinance 실시간 환율(`KRW=X`, 6h TTL 캐시) + 폴백으로 KRW 기준 환산.

### 실제로 드러나는 시나리오들

#### 🔴 시나리오 1: "S&P 500 ETF 3개 = 사실상 한 종목"
```
ISA 계좌    : TIGER 미국S&P500 (360750)  500만 원
연금저축    : KODEX 미국S&P500TR (379800) 300만 원
해외주식    : SPY                          $2,000 (≈274만 원)
```
**증권사 화면**: 3개 상품에 분산
**Look-through 결과**: 같은 S&P 500 구성종목에 약 1,074만 원이 동시 노출 → **중복도 약 99%** 경고

#### 🟡 시나리오 2: "나스닥 100과 S&P 500은 다른 ETF 아닌가요?"
```
TIGER 미국S&P500  +  TIGER 미국나스닥100 (또는 QQQ)
```
두 ETF 모두 **AAPL, MSFT, NVDA, AMZN, META, GOOGL** 등 빅테크를 상위 비중으로 보유.
Look-through로 풀면 **공통 보유 종목 약 15개, 중복도 40~60%** — "분산"이 아니라 "더블 다운"이라는 사실이 드러납니다.

#### 🟠 시나리오 3: "엔비디아 한 종목에 얼마나 노출되어 있을까?"
TIGER 미국S&P500 + TIGER 미국나스닥100 + 엔비디아 직접 보유분을 합치면, 사용자는 자신이 보유한 줄도 몰랐던 ETF 내부 NVDA 지분까지 누적되어 **엔비디아 단일 종목 노출이 포트폴리오의 12~15%**에 달할 수 있습니다.

---

## 🕸️ 네트워크 그래프 — Look-through 결과의 시각화

분해 결과를 D3.js force-directed 그래프(Canvas 렌더링)로 그립니다.

```
[일반 계좌] ──┬─→ [TIGER 미국S&P500] ─┬─→ AAPL
              │                      ├─→ NVDA  ←─┐
              └─→ [TIGER 나스닥100] ──┴─→ MSFT    │  같은 종목에
                                                  │  여러 ETF가
[ISA]      ──→ [KODEX 미국S&P500TR] ──→ NVDA  ────┘  수렴 = 집중 노출
```

- **3계층 노드** : Account(계좌) → Fund/ETF(상품) → Stock(실질 종목)
- **링크 굵기** = 노출 금액. 한눈에 큰 흐름이 보입니다.
- **수렴 패턴** : 한 stock 노드로 들어오는 링크가 많을수록, 사용자가 의도하지 않은 집중 노출을 의미합니다.
- **계좌 종류 구분** : 일반/ISA/연금저축/IRP/예수금을 시각적으로 분리하여, 세제 혜택 계좌에 어떤 자산이 들어있는지 확인할 수 있습니다.
- **노드 Hover 정보창** : 연관 종목 분석에서 노드에 마우스 오버하면 반투명 툴팁으로 종목/금액/비중/섹터와 유입 경로(연관 ETF·상품)가 즉시 표시됩니다.
- **워크플로우 상세 패널** : 우측 패널 제목을 "노드 상세"에서 "워크플로우 상세"로 통일해 분석 로그/노드 상세 컨텍스트를 함께 보여줍니다.
- **동적 범례** : 범례는 고정 5개가 아니라 실질 노출된 섹터 전체를 비중순으로 표시하며, "금융"과 "기타"를 분리 표기합니다.

---

## 📊 부가 분석 기능

### ETF 중복도 (Weighted Jaccard)
`backend/overlap.py`가 ETF 쌍별로 `sum(min(weight_a[i], weight_b[i]))` 형태의 가중 교집합 계산.
- 70% 이상 → "사실상 동일" 경고
- 40~70% → "높은 중복" 주의
- 5% 미만 → 표시 생략

### 집중도 지수 (HHI)
실질 종목 비중을 제곱 합산한 Herfindahl-Hirschman Index로 포트폴리오 편중도 정량화.

### 섹터/국가/통화 노출
Look-through 결과를 차원별로 재집계. `backend/sector_labels.py`가 yfinance 영문 섹터와 KRX 공식 `업종명`을 같은 한국어 canonical 라벨로 정규화하고, NVDA·005930 등 반도체 본업 종목은 ticker 기반 오버라이드로 격상합니다. 프런트 범례는 실질 노출된 섹터 전체를 대상으로 동적으로 렌더링됩니다.

### 시장 충격 시뮬레이션 (실측 백테스트)
5개 실제 과거 이벤트(2008 금융위기 · 2018 미중 무역분쟁 · 2020 코로나19 · 2022 美 금리 인상 · 2024 엔비디아 쇼크)에 대해 **yfinance 일봉 실측 데이터**로 종목별 수익률 + 일별 시계열을 계산. 채권형 종목은 KODEX 종합채권(273130.KS) 프록시로 대체. OpenAI API로 근거(Rationale) 생성 + 리밸런싱 제안 카드 표시.

### 대시보드 벤치마크 비교 차트 (NEW)
포트폴리오 대시보드에서 **내 포트폴리오 누적 수익률**을 `KOSPI`, `S&P 500`, `NASDAQ`과 동일 기간(기본 최근 1년) 기준으로 비교하는 선그래프를 제공합니다.
- 백엔드 `POST /api/portfolio/benchmark-compare`가 종목별 실질 익스포저를 기반으로 포트폴리오 시계열을 계산
- 지수 심볼은 `^KS11`, `^GSPC`, `^IXIC` 사용
- 축/범례에 각 시리즈 최종 수익률과 데이터 커버리지를 함께 표시

### 사용자 입력/표시 정합성 (2026-05 개선)
- 직접 입력 목록, 내 종목 현황, 시뮬레이션 영향 종목에서 종목 코드를 그대로 노출하지 않고 종목명을 우선 표시합니다.
- 내 종목 현황 탭은 최초 계좌만 표시하지 않고, 추가된 모든 계좌의 상품을 함께 렌더링하며 단일 계좌 입력 케이스도 누락 없이 표시합니다.
- `목표 포트폴리오 설정` 버튼/모달/목표비중 오버레이 기능은 제거되어 도넛 비교 UI를 단순화했습니다.

### AI 챗봇 (OpenAI API)
- **Look-through 결과만을 컨텍스트로 사용** — 임의 추정·계산 금지가 시스템 프롬프트에 명시
- 한국 금융업 컴플라이언스 가드: "사세요/매수하세요/원금 보장/대박/떡상" 등 9종 표현 정규식으로 자동 차단·치환
- 모든 응답 말미에 "본 정보는 정보제공 및 시뮬레이션이며 투자자문이 아닙니다" 면책 자동 부착

### 📸 스크린샷 자동 파싱 (NEW)
증권사 앱의 보유종목 화면을 캡처해서 좌측 패널 📸 드롭존에 드래그/클릭/`Ctrl+V`로 업로드하면 OpenAI vision이 **종목·금액·계좌 유형**을 자동 추출해 직접 입력 폼에 채워 넣습니다.
- 이미지는 메모리에서만 처리(디스크 저장 없음)
- 응답에 면책 문구 항상 포함, 사용자 확인 UX(편집·삭제 가능)
- API 키 미설정 환경에서도 데모를 보여줄 수 있는 **🧪 샘플 이미지로 테스트** 버튼 제공

### CSV 업로드
미래에셋 · 키움 · 토스 · 삼성 · NH 5개 증권사 컬럼 매핑 + `auto` 모드.
한국어/영문 헤더 동시 인식, EUC-KR/CP949/UTF-8/UTF-8-BOM 인코딩 자동 감지.

---

## 🏗️ 아키텍처

```
┌──────────────────────────────────────────────────────┐
│  Frontend (Vanilla JS + D3.js v7 Canvas)             │
│  네트워크 그래프 / 대시보드 / 시뮬레이션 / 챗        │
└────────────────────┬─────────────────────────────────┘
                     │ REST / SSE / multipart
┌────────────────────▼─────────────────────────────────┐
│  FastAPI                                             │
│  /api/portfolio · /api/upload · /api/chat · /api/finlife │
└────────────────────┬─────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────┐
│  Look-through 엔진 (core)                            │
│  expand() → aggregate() → compute_exposure()         │
└────────────────────┬─────────────────────────────────┘
                     │
   ┌─────────────────┼─────────────────┬─────────────┐
   ▼                 ▼                 ▼             ▼
 Seed DB         yfinance         OpenAI API     PostgreSQL
 (시드)         (실시간/과거)    (텍스트+비전)  + Neo4j (옵션)
```

### 기술 스택
| 분류 | 사용 기술 |
|---|---|
| Frontend | Vanilla JS, HTML5, CSS3, **D3.js v7 (Canvas)**, Chart.js, Cytoscape |
| Backend | Python 3.12, FastAPI, Pydantic v2 |
| AI/LLM | OpenAI API (텍스트 + 비전) |
| Data | yfinance, pykrx(KRX ETF), SQLAlchemy, Neo4j (옵션) |
| Infra | Docker, Google Cloud Run (asia-northeast3) |

---

## 🚀 시작하기

### 로컬 실행
```bash
pip install -r requirements.txt
```

`.env` 파일에 필요한 키를 넣습니다.

```bash
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=your_openai_model
OPENAI_FAST_MODEL=your_fast_openai_model
DART_API_KEY=your_dart_api_key
KRX_ID=your_krx_id
KRX_PW=your_krx_password
```

```bash
python main.py
# 또는
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```
브라우저에서 `http://localhost:8080` 접속.

### Docker
```bash
docker build -t lux-ru .
docker run -p 8080:8080 -e OPENAI_API_KEY=$OPENAI_API_KEY -e OPENAI_MODEL=$OPENAI_MODEL lux-ru
```

### Cloud Run 배포
```bash
./scripts/deploy_cloud_run.sh
```

이 스크립트는 `.env`의 `KRX_ID`, `KRX_PW`를 Secret Manager(`krx-id`, `krx-pw`)에 자동 반영하고 Cloud Run에 secret env로 연결합니다. `.env` 자체는 배포 소스에 포함하지 않습니다.
OpenAI 설정은 `.env`의 `OPENAI_API_KEY`를 Secret Manager(`openai-api-key`)에 반영하고, `OPENAI_MODEL`, `OPENAI_FAST_MODEL`은 Cloud Run 환경변수로 설정합니다.

운영 URL: `https://lux-ru-415500942280.asia-northeast3.run.app`

---

## 📁 디렉터리 구조

```
lux-ru/
├── main.py                       # FastAPI 진입점
├── backend/
│   ├── config.py                 # 환경변수 + CORS allowlist
│   ├── models.py                 # Pydantic 도메인 모델
│   ├── lookthrough.py            # ⭐ Look-through 재귀 분해 엔진
│   ├── overlap.py                # ETF 중복도 (Weighted Jaccard)
│   ├── live_data.py              # 사용자 직접 입력 → 그래프 빌더
│   ├── historical.py             # 5개 시나리오 yfinance 일봉 백테스트
│   ├── fx.py                     # FX 환율 동적 조회 (yfinance + TTL 캐시)
│   ├── sector_labels.py          # GICS → 한국어 섹터 라벨 단일 출처
│   ├── csv_parser.py             # 증권사 CSV 파서 (5사 매핑)
│   ├── screenshot_parser.py      # 📸 OpenAI vision 스크린샷 추출
│   ├── ai_chat.py                # OpenAI 텍스트 챗
│   ├── compliance.py             # 금지 표현 필터 + 면책 부착
│   ├── seed_data.py              # ETF 구성/주식/예적금 시드
│   ├── search_universe.py        # 대형 검색 유니버스 + KRX ETF 병합
│   ├── krx_etf.py                # pykrx 기반 국내 ETF 리스트/PDF 구성종목
│   ├── routers/                  # FastAPI 라우터
│   └── worker/crawler.py         # yfinance 기반 미국 ETF 크롤러
├── static/
│   ├── index.html                # 메인 SPA (5천+줄, 인라인 D3/JS)
│   ├── js/                       # 보조 페이지 스크립트
│   ├── css/style.css
│   └── assets/
│       ├── sample.csv            # 데모용 CSV
│       └── sample-screenshot.png # 데모용 스크린샷
├── scripts/
│   └── make_sample_screenshot.py # 샘플 이미지 생성기
├── requirements.txt
├── Dockerfile
└── docker-compose.yml            # PostgreSQL + Neo4j (옵션)
```

---

## 🔌 주요 API

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/api/upload` | 증권사 CSV 업로드 및 파싱 |
| `POST` | `/api/upload/screenshot` | 📸 스크린샷에서 종목 추출 (OpenAI vision) |
| `POST` | `/api/portfolio/analyze` | CSV 결과에 대한 전체 Look-through 분석 |
| `POST` | `/api/portfolio/analyze_real` | 사용자 직접 입력 종목 라이브 분석 |
| `POST` | `/api/portfolio/benchmark-compare` | 포트폴리오 vs KOSPI/S&P500/NASDAQ 누적 수익률 비교 |
| `GET`  | `/api/portfolio/backtest/scenarios` | 5개 과거 이벤트 시나리오 메타 |
| `POST` | `/api/portfolio/backtest` | 시나리오별 yfinance 실측 백테스트 |
| `GET`  | `/api/portfolio/analysis/{sid}` | 세션의 최신 분석 결과 조회 |
| `GET`  | `/api/portfolio/sessions/{sid}` | 세션 정보 조회 |
| `GET`  | `/api/portfolio/search-instruments?q=` | 종목 자동완성 |
| `POST` | `/api/chat` | OpenAI 기반 SSE 챗 |
| `GET`  | `/api/finlife/deposits` · `/savings` · `/pension` · `/all` | 예적금/연금 상품 |
| `GET`  | `/health` | 헬스체크 |

서버 실행 후 `/docs`에서 Swagger UI로 상세 스키마 확인 가능.

---

## 🧠 한 요청이 처리되는 흐름

사용자가 ISA 계좌에 **TIGER 미국S&P500 500만 원**, 연금저축에 **SPY $2,000**을 입력하면:

1. **정규화** : 티커 대문자 변환, USD→KRW 환산(`backend.fx.convert`, yfinance + TTL 캐시), 계좌 라벨 표준화
2. **시드/KRX 매칭** : `resolve_instrument()`로 시드 ETF를 찾고, 국내 ETF는 `pykrx` + `KRX_ID/KRX_PW`가 있으면 KRX ETF 리스트/PDF로 확장
3. **재귀 분해** : 시드 `HoldingSnapshot`, KRX ETF PDF, yfinance crawler 순으로 구성종목을 찾아 stock leaf까지 트리 전개
4. **금액 배분** : 보유 금액 × 각 종목 비중 = 실질 노출 금액
5. **동일 종목 합산** : `aggregate()`가 UUID 기준으로 leaf를 머지 — **여기서 "S&P 500 ETF 두 개"가 같은 AAPL/NVDA로 합쳐짐**
6. **차원별 집계** : yfinance sector 또는 KRX 업종명을 canonical 섹터로 맞춘 뒤 섹터/국가/통화 weight 합산, HHI 계산, 데이터 등급 산출
7. **그래프 빌드** : `live_data.py`가 Account → Fund → Stock 3계층 노드 + 링크 구조로 직렬화
8. **응답** : 그래프 + 상위 30개 종목 + 중복 ETF 쌍 + `debug_trace`(단계별 로그)를 단일 JSON으로 반환
9. **렌더링** : D3.js Canvas force simulation, 노드 크기는 노출 금액의 제곱근

---

## 🛡️ 컴플라이언스 주의

이 서비스는 **투자자문이 아닙니다**. `backend/compliance.py`가 다음을 강제합니다.

- 단정·권유 표현 9종(`"사세요"`, `"매수하세요"`, `"원금 보장"`, `"고수익"`, `"대박"` 등) 정규식 차단
- AI 응답 말미 면책 문구 자동 부착
- ETF 보유 내역에는 `coverage`(full/partial/proxy)와 `confidence`(0~1) 필수 표기
- 데이터 신뢰등급(A~E)을 항상 함께 노출하여, 사용자가 "이 분석이 얼마나 믿을 만한가"를 판단할 수 있도록 함
- 스크린샷 파싱: 이미지 메모리 처리(디스크 저장 없음) + 추출 결과는 추정값임을 UI에 명시

---

## 🗺️ 로드맵

- [x] 실제 과거 가격 데이터 기반 백테스트 (5개 시나리오 yfinance 일봉)
- [x] 📸 스크린샷 자동 파싱 (OpenAI vision)
- [ ] 증권사 OpenAPI 연동 (현재는 CSV 업로드 / 스크린샷 / 수동 입력)
- [ ] 분석 결과 영속화 (현재는 in-memory 세션)
- [ ] 종목 클릭 시 역추적(Back-tracing): 그 종목이 들어있는 모든 ETF/펀드를 그래프에서 하이라이트
- [x] 국내 ETF 검색/추가 기반 확장 (`pykrx` KRX ETF 리스트 + PDF 구성종목, `KRX_ID/KRX_PW` 필요)
- [ ] KOFIA·DART·KRX 공시 기반 펀드 구성 자동 갱신 (현재는 시드 + KRX ETF PDF + yfinance)
- [ ] 모바일 반응형 디자인 고도화
- [ ] 한국 PIPA 국외이전 대응: OpenAI API 사용 시 데이터 처리/보관 정책 검토

---

## 📄 라이선스

데모/연구 목적 프로젝트.

---

*문서 최종 업데이트: 2026-05-30*
