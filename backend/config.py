"""Application configuration."""
from __future__ import annotations
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "")
OPENAI_FAST_MODEL = os.getenv("OPENAI_FAST_MODEL", OPENAI_MODEL)
PORT = int(os.getenv("PORT", "8080"))

# Demo settings
MAX_CSV_ROWS = 500
MAX_DEPTH = 4
TOLERANCE = 0.005

# CORS
ALLOWED_ORIGINS = [
    "https://lux-ru-xtymbd36rq-du.a.run.app",
    "https://lux-ru-415500942280.asia-northeast3.run.app",
    "https://portfolio-xray-xtymbd36rq-du.a.run.app",
    "https://portfolio-xray-415500942280.asia-northeast3.run.app",
    "http://localhost:8080",
    "http://127.0.0.1:8080",
]

# Exchange rate — yfinance 조회 실패 시 사용하는 폴백 값.
# 정상 경로는 `backend.fx.get_fx_rate("USD","KRW")`이며 6시간 TTL로 캐시된다.
FX_KRW_USD = 1370.0
