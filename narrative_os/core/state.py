"""
core/state.py — Phase 1: 版本控制与状态持久化

职责：
  - 管理整部小说的"全量运行时状态"（PlotGraph + CharacterState[] + WorldState）
  - 每章生成完成后打版本快照（version = chapter number）
  - 支持"时光倒流"：回滚到任意章节的全部状态
  - 持久化格式：JSON（Pydantic .model_dump() / .model_validate()）
  - 从 state_template.json（v8.5 schema）迁移

目录结构（.narrative_os/{project_id}/）：
  state.json            — 当前状态（最新版本）
  versions/
    v{chapter:04d}.json — 每章快照
  knowledge_base.json   — KB（由 Maintenance Agent 更新）
"""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from narrative_os.infra.config import settings


# ------------------------------------------------------------------ #
# DB 辅助协程（延迟 import 避免循环）                                    #
# ------------------------------------------------------------------ #

async def _upsert_project_to_db(project_id: str, project_name: str) -> None:
    """幂等写入或更新项目记录到 DB。"""
    try:
        from narrative_os.infra.database import AsyncSessionLocal  # noqa: PLC0415
        from narrative_os.infra.models import Project  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415
        async with AsyncSessionLocal() as db:
            row = await db.get(Project, project_id)
            if row is None:
                db.add(Project(id=project_id, title=project_name or project_id))
            else:
                if project_name and row.title != project_name:
                    row.title = project_name
            await db.commit()
    except Exception:
        pass  # DB 写失败不影响文件系统主路径


async def _persist_chapter_to_db(
    project_id: str,
    chapter_num: int,
    volume: int,
    text: str,
    word_count: int,
    quality_score: float,
    hook_score: float,
    summary: str,
    source: str,
    plot_graph_json: str,
    characters_json: str,
    world_json: str,
) -> None:
    """写入章节文本 + 状态快照到 DB。"""
    try:
        from narrative_os.infra.database import AsyncSessionLocal  # noqa: PLC0415
        from narrative_os.infra.models import Chapter, StateSnapshot  # noqa: PLC0415
        from sqlalchemy import select  # noqa: PLC0415
        async with AsyncSessionLocal() as db:
            # 章节：存在则更新，否则新建
            stmt = select(Chapter).where(
                Chapter.project_id == project_id,
                Chapter.chapter_num == chapter_num,
            )
            row = (await db.execute(stmt)).scalar_one_or_none()
            if row is None:
                db.add(Chapter(
                    project_id=project_id,
                    chapter_num=chapter_num,
                    volume=volume,
                    text=text,
                    word_count=word_count,
                    quality_score=quality_score,
                    hook_score=hook_score,
                    summary=summary,
                    source=source,
                ))
            else:
                row.text = text
                row.word_count = word_count
                row.quality_score = quality_score
                row.hook_score = hook_score
                row.summary = summary
            # 快照：每章新建一条
            db.add(StateSnapshot(
                project_id=project_id,
                chapter_num=chapter_num,
                plot_graph_json=plot_graph_json,
                characters_json=characters_json,
                world_json=world_json,
            ))
            await db.commit()
    except Exception:
        pass


async def _rollback_chapters_in_db(project_id: str, rollback_to_chapter: int) -> None:
    """删除 DB 中 chapter_num > rollback_to_chapter 的章节和快照记录。"""
    try:
        from narrative_os.infra.database import AsyncSessionLocal  # noqa: PLC0415
        from narrative_os.infra.models import Chapter, StateSnapshot  # noqa: PLC0415
        from sqlalchemy import delete  # noqa: PLC0415
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(Chapter).where(
                    Chapter.project_id == project_id,
                    Chapter.chapter_num > rollback_to_chapter,
                )
            )
            await db.execute(
                delete(StateSnapshot).where(
                    StateSnapshot.project_id == project_id,
                    StateSnapshot.chapter_num > rollback_to_chapter,
                )
            )
            await db.commit()
    except Exception:
        pass


# ------------------------------------------------------------------ #
# NarrativeState — 全量运行时状态                                     #
# ------------------------------------------------------------------ #

class ChapterMeta(BaseModel):
    """一章的元数据（质量评分 + 摘要）。"""
    chapter: int
    summary: str = ""
    quality_score: float = 0.0
    hook_score: float = 0.0
    word_count: int = 0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class WorkflowStep(str):
    GENESIS = "genesis"
    PLANNING = "planning"
    KB_INIT = "kb_init"
    SCENE_PLAN = "scene_plan"
    WRITING = "writing"
    HUMANIZE = "humanize"
    DONE = "done"


class NarrativeState(BaseModel):
    """
    全量运行时状态 — 小说项目的"心跳"。

    对应 state_template.json v8.5 schema，增加了 Narrative OS 新字段。
    """
    project_id: str
    project_name: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # 工作流进度
    current_step: str = WorkflowStep.GENESIS
    current_chapter: int = 0
    current_volume: int = 1
    current_cycle_id: str = ""

    # 章节元数据索引
    chapters: list[ChapterMeta] = Field(default_factory=list)

    # 规划产出（引用 outline/ 目录下的文件路径）
    one_sentence: str = ""
    one_paragraph: str = ""
    genre_tags: list[str] = Field(default_factory=list)

    # 质量追踪（偏移警报状态）
    consecutive_no_payoff: int = 0    # 连续无爽点章数
    consecutive_hook_fail: int = 0    # 连续钩子失败章数
    consecutive_low_words: int = 0    # 连续低字数章数

    # Token 消耗统计
    total_tokens_used: int = 0

    # 用户确认检查点（Human-in-the-Loop）
    last_confirmed_step: str = ""
    pending_approval: bool = False
    approval_context: dict[str, Any] = Field(default_factory=dict)

    # 序列化时排除 snapshot_history（太重，存在 versions/ 目录）
    model_config = {"frozen": False}

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------ #
# StateManager                                                         #
# ------------------------------------------------------------------ #

class StateManager:
    """
    小说项目状态管理器。

    使用方式：
        sm = StateManager(project_id="my_novel")
        sm.initialize()                   # 创建 .narrative_os/my_novel/ 目录
        sm.save_state()                   # 保存当前状态
        sm.commit_chapter(chapter=1, ...)  # 打章节快照
        sm.rollback(chapter=1)            # 回滚到章1状态
    """

    def __init__(self, project_id: str, base_dir: str | None = None) -> None:
        self.project_id = project_id
        _base = Path(base_dir or settings.state_dir)
        self._dir = _base / project_id
        self._versions_dir = self._dir / "versions"
        self._state_path = self._dir / "state.json"
        self._kb_path = self._dir / "knowledge_base.json"
        self.state: NarrativeState | None = None

    # ---------------------------------------------------------------- #
    # Lifecycle                                                          #
    # ---------------------------------------------------------------- #

    def initialize(self, project_name: str = "", force: bool = False) -> NarrativeState:
        """
        初始化项目目录。
        force=True 时重建（清空已有状态）。
        """
        if self._dir.exists() and not force:
            # 已存在 → 加载
            return self.load_state()

        if force and self._dir.exists():
            shutil.rmtree(self._dir)

        self._dir.mkdir(parents=True, exist_ok=True)
        self._versions_dir.mkdir(parents=True, exist_ok=True)
        (self._dir / "chapters").mkdir(exist_ok=True)
        (self._dir / "outlines").mkdir(exist_ok=True)
        (self._dir / "scenes").mkdir(exist_ok=True)
        (self._dir / "logs").mkdir(exist_ok=True)

        self.state = NarrativeState(
            project_id=self.project_id,
            project_name=project_name or self.project_id,
        )
        self.save_state()
        # 双写 DB（fire-and-forget，不阻断）
        try:
            from narrative_os.infra.database import fire_and_forget  # noqa: PLC0415
            fire_and_forget(_upsert_project_to_db(self.project_id, project_name or self.project_id))
        except Exception:
            pass
        return self.state

    def load_state(self) -> NarrativeState:
        if not self._state_path.exists():
            raise FileNotFoundError(
                f"状态文件不存在: {self._state_path}\n"
                "请先调用 StateManager.initialize() 初始化项目。"
            )
        self.state = NarrativeState.model_validate_json(
            self._state_path.read_text(encoding="utf-8")
        )
        return self.state

    def save_state(self) -> None:
        if self.state is None:
            raise RuntimeError("状态未初始化，请先调用 initialize() 或 load_state()")
        self.state.touch()
        tmp = self._state_path.with_suffix(".tmp")
        tmp.write_text(
            self.state.model_dump_json(indent=2), encoding="utf-8"
        )
        tmp.replace(self._state_path)  # 原子替换，避免写入中断损坏

    # ---------------------------------------------------------------- #
    # Chapter Versioning                                                 #
    # ---------------------------------------------------------------- #

    def commit_chapter(
        self,
        chapter: int,
        *,
        plot_graph_dict: dict[str, Any] | None = None,
        characters_dict: dict[str, Any] | None = None,
        world_dict: dict[str, Any] | None = None,
        chapter_meta: ChapterMeta | None = None,
    ) -> Path:
        """
        提交章节快照（打版本号）。
        将 PlotGraph + CharacterState[] + WorldState 序列化为 versions/v{chapter:04d}.json。

        Maintenance Agent 在每章完成后调用此方法。
        """
        if self.state is None:
            raise RuntimeError("StateManager 未初始化")

        snapshot = {
            "version": chapter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "project_id": self.project_id,
            "plot_graph": plot_graph_dict or {},
            "characters": characters_dict or {},
            "world": world_dict or {},
        }
        version_path = self._versions_dir / f"v{chapter:04d}.json"
        version_path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 更新 state
        self.state.current_chapter = chapter
        if chapter_meta:
            # 替换或追加
            self.state.chapters = [
                m for m in self.state.chapters if m.chapter != chapter
            ]
            self.state.chapters.append(chapter_meta)
        self.save_state()

        # 双写 DB（fire-and-forget）
        try:
            from narrative_os.infra.database import fire_and_forget  # noqa: PLC0415
            _chapter_text = self.load_chapter_text(chapter) or ""
            _meta = chapter_meta or ChapterMeta(chapter=chapter)
            fire_and_forget(_persist_chapter_to_db(
                project_id=self.project_id,
                chapter_num=chapter,
                volume=snapshot.get("chapter_meta", {}).get("volume", 1) if "chapter_meta" in snapshot else 1,
                text=_chapter_text,
                word_count=_meta.word_count,
                quality_score=_meta.quality_score,
                hook_score=_meta.hook_score,
                summary=_meta.summary,
                source="pipeline",
                plot_graph_json=json.dumps(plot_graph_dict or {}, ensure_ascii=False),
                characters_json=json.dumps(characters_dict or {}, ensure_ascii=False),
                world_json=json.dumps(world_dict or {}, ensure_ascii=False),
            ))
        except Exception:
            pass

        return version_path

    def rollback(self, chapter: int) -> dict[str, Any]:
        """
        回滚到指定章节的快照（时光倒流）。
        返回快照 dict，由调用方重建 PlotGraph / CharacterState[] / WorldState。
        """
        version_path = self._versions_dir / f"v{chapter:04d}.json"
        if not version_path.exists():
            raise FileNotFoundError(f"版本快照不存在: {version_path}")
        snapshot = json.loads(version_path.read_text(encoding="utf-8"))
        # 更新当前 state 的章节指针
        if self.state:
            self.state.current_chapter = chapter
            # 截断章节元数据
            self.state.chapters = [m for m in self.state.chapters if m.chapter <= chapter]
            self.save_state()
        # 双写 DB（删除章节 > rollback_to）
        try:
            from narrative_os.infra.database import fire_and_forget  # noqa: PLC0415
            fire_and_forget(_rollback_chapters_in_db(self.project_id, chapter))
        except Exception:
            pass
        return snapshot

    def list_versions(self) -> list[int]:
        """返回已有版本的章节号列表（升序）。"""
        versions = []
        for p in sorted(self._versions_dir.glob("v*.json")):
            try:
                versions.append(int(p.stem[1:]))
            except ValueError:
                pass
        return versions

    # ---------------------------------------------------------------- #
    # Human-in-the-Loop 确认检查点                                     #
    # ---------------------------------------------------------------- #

    def request_approval(self, context: dict[str, Any]) -> None:
        """触发用户确认检查点（暂停自动流程）。"""
        if self.state is None:
            return
        self.state.pending_approval = True
        self.state.approval_context = context
        self.save_state()

    def approve(self, approved_step: str) -> None:
        """用户确认后，清除 pending_approval 标志并记录已确认步骤。"""
        if self.state is None:
            return
        self.state.pending_approval = False
        self.state.last_confirmed_step = approved_step
        self.state.approval_context = {}
        self.save_state()

    def is_pending_approval(self) -> bool:
        return bool(self.state and self.state.pending_approval)

    # ---------------------------------------------------------------- #
    # Knowledge Base                                                     #
    # ---------------------------------------------------------------- #

    def load_kb(self) -> dict[str, Any]:
        if not self._kb_path.exists():
            return {}
        return json.loads(self._kb_path.read_text(encoding="utf-8"))

    def save_kb(self, kb: dict[str, Any]) -> None:
        self._kb_path.write_text(
            json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def get_last_hook(self, chapter: int | None = None) -> str:
        """返回指定章节或最近一章的 hook。"""
        kb = self.load_kb()
        target_chapter = chapter
        if target_chapter is None:
            if self.state is None:
                try:
                    self.load_state()
                except FileNotFoundError:
                    return str(kb.get("last_hook", "") or "")
            target_chapter = self.state.current_chapter if self.state is not None else 0

        if target_chapter <= 0:
            return str(kb.get("last_hook", "") or "")

        return str(
            kb.get(f"chapter_{target_chapter}_hook")
            or kb.get("last_hook")
            or ""
        )

    def save_last_hook(self, chapter: int, hook_text: str) -> None:
        """持久化章节 hook，供下一章 Writer 消费。"""
        kb = self.load_kb()
        kb[f"chapter_{chapter}_hook"] = hook_text
        kb["last_hook"] = hook_text
        self.save_kb(kb)

    # ---------------------------------------------------------------- #
    # Paths                                                              #
    # ---------------------------------------------------------------- #

    def chapter_path(self, chapter: int) -> Path:
        return self._dir / "chapters" / f"chapter_{chapter:04d}.md"

    def save_chapter_text(self, chapter: int, text: str) -> Path:
        """将章节文本写入磁盘，返回文件路径。"""
        path = self.chapter_path(chapter)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def load_chapter_text(self, chapter: int) -> str | None:
        """读取章节文本，不存在时返回 None。"""
        path = self.chapter_path(chapter)
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def list_chapter_files(self) -> list[int]:
        """返回已保存的章节编号列表（升序）。"""
        chapters_dir = self._dir / "chapters"
        if not chapters_dir.exists():
            return []
        result = []
        for f in chapters_dir.glob("chapter_*.md"):
            try:
                n = int(f.stem.split("_")[1])
                result.append(n)
            except (IndexError, ValueError):
                pass
        return sorted(result)

    def outline_path(self, name: str) -> Path:
        return self._dir / "outlines" / f"{name}.md"

    def scene_path(self, cycle_id: str, chapter: int) -> Path:
        return self._dir / "scenes" / cycle_id / f"chapter_{chapter:04d}.md"

    def __repr__(self) -> str:
        chapter = self.state.current_chapter if self.state else "?"
        return f"StateManager(project={self.project_id!r}, chapter={chapter})"
