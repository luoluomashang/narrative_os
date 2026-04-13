"""
infra/models.py — SQLAlchemy ORM 模型定义

共 7 张表：
  - projects            项目元数据
  - chapters            章节文本 + 质量评分
  - state_snapshots     每章 KB 快照（plot_graph + characters + world）
  - trpg_sessions       TRPG 会话记录
  - cost_records        Token 消耗明细
  - settings            全局/项目级设置覆盖
  - worldbuilder_sessions WorldBuilder 向导会话

所有表预留 user_id TEXT DEFAULT 'local'，为未来多用户做准备。
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------ #
# Project                                                             #
# ------------------------------------------------------------------ #
class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    title: Mapped[str] = mapped_column(String(200), default="", server_default="")
    genre: Mapped[str] = mapped_column(String(100), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    settings_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )  # active / archived / deleted
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    # relationships
    chapters: Mapped[list["Chapter"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    snapshots: Mapped[list["StateSnapshot"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    trpg_sessions: Mapped[list["TrpgSession"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    wb_sessions: Mapped[list["WorldbuilderSession"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    cost_records: Mapped[list["CostRecord"]] = relationship(back_populates="project")
    benchmark_sources: Mapped[list["BenchmarkSourceRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    benchmark_snippets: Mapped[list["BenchmarkSnippetRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    benchmark_profiles: Mapped[list["BenchmarkProfileRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    benchmark_scores: Mapped[list["BenchmarkScoreRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    author_skills: Mapped[list["AuthorSkillRecord"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


# ------------------------------------------------------------------ #
# Chapter                                                             #
# ------------------------------------------------------------------ #
class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE")
    )
    chapter_num: Mapped[int] = mapped_column(Integer)
    volume: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    word_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quality_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    hook_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    source: Mapped[str] = mapped_column(
        String(20), default="pipeline", server_default="pipeline"
    )  # pipeline / trpg / manual
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="chapters")

    __table_args__ = (
        Index("ix_chapters_project_chapter", "project_id", "chapter_num"),
    )


# ------------------------------------------------------------------ #
# StateSnapshot                                                       #
# ------------------------------------------------------------------ #
class StateSnapshot(Base):
    __tablename__ = "state_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE")
    )
    chapter_num: Mapped[int] = mapped_column(Integer)
    plot_graph_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    characters_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    world_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="snapshots")


# ------------------------------------------------------------------ #
# TrpgSession                                                         #
# ------------------------------------------------------------------ #
class TrpgSession(Base):
    __tablename__ = "trpg_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE")
    )
    chapter_num: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    phase: Mapped[str] = mapped_column(
        String(30), default="INIT", server_default="INIT"
    )
    turn_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    scene_pressure: Mapped[float] = mapped_column(Float, default=5.0, server_default="5")
    emotional_temp_json: Mapped[str] = mapped_column(
        Text, default="{}", server_default="{}"
    )
    history_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    summary_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="trpg_sessions")


# ------------------------------------------------------------------ #
# CostRecord                                                          #
# ------------------------------------------------------------------ #
class CostRecord(Base):
    __tablename__ = "cost_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    project_id: Mapped[str | None] = mapped_column(
        String(100),
        ForeignKey("projects.id", ondelete="SET NULL"),
        nullable=True,
    )
    skill: Mapped[str] = mapped_column(String(100), default="", server_default="")
    agent: Mapped[str] = mapped_column(String(100), default="", server_default="")
    tokens_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    model: Mapped[str] = mapped_column(String(100), default="", server_default="")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project | None"] = relationship(back_populates="cost_records")

    __table_args__ = (Index("ix_cost_records_created_at", "created_at"),)


# ------------------------------------------------------------------ #
# SettingRecord                                                        #
# ------------------------------------------------------------------ #
class SettingRecord(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    value_json: Mapped[str] = mapped_column(Text, default="null", server_default="null")
    scope: Mapped[str] = mapped_column(
        String(20), default="global", server_default="global"
    )  # global / project
    project_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


# ------------------------------------------------------------------ #
# WorldbuilderSession                                                  #
# ------------------------------------------------------------------ #
class WorldbuilderSession(Base):
    __tablename__ = "worldbuilder_sessions"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE")
    )
    current_step: Mapped[str] = mapped_column(
        String(50), default="ONE_SENTENCE", server_default="ONE_SENTENCE"
    )
    completed_steps_json: Mapped[str] = mapped_column(
        Text, default="[]", server_default="[]"
    )
    draft_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    seed_data_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="wb_sessions")


# ------------------------------------------------------------------ #
# WorldSandbox  (世界观沙盘)                                          #
# ------------------------------------------------------------------ #
class WorldSandbox(Base):
    """世界观沙盘数据表 — 每个项目唯一一条记录（project_id UNIQUE）"""
    __tablename__ = "world_sandboxes"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: __import__('uuid').uuid4().hex)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    sandbox_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    runtime_world_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )


# ------------------------------------------------------------------ #
# StoryConcept  (故事概念)                                            #
# ------------------------------------------------------------------ #
class StoryConcept(Base):
    """故事概念数据表 — 每个项目唯一一条记录（project_id UNIQUE）"""
    __tablename__ = "story_concepts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True, default=lambda: __import__('uuid').uuid4().hex)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, unique=True, index=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    concept_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )


# ------------------------------------------------------------------ #
# BenchmarkSourceRecord                                               #
# ------------------------------------------------------------------ #
class BenchmarkSourceRecord(Base):
    __tablename__ = "benchmark_sources"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    corpus_group: Mapped[str] = mapped_column(String(100), default="", server_default="")
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    author_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    file_name: Mapped[str] = mapped_column(String(300), default="", server_default="")
    sha256: Mapped[str] = mapped_column(String(64), default="", server_default="")
    char_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    chapter_sep: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_type: Mapped[str] = mapped_column(
        String(30), default="project_reference", server_default="project_reference"
    )
    text_content: Mapped[str] = mapped_column(Text, default="", server_default="")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="benchmark_sources")


# ------------------------------------------------------------------ #
# BenchmarkSnippetRecord                                              #
# ------------------------------------------------------------------ #
class BenchmarkSnippetRecord(Base):
    __tablename__ = "benchmark_snippets"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    profile_id: Mapped[str] = mapped_column(String(100), index=True)
    source_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("benchmark_sources.id", ondelete="CASCADE"), index=True
    )
    scene_type: Mapped[str] = mapped_column(String(100), default="unknown", server_default="unknown")
    chapter: Mapped[int | None] = mapped_column(Integer, nullable=True)
    offset_start: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    offset_end: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    char_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    anchor_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    purity_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    distinctiveness_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    text: Mapped[str] = mapped_column(Text, default="", server_default="")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="benchmark_snippets")

    __table_args__ = (
        Index("ix_benchmark_snippets_project_scene", "project_id", "scene_type"),
    )


# ------------------------------------------------------------------ #
# BenchmarkProfileRecord                                              #
# ------------------------------------------------------------------ #
class BenchmarkProfileRecord(Base):
    __tablename__ = "benchmark_profiles"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    profile_type: Mapped[str] = mapped_column(String(50), nullable=False)
    profile_name: Mapped[str] = mapped_column(String(300), default="", server_default="")
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    stable_traits_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    conditional_traits_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    anti_traits_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    scene_anchors_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    humanness_baseline_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    status: Mapped[str] = mapped_column(String(30), default="draft", server_default="draft")
    activated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="benchmark_profiles")

    __table_args__ = (
        Index("ix_benchmark_profiles_project_created", "project_id", "created_at"),
    )


# ------------------------------------------------------------------ #
# BenchmarkScoreRecord                                                #
# ------------------------------------------------------------------ #
class BenchmarkScoreRecord(Base):
    __tablename__ = "benchmark_scores"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    chapter: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    profile_id: Mapped[str] = mapped_column(String(100), index=True)
    humanness_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    adherence_score: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    dimension_scores_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    violations_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    recommendations_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="benchmark_scores")

    __table_args__ = (
        Index("ix_benchmark_scores_project_chapter", "project_id", "chapter"),
    )


# ------------------------------------------------------------------ #
# AuthorSkillRecord                                                   #
# ------------------------------------------------------------------ #
class AuthorSkillRecord(Base):
    __tablename__ = "author_skills"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    skill_name: Mapped[str] = mapped_column(String(300), default="", server_default="")
    author_name: Mapped[str] = mapped_column(String(200), default="", server_default="")
    source_ids_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    stable_rules_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    conditional_rules_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    anti_rules_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    dialogue_rules_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    scene_patterns_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    chapter_hook_patterns_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    humanness_baseline_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    confidence_map_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    status: Mapped[str] = mapped_column(String(30), default="draft", server_default="draft")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    project: Mapped["Project"] = relationship(back_populates="author_skills")

    __table_args__ = (
        Index("ix_author_skills_project_created", "project_id", "created_at"),
    )


# ------------------------------------------------------------------ #
# RunRecord                                                           #
# ------------------------------------------------------------------ #
class RunRecord(Base):
    __tablename__ = "runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    run_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="running", server_default="running")
    chapter_num: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    correlation_id: Mapped[str] = mapped_column(
        String(40), default="", server_default="", index=True
    )
    failure_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_step_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    steps: Mapped[list["RunStepRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["ApprovalCheckpointRecord"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


# ------------------------------------------------------------------ #
# RunStepRecord                                                       #
# ------------------------------------------------------------------ #
class RunStepRecord(Base):
    __tablename__ = "run_steps"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    agent_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    status: Mapped[str] = mapped_column(String(30), default="running", server_default="running")
    correlation_id: Mapped[str] = mapped_column(
        String(40), default="", server_default=""
    )
    failure_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["RunRecord"] = relationship(back_populates="steps")
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(
        back_populates="step", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_run_steps_run_step", "run_id", "step_index"),)


# ------------------------------------------------------------------ #
# ArtifactRecord                                                      #
# ------------------------------------------------------------------ #
class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    step_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("run_steps.id", ondelete="CASCADE"), index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(50), default="draft", server_default="draft")
    agent_name: Mapped[str] = mapped_column(String(100), default="", server_default="")
    input_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    output_content: Mapped[str] = mapped_column(Text, default="", server_default="")
    correlation_id: Mapped[str] = mapped_column(
        String(40), default="", server_default=""
    )
    quality_scores: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    token_in: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    token_out: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    retry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    step: Mapped["RunStepRecord"] = relationship(back_populates="artifacts")


# ------------------------------------------------------------------ #
# ApprovalCheckpointRecord                                            #
# ------------------------------------------------------------------ #
class ApprovalCheckpointRecord(Base):
    __tablename__ = "approval_checkpoints"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("runs.id", ondelete="CASCADE"), index=True
    )
    correlation_id: Mapped[str] = mapped_column(
        String(40), default="", server_default=""
    )
    reason: Mapped[str] = mapped_column(Text, default="", server_default="")
    context: Mapped[str] = mapped_column(Text, default="", server_default="")
    decision: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    run: Mapped["RunRecord"] = relationship(back_populates="approvals")


# ------------------------------------------------------------------ #
# Story Plan Records                                                  #
# ------------------------------------------------------------------ #
class BookPlanRecord(Base):
    __tablename__ = "book_plans"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    project_id: Mapped[str] = mapped_column(
        String(100),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    premise: Mapped[str] = mapped_column(Text, default="", server_default="")
    genre: Mapped[str] = mapped_column(String(100), default="", server_default="")
    total_volumes: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    notes_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    volumes: Mapped[list["VolumePlanRecord"]] = relationship(
        back_populates="book_plan", cascade="all, delete-orphan"
    )


class VolumePlanRecord(Base):
    __tablename__ = "volume_plans"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    book_plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("book_plans.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    volume_num: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    premise: Mapped[str] = mapped_column(Text, default="", server_default="")
    arc_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    notes_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    book_plan: Mapped["BookPlanRecord"] = relationship(back_populates="volumes")
    chapters: Mapped[list["ChapterPlanRecord"]] = relationship(
        back_populates="volume_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_volume_plans_book_volume", "book_plan_id", "volume_num", unique=True),
    )


class ChapterPlanRecord(Base):
    __tablename__ = "chapter_plans"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    volume_plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("volume_plans.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    chapter_num: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    volume_num: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    title: Mapped[str] = mapped_column(String(300), default="", server_default="")
    summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    hook: Mapped[str] = mapped_column(Text, default="", server_default="")
    tension_target: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    dialogue_goals_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    legacy_outline_text: Mapped[str] = mapped_column(Text, default="", server_default="")
    source_run_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    volume_plan: Mapped["VolumePlanRecord"] = relationship(back_populates="chapters")
    scene_beats: Mapped[list["SceneBeatRecord"]] = relationship(
        back_populates="chapter_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_chapter_plans_project_volume_chapter", "project_id", "volume_num", "chapter_num", unique=True),
    )


class SceneBeatRecord(Base):
    __tablename__ = "scene_beats"

    id: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        default=lambda: __import__("uuid").uuid4().hex,
    )
    chapter_plan_id: Mapped[str] = mapped_column(
        String(100), ForeignKey("chapter_plans.id", ondelete="CASCADE"), index=True
    )
    beat_index: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    beat_key: Mapped[str] = mapped_column(String(100), default="", server_default="")
    label: Mapped[str] = mapped_column(String(300), default="", server_default="")
    objective: Mapped[str] = mapped_column(Text, default="", server_default="")
    conflict: Mapped[str] = mapped_column(Text, default="", server_default="")
    outcome: Mapped[str] = mapped_column(Text, default="", server_default="")
    tension: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    location: Mapped[str] = mapped_column(String(200), default="", server_default="")
    characters_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    source_node_ids_json: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    estimated_words: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    user_id: Mapped[str] = mapped_column(
        String(100), default="local", server_default="local"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    chapter_plan: Mapped["ChapterPlanRecord"] = relationship(back_populates="scene_beats")

    __table_args__ = (
        Index("ix_scene_beats_chapter_index", "chapter_plan_id", "beat_index", unique=True),
    )
