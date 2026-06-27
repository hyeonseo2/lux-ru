"""Interactive diagnosis game API."""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from ..game_agents import (
    GAME_CATALOG,
    generate_conversation_reply,
    generate_game_wiki,
    generate_gm_message,
    infer_conversation_action,
    start_message,
)
from ..game_models import EventType, GameEvent, GameId, TraitSignal
from ..game_store import (
    add_event,
    create_session,
    get_session,
    list_events,
    list_wikis,
    save_wiki,
    set_portfolio_analysis,
)
from ..live_data import analyze_live_portfolio

router = APIRouter(prefix="/api/games", tags=["games"])


class GameSessionRequest(BaseModel):
    session_id: str | None = None
    positions: list[dict[str, Any]] = Field(default_factory=list)


class GameStartRequest(BaseModel):
    session_id: str
    context: dict[str, Any] = Field(default_factory=dict)


class GameEventRequest(BaseModel):
    session_id: str
    turn: int = 0
    event_type: EventType
    action: str | None = None
    context: str = ""
    reaction_latency_ms: int | None = None
    signal: TraitSignal = Field(default_factory=TraitSignal)
    payload: dict[str, Any] = Field(default_factory=dict)


class GmRequest(BaseModel):
    session_id: str
    turn: int = 0
    last_action: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ConversationRequest(BaseModel):
    session_id: str
    turn: int = 0
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class FinishRequest(BaseModel):
    session_id: str


@router.post("/session")
async def create_game_session(req: GameSessionRequest) -> dict:
    portfolio_analysis = None
    if req.positions:
        portfolio_analysis = await run_in_threadpool(analyze_live_portfolio, req.positions)
    session = create_session(req.session_id, portfolio_analysis=portfolio_analysis)
    return {
        "success": True,
        "session_id": session["session_id"],
        "portfolio_analysis": session["portfolio_analysis"],
    }


@router.get("/catalog")
async def games_catalog() -> dict:
    return {"games": GAME_CATALOG}


@router.get("/sessions/{session_id}")
async def game_session_detail(session_id: str) -> dict:
    session = get_session(session_id)
    return {
        "success": True,
        "session_id": session_id,
        "has_portfolio_analysis": session["portfolio_analysis"] is not None,
        "event_count": len(session["events"]),
        "wiki_count": len(session["wikis"]),
        "has_synthesis_report": session["synthesis_report"] is not None,
    }


@router.get("/sessions/{session_id}/events")
async def game_events(session_id: str, game_id: GameId | None = None) -> dict:
    events = list_events(session_id, game_id)
    return {"success": True, "events": [event.model_dump(mode="json") for event in events]}


@router.get("/sessions/{session_id}/wikis")
async def game_wikis(session_id: str) -> dict:
    wikis = list_wikis(session_id)
    return {"success": True, "wikis": [wiki.model_dump(mode="json") for wiki in wikis]}


@router.post("/{game_id}/start")
async def start_game(game_id: GameId, req: GameStartRequest) -> dict:
    create_session(req.session_id)
    message = start_message(game_id)
    event = add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=0,
        event_type="game_start",
        action="START",
        context=json.dumps(req.context, ensure_ascii=False),
        payload=req.context,
    ))
    return {
        "success": True,
        "game_id": game_id,
        "event": event.model_dump(mode="json"),
        "gm_message": message,
    }


@router.post("/{game_id}/events")
async def record_game_event(game_id: GameId, req: GameEventRequest) -> dict:
    event = add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=req.turn,
        event_type=req.event_type,
        action=req.action,
        context=req.context,
        reaction_latency_ms=req.reaction_latency_ms,
        signal=req.signal,
        payload=req.payload,
    ))
    return {"success": True, "event": event.model_dump(mode="json")}


@router.post("/{game_id}/gm")
async def game_master_message(game_id: GameId, req: GmRequest) -> dict:
    message, mode = await run_in_threadpool(
        generate_gm_message,
        game_id,
        req.last_action,
        req.context,
    )
    event = add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=req.turn,
        event_type="gm_message",
        action="GM_MESSAGE",
        context=message,
        payload={"mode": mode, "source_context": req.context},
    ))
    return {
        "success": True,
        "mode": mode,
        "message": message,
        "event": event.model_dump(mode="json"),
    }


@router.post("/{game_id}/conversation")
async def conversation_turn(game_id: GameId, req: ConversationRequest) -> dict:
    action, signal = infer_conversation_action(game_id, req.message, req.context)
    if isinstance(req.context.get("signal"), dict):
        signal = TraitSignal(**req.context["signal"])
    user_event = add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=req.turn,
        event_type="user_action" if game_id == "buy_sell" else "user_choice",
        action=action,
        context=req.message,
        reaction_latency_ms=req.context.get("elapsed_ms"),
        signal=signal,
        payload=req.context,
    ))
    message, mode = await run_in_threadpool(
        generate_conversation_reply,
        game_id,
        req.message,
        action,
        req.context,
    )
    gm_event = add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=req.turn,
        event_type="gm_message",
        action="GM_MESSAGE",
        context=message,
        payload={"mode": mode, "source_context": req.context, "inferred_action": action},
    ))
    return {
        "success": True,
        "mode": mode,
        "message": message,
        "inferred_action": action,
        "signal": signal.model_dump(mode="json"),
        "event": user_event.model_dump(mode="json"),
        "gm_event": gm_event.model_dump(mode="json"),
    }


@router.post("/{game_id}/finish")
async def finish_game(game_id: GameId, req: FinishRequest) -> dict:
    events = list_events(req.session_id, game_id)
    add_event(GameEvent(
        session_id=req.session_id,
        game_id=game_id,
        turn=len(events) + 1,
        event_type="game_end",
        action="END",
        context="게임 종료 및 위키 생성",
    ))
    events = list_events(req.session_id, game_id)
    wiki = await run_in_threadpool(generate_game_wiki, req.session_id, game_id, events)
    save_wiki(wiki)
    return {"success": True, "wiki": wiki.model_dump(mode="json")}


@router.post("/sessions/{session_id}/portfolio")
async def update_game_portfolio(session_id: str, req: GameSessionRequest) -> dict:
    portfolio_analysis = None
    if req.positions:
        portfolio_analysis = await run_in_threadpool(analyze_live_portfolio, req.positions)
    set_portfolio_analysis(session_id, portfolio_analysis)
    return {"success": True, "session_id": session_id, "portfolio_analysis": portfolio_analysis}
