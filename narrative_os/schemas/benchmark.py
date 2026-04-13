"""schemas/benchmark.py — Benchmark Phase 1 请求/响应模型。"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from narrative_os.schemas.traces import Run


class BenchmarkJobType(str, Enum):
    PROJECT_BENCHMARK = "project_benchmark"
    AUTHOR_DISTILLATION = "author_distillation"


class BenchmarkJobMode(str, Enum):
    SINGLE_WORK = "single_work"
    MULTI_WORK = "multi_work"
    SCENE = "scene"


class BenchmarkSourceType(str, Enum):
    PROJECT_REFERENCE = "project_reference"
    AUTHOR_REFERENCE = "author_reference"


class BenchmarkProfileStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"


class BenchmarkSkillApplyMode(str, Enum):
    GUIDE = "guide"
    HYBRID = "hybrid"
    STRICT = "strict"


class BenchmarkSceneType(str, Enum):
    BATTLE = "battle"
    EMOTION = "emotion"
    REVEAL = "reveal"
    DAILY = "daily"
    ENSEMBLE = "ensemble"
    GENERAL = "general"


class BenchmarkSourceCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    file_name: str = Field(default="", max_length=300)
    text: str = Field(default="")
    author_name: str | None = Field(default=None, max_length=200)
    corpus_group: str = Field(default="", max_length=100)
    chapter_sep: str | None = Field(default=None, max_length=300)


class BenchmarkJobCreateRequest(BaseModel):
    job_type: BenchmarkJobType
    mode: BenchmarkJobMode = BenchmarkJobMode.SINGLE_WORK
    source_ids: list[str] = Field(default_factory=list)
    sources: list[BenchmarkSourceCreateRequest] = Field(default_factory=list)
    chapter_sep: str | None = Field(default=None, max_length=300)
    extract_snippets: bool = True
    target_platform: str | None = Field(default=None, max_length=100)
    author_name: str | None = Field(default=None, max_length=200)
    corpus_group: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _validate_sources(self) -> "BenchmarkJobCreateRequest":
        if not self.source_ids and not self.sources:
            raise ValueError("source_ids 或 sources 至少提供一项。")
        if self.job_type == BenchmarkJobType.AUTHOR_DISTILLATION and not (
            self.author_name or self.corpus_group
        ):
            raise ValueError("author_distillation 必须提供 author_name 或 corpus_group。")
        return self


class BenchmarkSource(BaseModel):
    source_id: str
    project_id: str
    corpus_group: str = ""
    title: str
    author_name: str | None = None
    file_name: str = ""
    sha256: str = ""
    char_count: int = 0
    chapter_sep: str | None = None
    source_type: BenchmarkSourceType
    created_at: str


class BenchmarkSnippet(BaseModel):
    snippet_id: str
    profile_id: str
    project_id: str
    source_id: str
    scene_type: BenchmarkSceneType
    chapter: int | None = None
    offset_start: int = 0
    offset_end: int = 0
    char_count: int = 0
    anchor_score: float = 0.0
    purity_score: float = 0.0
    distinctiveness_score: float = 0.0
    source_hit_verified: bool = False
    text: str


class BenchmarkProfile(BaseModel):
    profile_id: str
    project_id: str
    profile_type: BenchmarkJobType
    profile_name: str = ""
    source_ids: list[str] = Field(default_factory=list)
    stable_traits: list[dict[str, Any]] = Field(default_factory=list)
    conditional_traits: list[dict[str, Any]] = Field(default_factory=list)
    anti_traits: list[dict[str, Any]] = Field(default_factory=list)
    scene_anchors: dict[str, Any] = Field(default_factory=dict)
    humanness_baseline: dict[str, Any] = Field(default_factory=dict)
    status: BenchmarkProfileStatus = BenchmarkProfileStatus.DRAFT
    snippet_count: int = 0
    created_at: str
    activated_at: str | None = None


class AuthorSkillProfile(BaseModel):
    skill_id: str
    origin_project_id: str
    run_id: str | None = None
    skill_name: str = ""
    author_name: str = ""
    source_ids: list[str] = Field(default_factory=list)
    stable_rules: list[dict[str, Any]] = Field(default_factory=list)
    conditional_rules: list[dict[str, Any]] = Field(default_factory=list)
    anti_rules: list[dict[str, Any]] = Field(default_factory=list)
    dialogue_rules: list[dict[str, Any]] = Field(default_factory=list)
    scene_patterns: dict[str, Any] = Field(default_factory=dict)
    chapter_hook_patterns: list[dict[str, Any]] = Field(default_factory=list)
    humanness_baseline: dict[str, Any] = Field(default_factory=dict)
    confidence_map: dict[str, Any] = Field(default_factory=dict)
    status: BenchmarkProfileStatus = BenchmarkProfileStatus.DRAFT
    created_at: str
    applied: bool = False
    application_mode: BenchmarkSkillApplyMode | None = None


class BenchmarkSkillListResponse(BaseModel):
    items: list[AuthorSkillProfile] = Field(default_factory=list)
    active_skill_id: str | None = None
    active_mode: BenchmarkSkillApplyMode | None = None


class BenchmarkSkillApplyRequest(BaseModel):
    mode: BenchmarkSkillApplyMode = BenchmarkSkillApplyMode.HYBRID


class BenchmarkSkillApplyResponse(BaseModel):
    skill: AuthorSkillProfile
    mode: BenchmarkSkillApplyMode
    message: str = ""


class BenchmarkJobCreateResponse(BaseModel):
    run_id: str
    status: str
    profile: BenchmarkProfile
    author_skill: AuthorSkillProfile | None = None
    source_ids: list[str] = Field(default_factory=list)
    snippet_count: int = 0
    message: str = ""


class BenchmarkJobDetailResponse(BaseModel):
    run: Run
    profile: BenchmarkProfile | None = None
    author_skill: AuthorSkillProfile | None = None
    sources: list[BenchmarkSource] = Field(default_factory=list)
    snippets: list[BenchmarkSnippet] = Field(default_factory=list)
    message: str = ""


class BenchmarkProfileActivateRequest(BaseModel):
    profile_id: str = Field(..., min_length=1)


class BenchmarkSnippetListResponse(BaseModel):
    profile: BenchmarkProfile | None = None
    items: list[BenchmarkSnippet] = Field(default_factory=list)


class BenchmarkScore(BaseModel):
    score_id: str
    project_id: str
    run_id: str | None = None
    chapter: int = 0
    profile_id: str
    humanness_score: float = 0.0
    adherence_score: float = 0.0
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    violations: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    created_at: str