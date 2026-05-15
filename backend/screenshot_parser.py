"""Screenshot-based portfolio extraction via Gemini vision.

사용자가 업로드한 증권사·자산관리 앱의 보유종목 스크린샷에서
종목/티커/평가금액/계좌 유형을 추출해 직접 입력 폼에 채워 넣을 수 있는
구조화된 리스트로 반환한다.

법적/운영 가드
----------------
- 이미지는 메모리에서만 처리, 디스크에 저장하지 않음.
- 결과는 AI 추정이며 응답에 면책 문구를 항상 포함.
- 사이즈/포맷 제한으로 비정상 입력 차단.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .config import GOOGLE_API_KEY, GEMINI_MODEL
from .seed_data import ALL_INSTRUMENTS, resolve_instrument

LOG = logging.getLogger(__name__)


EXTRACTION_PROMPT = """이 이미지는 한국 또는 미국 증권사·자산관리 앱의 포트폴리오 보유종목 화면입니다.
보유 중인 모든 종목/ETF/펀드를 추출해 **JSON 배열만** 응답하세요. 코드블록(```)이나 설명 문구 금지.

각 항목 스키마:
{
  "name": "한글 또는 영문 종목/ETF 이름",
  "ticker": "종목코드(6자리 숫자) 또는 영문 티커. 보이지 않으면 빈 문자열",
  "amount_krw": 평가금액_정수,
  "currency": "KRW 또는 USD",
  "account_type": "taxable|pension_saving|isa|irp|deposit|etc"
}

추출 규칙
1. amount_krw는 정수만. "1,234,567원" → 1234567. 쉼표·통화기호·단위 제거.
2. 외화 표기는 currency="USD"로 두고 amount_krw에는 USD 금액 그대로(서버가 환산).
3. 종목코드(6자리 숫자) 또는 영문 티커(SPY, QQQ 등)가 보이면 ticker에 그대로.
4. 계좌 유형 매핑:
   - 주식/위탁/일반/CMA → taxable
   - 연금저축 → pension_saving
   - ISA → isa
   - IRP/퇴직연금 → irp
   - 예수금/입출금/현금 → deposit
   - 알 수 없으면 etc
5. 평가금액(현재가치) 우선. 매수금액·평단·수익률·계좌번호 무시.
6. 보유수량 0이거나 식별 불가, 광고·뉴스 항목은 생략.

배열만 반환. 빈 결과면 []."""


MAX_BYTES = 8 * 1024 * 1024  # 8 MB
ALLOWED_MIMES = {
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/webp",
    "image/heic",
    "image/heif",
}

ACCOUNT_LABEL_MAP: dict[str, str] = {
    "taxable": "주식계좌",
    "pension_saving": "연금저축",
    "isa": "ISA",
    "irp": "IRP",
    "deposit": "예수금/입출금",
    "etc": "기타",
}

DISCLAIMER = (
    "AI가 이미지에서 추출한 결과로 부정확할 수 있습니다. "
    "추가하기 전에 종목·금액·계좌 유형이 맞는지 반드시 확인하세요. "
    "업로드된 이미지는 분석 즉시 폐기되며 저장되지 않습니다."
)


def _clean_text(s: Any) -> str:
    if s is None:
        return ""
    return str(s).strip()


def _coerce_int(v: Any) -> int:
    if v is None:
        return 0
    if isinstance(v, bool):
        return 0
    if isinstance(v, (int, float)):
        return int(v)
    text = re.sub(r"[^\d\-]", "", str(v))
    try:
        return int(text) if text else 0
    except ValueError:
        return 0


def _resolve_to_seed_ticker(name: str, raw_ticker: str) -> tuple[str, bool]:
    """Return (ticker, resolved_from_seed).

    1) raw_ticker가 시드에 있으면 시드 symbol 그대로 사용.
    2) name으로 seed_data.resolve_instrument 시도.
    3) 둘 다 실패해도 raw_ticker 또는 name이 비어 있지 않다면 그 값을 반환 —
       프론트의 search-instruments + 사용자 수정 흐름으로 보강.
    """
    t = _clean_text(raw_ticker).upper()
    if t and re.fullmatch(r"[A-Z0-9.\-]{1,20}", t):
        uid = resolve_instrument(t)
        if uid:
            inst = ALL_INSTRUMENTS.get(uid)
            if inst and inst.symbol:
                return inst.symbol.upper(), True
        return t, False

    n = _clean_text(name)
    if not n:
        return "", False
    uid = resolve_instrument(n)
    if uid:
        inst = ALL_INSTRUMENTS.get(uid)
        if inst and inst.symbol:
            return inst.symbol.upper(), True
    return "", False


def _unwrap_codeblock(raw: str) -> str:
    return re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        raw,
        flags=re.IGNORECASE | re.DOTALL,
    ).strip()


def _result(success: bool, positions: list, warnings: list, extra: dict | None = None) -> dict:
    payload = {
        "success": success,
        "positions": positions,
        "warnings": warnings,
        "disclaimer": DISCLAIMER,
    }
    if extra:
        payload.update(extra)
    return payload


def parse_screenshot(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    """Gemini Vision으로 스크린샷에서 보유종목을 추출.

    Returns:
        {success, positions, warnings, disclaimer, extracted_count, matched_count}
    """
    if not GOOGLE_API_KEY:
        return _result(False, [], ["GOOGLE_API_KEY가 설정되지 않아 스크린샷 파싱을 사용할 수 없습니다."])

    if not image_bytes:
        return _result(False, [], ["빈 이미지입니다."])

    if len(image_bytes) > MAX_BYTES:
        return _result(False, [], [f"이미지가 너무 큽니다 (최대 {MAX_BYTES // (1024 * 1024)} MB)."])

    mt = (mime_type or "").lower().strip()
    if mt not in ALLOWED_MIMES:
        return _result(False, [], [f"지원하지 않는 이미지 형식입니다: {mt or '미상'}"])

    try:
        import google.generativeai as genai
        genai.configure(api_key=GOOGLE_API_KEY)
        model = genai.GenerativeModel(GEMINI_MODEL)
        response = model.generate_content(
            [EXTRACTION_PROMPT, {"mime_type": mt, "data": image_bytes}],
            generation_config={
                "response_mime_type": "application/json",
                "temperature": 0.1,
            },
        )
        raw = (getattr(response, "text", None) or "").strip()
    except Exception as exc:
        LOG.error("Gemini vision call failed: %s", exc)
        return _result(False, [], [f"AI 추출 호출 실패: {exc}"])

    if not raw:
        return _result(False, [], ["AI 응답이 비어 있습니다."])

    raw_stripped = _unwrap_codeblock(raw)
    try:
        parsed = json.loads(raw_stripped)
    except json.JSONDecodeError as exc:
        LOG.warning("Failed to parse Gemini JSON: %s | raw=%s", exc, raw_stripped[:300])
        return _result(False, [], ["AI 응답을 JSON으로 해석하지 못했습니다."])

    if isinstance(parsed, dict):
        for key in ("positions", "items", "holdings", "data"):
            if key in parsed and isinstance(parsed[key], list):
                parsed = parsed[key]
                break

    if not isinstance(parsed, list):
        return _result(False, [], ["AI 응답 구조가 예상과 다릅니다."])

    positions: list[dict[str, Any]] = []
    warnings: list[str] = []
    extracted_total = len(parsed)

    for idx, item in enumerate(parsed, start=1):
        if not isinstance(item, dict):
            warnings.append(f"{idx}번 항목: 형식 오류, 스킵")
            continue
        name = _clean_text(item.get("name") or item.get("instrument_name"))
        raw_ticker = _clean_text(item.get("ticker") or item.get("symbol"))
        amount = _coerce_int(
            item.get("amount_krw")
            or item.get("amount")
            or item.get("market_value")
        )
        currency = (_clean_text(item.get("currency")) or "KRW").upper()
        account_type = _clean_text(item.get("account_type") or "taxable").lower()
        if account_type not in ACCOUNT_LABEL_MAP:
            account_type = "taxable"

        if not name and not raw_ticker:
            warnings.append(f"{idx}번 항목: 이름·티커 모두 없음, 스킵")
            continue
        if amount <= 0:
            warnings.append(f"{idx}번 항목 '{name or raw_ticker}': 금액 0 이하, 스킵")
            continue

        ticker, resolved = _resolve_to_seed_ticker(name, raw_ticker)
        display_ticker = ticker or raw_ticker
        if not display_ticker:
            warnings.append(
                f"{idx}번 항목 '{name}': 티커를 추정하지 못했습니다. 직접 입력으로 보강해 주세요."
            )
            continue
        if not resolved and not ticker:
            warnings.append(
                f"'{name or display_ticker}': 시드 데이터에서 매칭되지 않아 분석 정확도가 떨어질 수 있습니다."
            )

        positions.append({
            "ticker": display_ticker.upper(),
            "name": name or display_ticker,
            "amount": amount,
            "currency": currency,
            "account_type": account_type,
            "account_label": ACCOUNT_LABEL_MAP[account_type],
            "resolved": resolved,
        })

    return _result(
        True,
        positions,
        warnings,
        extra={
            "extracted_count": extracted_total,
            "matched_count": sum(1 for p in positions if p["resolved"]),
        },
    )
