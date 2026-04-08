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
    sandbox_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
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
    concept_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now
    )
