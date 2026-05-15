"""AI Chat API router with SSE streaming."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..ai_chat import generate_ai_response
from .portfolio import _sessions

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    session_id: str
    message: str


@router.post("")
async def chat(req: ChatRequest):
    """SSE streaming chat endpoint."""
    session = _sessions.get(req.session_id, {})
    analysis = session.get("analysis")

    async def event_stream():
        # Send tool progress
        yield f"data: {json.dumps({'type': 'progress', 'step': 'intent_classify', 'message': '질문 분석 중...'})}\n\n"

        yield f"data: {json.dumps({'type': 'progress', 'step': 'data_lookup', 'message': '포트폴리오 데이터 조회 중...'})}\n\n"

        yield f"data: {json.dumps({'type': 'progress', 'step': 'generate', 'message': 'AI 답변 생성 중...'})}\n\n"

        # Stream AI response
        async for chunk in generate_ai_response(req.message, analysis):
            yield f"data: {json.dumps({'type': 'content', 'text': chunk})}\n\n"

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
