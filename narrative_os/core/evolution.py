"""
core/evolution.py — Phase 4.2: 变更集与 Canon 提交系统

三层结构：
  WorldChange      — 单条变更记录
  WorldChangeSet   — 变更集（一次会话/流水线产生的所有变更）
  CanonCommit      — 正史提交控制器（审批 / 驳回 / 提交到正史）

三种结束方式（用于 TRPG 会话结束时）：
  session_only     — 仅保存会话记录，不影响主线
  draft_chapter    — 生成候选章节草稿（人工确认后再接受）
  canon_chapter    — 直接采纳为正史章节（需二次确认标志）
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from narrative_os.core.world_sandbox import WorldSandboxData


# ------------------------------------------------------------------ #
# 枚举                                                                  #
# ------------------------------------------------------------------ #

class ChangeSource(str, Enum):
    PIPELINE = "pipeline"           # 写作流水线产生的变更
    INTERACTIVE = "interactive"     # 互动模式（TRPG）产生的变更
    SANDBOX_SIM = "sandbox_sim"     # SandboxSimulator 推演产生
    MANUAL = "manual"               # 人工手动指定


class ChangeTag(str, Enum):
    RUNTIME_ONLY = "runtime_only"           # 临时，不落盘
    DRAFT = "draft"                         # 草稿，待审
    CANON_PENDING = "canon_pending"         # 待确认进入正史
    CANON_CONFIRMED = "canon_confirmed"     # 已确认正史


class SessionCommitMode(str, Enum):
    SESSION_ONLY = "session_only"       # 仅保存会话记录
    DRAFT_CHAPTER = "draft_chapter"     # 生成候选章节草稿
    CANON_CHAPTER = "canon_chapter"     # 直接采纳为正史章节


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class WorldChange(BaseModel):
    """单条世界状态变更记录。"""
    change_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: ChangeSource = ChangeSource.MANUAL
    chapter: int = 0
    tag: ChangeTag = ChangeTag.DRAFT
    change_type: str = ""  # "faction_relation" / "new_location" / "timeline_event" / "rule_addition"
    description: str = ""
    before_snapshot: dict | None = None
    after_value: dict = Field(default_factory=dict)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class WorldChangeSet(BaseModel):
    """一次生产动作（会话/流水线）产生的变更集。"""
    changeset_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    session_id: str | None = None
    source: ChangeSource = ChangeSource.MANUAL
    changes: list[WorldChange] = Field(default_factory=list)
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    commit_mode: SessionCommitMode = SessionCommitMode.SESSION_ONLY
    # 草稿章节内容（draft_chapter / canon_chapter 模式时填充）
    draft_content: str = ""
    # 二次确认标志（canon_chapter 必须为 True 才执行提交）
    canon_confirmed: bool = False

    def pending_changes(self) -> list[WorldChange]:
        """返回待审批的变更（tag=DRAFT 或 CANON_PENDING）。"""
        return [c for c in self.changes if c.tag in (ChangeTag.DRAFT, ChangeTag.CANON_PENDING)]

    def confirmed_changes(self) -> list[WorldChange]:
        """返回已确认的变更（tag=CANON_CONFIRMED）。"""
        return [c for c in self.changes if c.tag == ChangeTag.CANON_CONFIRMED]


# ------------------------------------------------------------------ #
# CanonCommit                                                           #
# ------------------------------------------------------------------ #

class CanonCommit:
    """
    正史提交控制器。

    功能：
      - create_changeset()  创建新变更集
      - approve_change()    审批单条变更
      - approve_all()       批量审批变更集内所有变更
      - reject_change()     驳回单条变更
      - commit_to_canon()   将已确认变更写入正史（更新 sandbox 状态）
    """

    def __init__(self) -> None:
        # project_id → list[WorldChangeSet]
        self._changesets: dict[str, list[WorldChangeSet]] = {}
        # change_id → WorldChange（全局索引）
        self._changes_index: dict[str, WorldChange] = {}
        # changeset_id → WorldChangeSet（快速查询）
        self._changesets_index: dict[str, WorldChangeSet] = {}

    # ---------------------------------------------------------------- #
    # 创建变更集                                                         #
    # ---------------------------------------------------------------- #

    def create_changeset(
        self,
        project_id: str,
        source: ChangeSource = ChangeSource.MANUAL,
        session_id: str | None = None,
        changes: list[WorldChange] | None = None,
        commit_mode: SessionCommitMode = SessionCommitMode.SESSION_ONLY,
        draft_content: str = "",
    ) -> WorldChangeSet:
        """创建一个新的变更集并注册到内存索引。"""
        cs = WorldChangeSet(
            project_id=project_id,
            session_id=session_id,
            source=source,
            changes=changes or [],
            commit_mode=commit_mode,
            draft_content=draft_content,
        )
        self._changesets.setdefault(project_id, []).append(cs)
        self._changesets_index[cs.changeset_id] = cs
        for c in cs.changes:
            self._changes_index[c.change_id] = c
        return cs

    def add_change(self, changeset_id: str, change: WorldChange) -> WorldChange:
        """向已有变更集追加一条变更。"""
        cs = self._changesets_index.get(changeset_id)
        if cs is None:
            raise KeyError(f"变更集 '{changeset_id}' 不存在")
        cs.changes.append(change)
        self._changes_index[change.change_id] = change
        return change

    # ---------------------------------------------------------------- #
    # 列表查询                                                           #
    # ---------------------------------------------------------------- #

    def list_changesets(self, project_id: str) -> list[WorldChangeSet]:
        return self._changesets.get(project_id, [])

    def get_changeset(self, changeset_id: str) -> WorldChangeSet | None:
        return self._changesets_index.get(changeset_id)

    # ---------------------------------------------------------------- #
    # 审批 / 驳回                                                        #
    # ---------------------------------------------------------------- #

    def approve_change(self, change_id: str) -> WorldChange:
        """审批单条变更（DRAFT/RUNTIME_ONLY → CANON_PENDING）。"""
        change = self._changes_index.get(change_id)
        if change is None:
            raise KeyError(f"变更 '{change_id}' 不存在")
        change.tag = ChangeTag.CANON_PENDING
        return change

    def approve_all(self, changeset_id: str) -> int:
        """批量审批变更集中的所有草稿变更，返回审批条数。"""
        cs = self._changesets_index.get(changeset_id)
        if cs is None:
            raise KeyError(f"变更集 '{changeset_id}' 不存在")
        count = 0
        for c in cs.changes:
            if c.tag in (ChangeTag.DRAFT, ChangeTag.RUNTIME_ONLY):
                c.tag = ChangeTag.CANON_PENDING
                count += 1
        return count

    def reject_change(self, change_id: str) -> WorldChange:
        """驳回单条变更（→ RUNTIME_ONLY，不进正史）。"""
        change = self._changes_index.get(change_id)
        if change is None:
            raise KeyError(f"变更 '{change_id}' 不存在")
        change.tag = ChangeTag.RUNTIME_ONLY
        return change

    # ---------------------------------------------------------------- #
    # 提交正史                                                           #
    # ---------------------------------------------------------------- #

    def commit_to_canon(
        self,
        changeset_id: str,
        sandbox: "WorldSandboxData | None" = None,
    ) -> list[WorldChange]:
        """
        将 CANON_PENDING 变更提交为 CANON_CONFIRMED，并可选地更新 sandbox。

        commit_mode == canon_chapter 时，canon_confirmed 必须为 True。

        返回已提交的变更列表。
        """
        cs = self._changesets_index.get(changeset_id)
        if cs is None:
            raise KeyError(f"变更集 '{changeset_id}' 不存在")

        # canon_chapter 需要二次确认
        if cs.commit_mode == SessionCommitMode.CANON_CHAPTER and not cs.canon_confirmed:
            raise PermissionError("canon_chapter 提交需要先设置 canon_confirmed=True")

        committed: list[WorldChange] = []
        for c in cs.changes:
            if c.tag == ChangeTag.CANON_PENDING:
                c.tag = ChangeTag.CANON_CONFIRMED
                committed.append(c)
                # 应用到 sandbox（可选）
                if sandbox is not None:
                    _apply_to_sandbox(c, sandbox)

        if committed:
            self._persist_committed_changes(cs.project_id, committed)

        return committed

    def commit_session(
        self,
        project_id: str,
        session_id: str,
        mode: SessionCommitMode,
        draft_content: str = "",
        changes: list[WorldChange] | None = None,
        require_canon_confirm: bool = False,
    ) -> WorldChangeSet:
        """
        互动会话结束时的提交入口（三种方式封装）。

        - session_only:   仅保存会话记录，不影响主线
        - draft_chapter:  生成候选草稿，不自动采纳
        - canon_chapter:  require_canon_confirm=True 才执行正史写入
        """
        cs = self.create_changeset(
            project_id=project_id,
            source=ChangeSource.INTERACTIVE,
            session_id=session_id,
            changes=changes,
            commit_mode=mode,
            draft_content=draft_content,
        )

        if mode == SessionCommitMode.SESSION_ONLY:
            # 仅归档，不提升变更 tag
            pass
        elif mode == SessionCommitMode.DRAFT_CHAPTER:
            # 阶段五：章节草稿也统一进入 CANON_PENDING，等待审批后回流主线
            for c in cs.changes:
                if c.tag in (ChangeTag.RUNTIME_ONLY, ChangeTag.DRAFT):
                    c.tag = ChangeTag.CANON_PENDING
        elif mode == SessionCommitMode.CANON_CHAPTER:
            # 推进到 CANON_PENDING，但需要二次确认才执行 commit
            for c in cs.changes:
                c.tag = ChangeTag.CANON_PENDING
            if require_canon_confirm:
                cs.canon_confirmed = True

        return cs

    def _persist_committed_changes(
        self,
        project_id: str,
        changes: list[WorldChange],
    ) -> None:
        try:
            from narrative_os.core.world_repository import get_world_repository

            repo = get_world_repository()
            world = repo.get_world_state(project_id)
            for change in changes:
                _apply_to_world_state(change, world)
            repo.save_runtime_world_state(project_id, world)
        except Exception:
            return


# ------------------------------------------------------------------ #
# 内部工具                                                              #
# ------------------------------------------------------------------ #

def _apply_to_sandbox(change: WorldChange, sandbox: "WorldSandboxData") -> None:
    """将单条 WorldChange 应用到 WorldSandboxData（简化版）。"""
    ct = change.change_type

    if ct == "rule_addition":
        rule_text = change.after_value.get("rule", change.description)
        if rule_text and rule_text not in sandbox.world_rules:
            sandbox.world_rules.append(rule_text)

    elif ct == "faction_relation":
        # 仅记录到 description；完整实现需操作 relations 列表
        pass

    elif ct == "timeline_event":
        from narrative_os.core.world_sandbox import TimelineSandboxEvent
        try:
            ev = TimelineSandboxEvent(**change.after_value)
            sandbox.timeline_events.append(ev)
        except Exception:
            pass


def _apply_to_world_state(change: WorldChange, world: Any) -> None:
    """将单条 WorldChange 应用到 WorldState。"""
    ct = change.change_type

    if ct == "rule_addition":
        rule_text = change.after_value.get("rule", change.description)
        if rule_text:
            world.add_world_rule(rule_text)
        return

    if ct == "timeline_event":
        description = change.after_value.get("event", change.description)
        world.advance_timeline(change.chapter or 0, event=description)
        return

    if ct == "faction_relation":
        source_id = change.after_value.get("source_faction")
        target_id = change.after_value.get("target_faction")
        value = change.after_value.get("relation")
        if source_id in getattr(world, "factions", {}) and target_id:
            try:
                world.factions[source_id].update_hostility(target_id, float(value))
            except Exception:
                pass


# ------------------------------------------------------------------ #
# 单例工厂                                                              #
# ------------------------------------------------------------------ #

_canon_commit_instances: dict[str, CanonCommit] = {}


def get_canon_commit(project_id: str) -> CanonCommit:
    """每个 project 使用独立 CanonCommit 实例（内存单例）。"""
    if project_id not in _canon_commit_instances:
        _canon_commit_instances[project_id] = CanonCommit()
    return _canon_commit_instances[project_id]
