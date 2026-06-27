"""In-memory store for interactive diagnosis sessions."""
from __future__ import annotations

from uuid import uuid4

from .game_models import GameEvent, GameId, GameWiki, SynthesisReport

_game_sessions: dict[str, dict] = {}


def create_session(session_id: str | None = None, portfolio_analysis: dict | None = None) -> dict:
    sid = session_id or f"luxru-game-{uuid4().hex[:10]}"
    session = _game_sessions.setdefault(
        sid,
        {
            "portfolio_analysis": None,
            "events": [],
            "wikis": {},
            "synthesis_report": None,
        },
    )
    if portfolio_analysis is not None:
        session["portfolio_analysis"] = portfolio_analysis
    return {"session_id": sid, **session}


def get_session(session_id: str) -> dict:
    return create_session(session_id)


def set_portfolio_analysis(session_id: str, portfolio_analysis: dict | None) -> None:
    session = get_session(session_id)
    session["portfolio_analysis"] = portfolio_analysis


def add_event(event: GameEvent) -> GameEvent:
    session = get_session(event.session_id)
    session["events"].append(event)
    return event


def list_events(session_id: str, game_id: GameId | None = None) -> list[GameEvent]:
    events: list[GameEvent] = get_session(session_id)["events"]
    if game_id:
        return [event for event in events if event.game_id == game_id]
    return list(events)


def save_wiki(wiki: GameWiki) -> GameWiki:
    session = get_session(wiki.session_id)
    session["wikis"][wiki.game_id] = wiki
    return wiki


def list_wikis(session_id: str) -> list[GameWiki]:
    return list(get_session(session_id)["wikis"].values())


def save_report(report: SynthesisReport) -> SynthesisReport:
    session = get_session(report.session_id)
    session["synthesis_report"] = report
    return report
