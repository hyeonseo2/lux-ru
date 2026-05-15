"""FX rate lookup with TTL cache and graceful fallback.

KRW↔USD 환율을 yfinance에서 동적으로 조회한다. 네트워크 실패·yfinance
의존성 누락·rate-limit 등 모든 실패 케이스에서는 `config.FX_KRW_USD`
하드코딩 값으로 안전하게 폴백한다.

캐시는 프로세스 메모리에 보관(in-process LRU + TTL). Cloud Run 다중
인스턴스 환경에서는 인스턴스별로 독립이지만 TTL이 짧지 않아 비용 부담은
무시 가능. 외부 공유 캐시(Redis)가 필요해지면 `_FX_CACHE` 어댑터만 교체.
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .config import FX_KRW_USD

LOG = logging.getLogger(__name__)

# (from_ccy, to_ccy) -> (rate, expires_at_unix)
_FX_CACHE: dict[tuple[str, str], tuple[float, float]] = {}
DEFAULT_TTL_SECONDS = 6 * 3600  # 6시간 — FX는 분 단위 변동이 크지 않고 외부 호출 절감.


def _fetch_yfinance(pair: str) -> Optional[float]:
    """Return latest available rate for a yfinance currency pair (e.g. 'KRW=X').

    `KRW=X`는 USD/KRW를 의미한다(1 USD당 KRW 수). 실패 시 None.
    """
    try:
        import yfinance as yf
    except Exception as exc:
        LOG.warning("yfinance unavailable for FX lookup: %s", exc)
        return None

    try:
        ticker = yf.Ticker(pair)
        # 1차: fast_info (info보다 가벼움, 일부 환경에서만 제공)
        fast = getattr(ticker, "fast_info", None)
        if fast is not None:
            try:
                v = fast.get("last_price") if hasattr(fast, "get") else getattr(fast, "last_price", None)
                if v is not None and float(v) > 0:
                    return float(v)
            except Exception:
                pass

        # 2차: history (가장 안정적)
        hist = ticker.history(period="5d", interval="1d")
        if hist is not None and len(hist) > 0 and "Close" in hist:
            last = hist["Close"].iloc[-1]
            if last is not None and float(last) > 0:
                return float(last)

        # 3차: info (느리지만 가끔 1차/2차가 비었을 때 채워줌)
        info = getattr(ticker, "info", None) or {}
        if isinstance(info, dict):
            for key in ("regularMarketPrice", "previousClose", "ask", "bid"):
                v = info.get(key)
                if v is not None and float(v) > 0:
                    return float(v)
    except Exception as exc:
        LOG.warning("yfinance fetch %s failed: %s", pair, exc)
    return None


def _fallback_rate(from_ccy: str, to_ccy: str) -> Optional[float]:
    """Use the hardcoded FX_KRW_USD as last-resort fallback."""
    if from_ccy == "USD" and to_ccy == "KRW":
        return float(FX_KRW_USD)
    if from_ccy == "KRW" and to_ccy == "USD":
        return 1.0 / float(FX_KRW_USD)
    return None


def get_fx_rate(from_ccy: str, to_ccy: str, ttl: int = DEFAULT_TTL_SECONDS) -> float:
    """Return `to_ccy` per 1 unit of `from_ccy`. Cached TTL seconds.

    동일 통화면 1.0. 미지원 페어는 1.0과 함께 경고 로그.
    """
    fc = (from_ccy or "").upper().strip()
    tc = (to_ccy or "").upper().strip()
    if not fc or not tc or fc == tc:
        return 1.0

    cache_key = (fc, tc)
    now = time.time()
    cached = _FX_CACHE.get(cache_key)
    if cached and cached[1] > now:
        return cached[0]

    rate: Optional[float] = None
    if (fc, tc) == ("USD", "KRW"):
        rate = _fetch_yfinance("KRW=X")
    elif (fc, tc) == ("KRW", "USD"):
        live = _fetch_yfinance("KRW=X")
        if live and live > 0:
            rate = 1.0 / live

    if rate is None:
        rate = _fallback_rate(fc, tc)
        if rate is None:
            LOG.warning("Unsupported FX pair %s/%s; returning 1.0", fc, tc)
            return 1.0
        LOG.info("FX fallback used for %s/%s: %.4f", fc, tc, rate)

    _FX_CACHE[cache_key] = (rate, now + ttl)
    return rate


def convert(amount, from_ccy: str, to_ccy: str):
    """Convert amount with caching. Preserves Decimal precision if input is Decimal."""
    rate = get_fx_rate(from_ccy, to_ccy)
    # Preserve Decimal where possible
    try:
        from decimal import Decimal
        if isinstance(amount, Decimal):
            return amount * Decimal(str(rate))
    except Exception:
        pass
    return amount * rate


def reset_cache() -> None:
    """Wipe in-process cache. Tests/admin only."""
    _FX_CACHE.clear()
