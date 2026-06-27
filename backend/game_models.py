"""Models for interactive diagnosis games."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

GameId = Literal["buy_sell", "balance", "risk", "bias", "master", "saju"]
EventType = Literal[
    "game_start",
    "gm_message",
    "user_choice",
    "user_action",
    "hesitation",
    "round_start",
    "round_end",
    "game_end",
]


class TraitSignal(BaseModel):
    risk_tolerance: int = Field(default=0, ge=-5, le=5)
    diversification: int = Field(default=0, ge=-5, le=5)
    behavior_bias: int = Field(default=0, ge=-5, le=5)
    time_horizon: int = Field(default=0, ge=-5, le=5)
    stability_growth: int = Field(default=0, ge=-5, le=5)
    sector_tags: list[str] = Field(default_factory=list)


class GameEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    game_id: GameId
    turn: int = 0
    event_type: EventType
    created_at: datetime = Field(default_factory=datetime.utcnow)
    action: str | None = None
    context: str = ""
    reaction_latency_ms: int | None = None
    signal: TraitSignal = Field(default_factory=TraitSignal)
    payload: dict[str, Any] = Field(default_factory=dict)


class GameWiki(BaseModel):
    session_id: str
    game_id: GameId
    title: str
    markdown: str
    trait_summary: TraitSignal
    evidence_count: int
    created_at: datetime = Field(default_factory=datetime.utcnow)


class SynthesisReport(BaseModel):
    session_id: str
    markdown: str
    source_game_ids: list[GameId]
    created_at: datetime = Field(default_factory=datetime.utcnow)
