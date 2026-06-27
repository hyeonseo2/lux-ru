"""CSV / screenshot upload API router."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..csv_parser import parse_csv
from ..screenshot_parser import MAX_BYTES, parse_screenshot

router = APIRouter(prefix="/api/upload", tags=["upload"])


@router.post("")
async def upload_csv(
    file: UploadFile = File(...),
    broker: str = Form("auto"),
    session_id: str = Form(""),
):
    """Upload and parse a broker CSV file."""
    content = await file.read()

    positions, column_mapping, warnings = parse_csv(content, broker=broker)

    return {
        "success": True,
        "rows_total": len(positions) + len(warnings),
        "rows_parsed": len(positions),
        "rows_failed": len([w for w in warnings if "매핑 실패" in w]),
        "positions": [p.model_dump(mode="json") for p in positions],
        "column_mapping": column_mapping,
        "warnings": warnings,
    }


@router.post("/screenshot")
async def upload_screenshot(file: UploadFile = File(...)):
    """포트폴리오 스크린샷을 OpenAI vision으로 파싱.

    이미지 바이트는 메모리에서만 처리되며 디스크에 저장되지 않습니다.
    """
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"이미지가 너무 큽니다 (최대 {MAX_BYTES // (1024 * 1024)} MB).",
        )
    return parse_screenshot(content, file.content_type or "")
