"""schemas/characters.py — 角色管理请求/响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.core.character import (
    BehaviorConstraint as BehaviorConstraintDetail,
    CharacterDrive,
    CharacterRuntime,
    CharacterState as CharacterDetail,
    DialogueExample,
    Motivation,
    RelationshipProfile,
    VoiceFingerprint,
)


class CharacterSummary(BaseModel):
    name: str
    emotion: str = "平静"
    health: float = 1.0
    arc_stage: str = "防御"
    faction: str = ""
    is_alive: bool = True


class PlotNode(BaseModel):
    id: str
    type: str = ""
    status: str = ""
    tension: float = 0.0

    model_config = {"extra": "allow"}


class PlotEdge(BaseModel):
    source: str
    target: str

    model_config = {"extra": "allow"}


class PlotGraphData(BaseModel):
    nodes: list[PlotNode] = Field(default_factory=list)
    edges: list[PlotEdge] = Field(default_factory=list)


class CharacterCreateRequest(BaseModel):
    name: str
    traits: list[str] = Field(default_factory=list)
    goal: str = ""
    backstory: str = ""
    description: str = ""
    personality: str = ""
    alias: list[str] = Field(default_factory=list)
    speech_style: str = ""
    catchphrases: list[str] = Field(default_factory=list)
    dialogue_examples: list[DialogueExample | dict[str, Any]] = Field(default_factory=list)
    motivations: list[Motivation | dict[str, Any]] = Field(default_factory=list)
    scenario_context: str = ""
    system_instructions: str = ""
    faction: str = ""


class CharacterRuntimeUpdateRequest(BaseModel):
    current_location: str | None = None
    current_agenda: str | None = None
    location: str | None = None
    agenda: str | None = None
    current_companions: list[str] | None = None
    current_pressure: float | None = None
    emotion_trigger_source: str | None = None
    recent_key_events: list[str] | None = None
    can_advance_plot: bool | None = None
    stance_mode: str | None = None


class TestVoiceRequest(BaseModel):
    scenario: str


class TestVoiceResponse(BaseModel):
    dialogue: str


class DeleteCharacterResponse(BaseModel):
    deleted: str
