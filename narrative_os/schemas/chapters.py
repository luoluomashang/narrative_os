"""schemas/chapters.py — 章节生成请求/响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.infra.config import settings


class RunChapterRequest(BaseModel):
    chapter: int = Field(ge=1, le=9999)
    volume: int = Field(default=1, ge=1, le=999)
    target_summary: str = Field(min_length=1)
    word_count_target: int = Field(default=2000, ge=500, le=20000)
    strategy: str = settings.llm_strategy
    previous_hook: str = ""
    existing_arc_summary: str = ""
    character_names: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    project_id: str = "default"
    skill_names: list[str] = Field(default_factory=list)
    force_generate: bool = False


class RunChapterResponse(BaseModel):
    chapter: int
    volume: int
    text: str
    word_count: int
    change_ratio: float
    quality_score: float
    hook_score: float
    passed: bool
    retry_count: int
    run_id: str = ""


class PlanChapterRequest(BaseModel):
    chapter: int
    volume: int = 1
    target_summary: str
    word_count_target: int = 2000
    previous_hook: str = ""
    character_names: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    project_id: str = "default"


class PlanChapterResponse(BaseModel):
    chapter_outline: str
    planned_nodes: list[dict[str, Any]]
    dialogue_goals: list[str]
    hook_suggestion: str
    hook_type: str
    tension_curve: list[float]


class CheckChapterRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_id: str = "default"
    chapter: int = 0


class CheckChapterResponse(BaseModel):
    issues: list[dict[str, Any]]
    passed: bool


class HumanizeRequest(BaseModel):
    text: str = Field(..., min_length=1)
    project_id: str = "default"
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)


class HumanizeResponse(BaseModel):
    original: str
    humanized: str
    changes_count: int
    diff: list[dict[str, str]]


class ChapterListItem(BaseModel):
    chapter: int
    summary: str = ""
    word_count: int = 0
    quality_score: float = 0.0
    hook_score: float = 0.0
    has_text: bool = False
    timestamp: str = ""


class ChapterTextResponse(BaseModel):
    chapter: int
    text: str
    word_count: int = 0
    summary: str = ""
    quality_score: float = 0.0
    hook_score: float = 0.0
    timestamp: str = ""


class ExportNovelResponse(BaseModel):
    project_id: str
    title: str
    chapter_count: int
    total_chapters: int
    total_words: int
    format: str
    content: str


class MetricsRequest(BaseModel):
    draft: dict[str, Any]
    word_count_target: int = 2000


class MetricsResponse(BaseModel):
    chapter: int
    overall_score: float
    avg_tension: float
    hook_score: float
    payoff_density: float
    pacing_score: float
    tension_trend: str
    consistency_score: float
    word_efficiency: float
    qd_01_catharsis: float = 0.0
    qd_02_golden_finger: float = 0.0
    qd_03_rhythm: float = 0.0
    qd_04_dialogue: float = 0.0
    qd_05_char_consistency: float = 0.0
    qd_06_meaning: float = 0.0
    qd_07_hook: float = 0.0
    qd_08_readability: float = 0.0


class CostResponse(BaseModel):
    used_tokens: int
    budget_tokens: int
    usage_ratio: float
    by_skill: dict[str, int]
    by_agent: dict[str, int]


class WritingPrecheckItem(BaseModel):
    key: str
    passed: bool
    severity: str = "warning"
    message: str
    action_path: str | None = None


class WritingContextCharacter(BaseModel):
    name: str
    current_location: str = ""
    current_agenda: str = ""
    current_pressure: float = 0.0
    recent_key_events: list[str] = Field(default_factory=list)


class WritingWorldSummary(BaseModel):
    published: bool = False
    factions: list[str] = Field(default_factory=list)
    regions: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)


class WritingContextResponse(BaseModel):
    project_id: str
    chapter: int = 1
    previous_hook: str = ""
    current_volume_goal: str = ""
    pending_changes_count: int = 0
    world: WritingWorldSummary = Field(default_factory=WritingWorldSummary)
    characters: list[WritingContextCharacter] = Field(default_factory=list)
    prechecks: list[WritingPrecheckItem] = Field(default_factory=list)
