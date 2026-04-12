"""schemas/trpg.py — TRPG 会话请求/响应模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    project_id: str = "default"
    character_name: str = "主角"
    density: str = "normal"
    opening_prompt: str = ""
    world_summary: str = ""
    max_history_turns: int = 50
    chapter: Optional[int] = None


class CreateSessionResponse(BaseModel):
    session_id: str
    phase: str
    density: str
    scene_pressure: float
    opening_turn: "TurnRecordResponse | None" = None


class SessionStepRequest(BaseModel):
    user_input: str


class InterruptRequest(BaseModel):
    bangui_command: str


class RollbackRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=20)


class SessionStatusResponse(BaseModel):
    session_id: str
    project_id: str
    phase: str
    turn: int
    scene_pressure: float
    density: str
    history_count: int
    emotional_temperature: Any
    turn_char_count: int = 0


class TurnRecordResponse(BaseModel):
    turn_id: int
    who: str
    content: str
    scene_pressure: float
    density: str
    phase: str
    has_decision: bool
    decision_options: list[str] = Field(default_factory=list)


class SessionSummary(BaseModel):
    duration_minutes: int = 0
    turn_count: int = 0
    word_count: int = 0
    bangui_count: int = 0
    key_decisions: list[dict[str, Any]] = Field(default_factory=list)
    next_hook: str = ""
    character_delta: list[dict[str, Any]] = Field(default_factory=list)
    saved_chapter: int | None = None


class SaveRequest(BaseModel):
    trigger: str = "manual"


class SavePoint(BaseModel):
    save_id: str
    trigger: str
    timestamp: str
    turn: int
    scene_pressure: float | None = None


class ControlModeRequest(BaseModel):
    mode: str
    ai_controlled_characters: list[str] = Field(default_factory=list)
    allow_protagonist_proxy: bool = False
    director_intervention_enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class ControlModeResponse(BaseModel):
    session_id: str
    mode: str
    prompt_hint: str


class AgendaResponse(BaseModel):
    session_id: str
    turn: int
    agenda: list[dict[str, Any]] = Field(default_factory=list)


class SessionCommitRequest(BaseModel):
    commit_type: str = "session_only"
    mode: str | None = None  # 向后兼容：某些测试发送 {"mode": "..."}
    draft_content: str = ""
    require_canon_confirm: bool = False


class SessionCommitResponse(BaseModel):
    changeset_id: str
    commit_mode: str
    changes_count: int
    canon_confirmed: bool
