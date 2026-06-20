"""FastAPI application entry point for LUX-RU."""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import ALLOWED_ORIGINS as DEFAULT_ALLOWED_ORIGINS
from backend.routers import portfolio, upload, chat, finlife

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="LUX-RU",
    description="Look-Through Risk & Return Unit",
    version="1.0.0",
)

origins = [
    s.strip()
    for s in os.getenv("ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if s.strip()
]
if not origins:
    origins = DEFAULT_ALLOWED_ORIGINS

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=all(o != "*" for o in origins),
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(portfolio.router)
app.include_router(upload.router)
app.include_router(chat.router)
app.include_router(finlife.router)

# Static files
BASE_DIR = Path(__file__).parent
STATIC_DIR = BASE_DIR / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def root():
    """Serve the service selector."""
    landing_path = STATIC_DIR / "landing.html"
    if landing_path.exists():
        return FileResponse(str(landing_path))
    return await original_service()


@app.get("/original")
async def original_service():
    """Serve the original LUX-RU service."""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "LUX-RU API", "docs": "/docs"}


@app.get("/demo")
async def demo_service():
    """Serve the demo-based LUX-RU wizard."""
    demo_path = BASE_DIR / "LUX-RU_demo.html"
    if demo_path.exists():
        return FileResponse(str(demo_path))
    return await original_service()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lux-ru"}


if __name__ == "__main__":
    import uvicorn
    from backend.config import PORT
    uvicorn.run(app, host="0.0.0.0", port=PORT)
