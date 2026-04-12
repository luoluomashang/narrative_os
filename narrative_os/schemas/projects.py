"""schemas/projects.py — 项目管理请求/响应模型。"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ProjectListItem(BaseModel):
    project_id: str
    title: str = ""
    chapter_count: int = 0
    total_chapters: int = 0
    last_modified: str = ""
    status: str = "active"


class ProjectInitRequest(BaseModel):
    project_id: str = Field(..., min_length=1, max_length=100)
    title: str = ""
    genre: str = ""
    description: str = ""


class ProjectInitResponse(BaseModel):
    project_id: str
    created_at: str
    state_dir: str


class ProjectUpdateRequest(BaseModel):
    title: Optional[str] = None
    genre: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class ProjectMutationResponse(BaseModel):
    success: bool = True
    project_id: str
    status: str | None = None


class WorkflowNodeStatus(BaseModel):
    step_id: str
    label: str
    status: str
    href: str = ""
    statistic: str = ""


class ProjectStatusResponse(BaseModel):
    project_id: str
    project_name: str = ""
    current_chapter: int = 0
    current_volume: int = 1
    total_word_count: int = 0
    versions: list[int] = Field(default_factory=list)
    world_published: bool = False
    character_count: int = 0
    characters_with_drive: int = 0
    pending_changes_count: int = 0
    current_volume_goal: str = ""
    workflow_nodes: list[WorkflowNodeStatus] = Field(default_factory=list)


class ProjectRollbackRequest(BaseModel):
    steps: int = Field(default=1, ge=1, le=50)


class ProjectRollbackResponse(BaseModel):
    success: bool = True
    project_id: str
    rolled_back_to_chapter: int
    snapshot_timestamp: str = ""


class MetricsHistoryItem(BaseModel):
    chapter: int
    summary: str = ""
    quality_score: float = 0.0
    hook_score: float = 0.0
    word_count: int = 0
    timestamp: str = ""
    qd_01: float = 0.0
    qd_02: float = 0.0
    qd_03: float = 0.0
    qd_04: float = 0.0
    qd_05: float = 0.0
    qd_06: float = 0.0
    qd_07: float = 0.0
    qd_08: float = 0.0


class SettingsUpdateRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class GlobalSettingsResponse(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectSettingsResponse(BaseModel):
    project_id: str
    global_settings: dict[str, Any] = Field(default_factory=dict)
    project_overrides: dict[str, Any] = Field(default_factory=dict)
    merged: dict[str, Any] = Field(default_factory=dict)


class CostSummaryResponse(BaseModel):
    today_tokens: int
    total_tokens: int
    today_cost_usd: float
    by_agent: dict[str, int]
    by_skill: dict[str, int]


class CostHistoryItem(BaseModel):
    date: str
    tokens: int
    cost_usd: float
    by_skill: dict[str, int] = Field(default_factory=dict)
    by_agent: dict[str, int] = Field(default_factory=dict)
