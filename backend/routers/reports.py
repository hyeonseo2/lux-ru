"""Interactive diagnosis report API."""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..game_store import get_session, list_wikis, save_report
from ..report_agents import generate_synthesis_report

router = APIRouter(prefix="/api/reports", tags=["reports"])


class SynthesisRequest(BaseModel):
    session_id: str
    include_backtest: bool = True


@router.post("/synthesis")
async def synthesis_report(req: SynthesisRequest) -> dict:
    session = get_session(req.session_id)
    wikis = list_wikis(req.session_id)
    report = await run_in_threadpool(
        generate_synthesis_report,
        session_id=req.session_id,
        wikis=wikis,
        portfolio_analysis=session.get("portfolio_analysis"),
    )
    save_report(report)
    return {"success": True, "report": report.model_dump(mode="json")}
