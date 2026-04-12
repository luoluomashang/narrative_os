"""schemas/traces.py — 追踪 & 杂项请求/响应模型。"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class RunType(str, Enum):
    CHAPTER_GENERATION = "chapter_generation"
    TRPG_TURN = "trpg_turn"
    WORLD_PUBLISH = "world_publish"
    CANON_COMMIT = "canon_commit"


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class ArtifactType(str, Enum):
    OUTLINE = "outline"
    DRAFT = "draft"
    CRITIQUE = "critique"
    FINAL_TEXT = "final_text"
    MAINTENANCE = "maintenance"
    WORLD_DELTA = "world_delta"


class Artifact(BaseModel):
    artifact_id: str = ""
    run_id: str = ""
    step_id: str = ""
    artifact_type: ArtifactType
    agent_name: str
    input_summary: str
    output_content: str
    quality_scores: dict[str, float] = Field(default_factory=dict)
    token_in: int = 0
    token_out: int = 0
    latency_ms: float = 0.0
    retry_count: int = 0
    retry_reason: str | None = None


class RunStep(BaseModel):
    step_id: str
    run_id: str
    step_index: int
    agent_name: str
    status: RunStatus
    artifact: Artifact | None = None
    started_at: str
    ended_at: str | None = None


class ApprovalCheckpoint(BaseModel):
    checkpoint_id: str
    run_id: str
    reason: str
    context: str
    created_at: str
    resolved_at: str | None = None
    decision: str | None = None


class Run(BaseModel):
    run_id: str
    project_id: str
    run_type: RunType
    status: RunStatus
    chapter_num: int | None = None
    session_id: str | None = None
    steps: list[RunStep] = Field(default_factory=list)
    started_at: str
    ended_at: str | None = None
    total_cost_usd: float = 0.0
    approval_checkpoint: ApprovalCheckpoint | None = None


class RunListResponse(BaseModel):
    items: list[Run] = Field(default_factory=list)


class RunApprovalRequest(BaseModel):
    decision: str = Field(..., pattern="^(approve|reject|retry)$")


class RunApprovalResponse(BaseModel):
    run_id: str
    status: RunStatus
    checkpoint: ApprovalCheckpoint | None = None


class StyleExtractRequest(BaseModel):
    text: str = Field(..., min_length=1)


class StyleExtractResponse(BaseModel):
    sentence_length: str
    tone: str
    genre: str
    style_directives: list[str] = Field(default_factory=list)
    warning_words: list[str] = Field(default_factory=list)


class PluginInfo(BaseModel):
    id: str
    name: str
    enabled: bool
    description: str


class StylePreset(BaseModel):
    id: str
    name: str
    genre: str
    tone: str
    sentence_length: str
    params: dict[str, Any] = Field(default_factory=dict)


class TraceResponse(BaseModel):
    chapter_id: str
    nodes: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    note: str = ""


class WorldbuilderStepRequest(BaseModel):
    wb_session_id: str
    user_input: str = ""


class WorldbuilderStartResponse(BaseModel):
    wb_session_id: str
    step: str
    prompt: str
    requires_confirmation: bool
    skippable: bool
    draft: dict[str, Any] | None = None


class WorldbuilderStepResponse(BaseModel):
    wb_session_id: str
    step: str
    done: bool
    prompt: str | None = None
    requires_confirmation: bool
    skippable: bool
    draft: dict[str, Any] | None = None
    seed_data: dict[str, Any] | None = None


class WorldBuilderDiscussRequest(BaseModel):
    wb_session_id: str
    message: str


class ConsistencyCheckRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_id: str = "default"
    chapter: int = 0


class ConsistencyIssue(BaseModel):
    dimension: str
    severity: str
    description: str
    suggestion: str
    source_rule: str = ""
    confidence: float = 0.0


class ConsistencyReport(BaseModel):
    score: float = 0.0
    issues: list[ConsistencyIssue] = Field(default_factory=list)
    summary: str = ""
