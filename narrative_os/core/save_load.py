"""
core/save_load.py — Phase 3: 完整 SL（存档/读档）系统

三层结构：
  A. SavePoint — 快照存档（世界/角色/会话历史的完整快照）
  B. SoftRollback — 读档恢复（保留 memory_summary 防止完全失忆）
  C. DeadlockBreaker — 防死锁解套（检测+解套策略）
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from narrative_os.agents.interactive import InteractiveSession


# ------------------------------------------------------------------ #
# A. SavePoint — 快照存档                                               #
# ------------------------------------------------------------------ #

class SavePoint(BaseModel):
    """完整场景快照，用于 SL 系统的存/读档。"""
    save_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    project_id: str
    trigger: str = "manual"
    # "scene_start" / "major_decision" / "high_risk" / "character_death" / "manual"
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    world_snapshot: dict = Field(default_factory=dict)      # WorldState.model_dump()
    character_snapshots: dict = Field(default_factory=dict) # {name: CharacterState.model_dump()}
    session_history: list = Field(default_factory=list)     # TurnRecord 列表
    plot_position: str = ""                                  # 当前 PlotNode id
    memory_summary: str = ""  # 本存档点的记忆摘要（软回退时保留）
    scene_pressure: float = 5.0
    turn: int = 0


# ------------------------------------------------------------------ #
# SaveStore — 存档持久化（内存 + 文件）                                  #
# ------------------------------------------------------------------ #

class SaveStore:
    """管理一个 session 的多个 SavePoint（内存）。"""

    def __init__(self) -> None:
        self._saves: dict[str, SavePoint] = {}  # save_id → SavePoint

    def create(
        self,
        session: "InteractiveSession",
        trigger: str = "manual",
        world_snapshot: dict | None = None,
        character_snapshots: dict | None = None,
        plot_position: str = "",
        memory_summary: str = "",
    ) -> SavePoint:
        """创建并存储一个 SavePoint。"""
        sp = SavePoint(
            session_id=session.session_id,
            project_id=session.project_id,
            trigger=trigger,
            world_snapshot=world_snapshot or {},
            character_snapshots=character_snapshots or {},
            session_history=[r.model_dump() for r in session.history],
            plot_position=plot_position,
            memory_summary=memory_summary,
            scene_pressure=session.scene_pressure,
            turn=session.turn,
        )
        self._saves[sp.save_id] = sp
        return sp

    def list_saves(self, session_id: str) -> list[SavePoint]:
        return sorted(
            [s for s in self._saves.values() if s.session_id == session_id],
            key=lambda s: s.timestamp,
        )

    def get(self, save_id: str) -> SavePoint | None:
        return self._saves.get(save_id)

    def delete(self, save_id: str) -> bool:
        if save_id in self._saves:
            del self._saves[save_id]
            return True
        return False


# ------------------------------------------------------------------ #
# B. SoftRollback — 读档（保留 memory_summary）                         #
# ------------------------------------------------------------------ #

class SoftRollback:
    """
    读档恢复逻辑。
    恢复 session 到指定 SavePoint 的状态，但保留 memory_summary 以防完全失忆。
    """

    @staticmethod
    def restore(
        session: "InteractiveSession",
        save_point: SavePoint,
        inject_micro_perturbation: bool = True,
    ) -> "InteractiveSession":
        """
        将 session 恢复到 save_point 状态。

        Args:
            session: 要恢复的 InteractiveSession（in-place修改）
            save_point: 目标存档点
            inject_micro_perturbation: 是否注入微扰（防止完全一致路径重现）
        """
        from narrative_os.agents.interactive import TurnRecord

        # 恢复历史
        session.history = [
            TurnRecord.model_validate(r) for r in save_point.session_history
        ]
        session.turn = save_point.turn
        session.scene_pressure = save_point.scene_pressure

        # 保留 memory_summary（不完全失忆）
        if save_point.memory_summary:
            session.memory_summary_cache = save_point.memory_summary  # type: ignore[attr-defined]

        # 重置为 PING_PONG 阶段
        from narrative_os.agents.interactive import SessionPhase
        session.phase = SessionPhase.PING_PONG
        session.open_decision = None

        # 注入微扰提示（防止同路径死循环）
        if inject_micro_perturbation and save_point.memory_summary:
            from narrative_os.agents.interactive import TurnRecord as TR
            perturbation = TR(
                turn_id=session.turn,
                who="system",
                content=(
                    f"[系统提示] 读档恢复至存档「{save_point.save_id[:8]}」，"
                    f"场景记忆：{save_point.memory_summary[:80]}…"
                ),
                scene_pressure=session.scene_pressure,
                density=session.density,
                phase=SessionPhase.PING_PONG,
            )
            session.history.append(perturbation)

        return session


# ------------------------------------------------------------------ #
# C. DeadlockBreaker — 防死锁解套                                        #
# ------------------------------------------------------------------ #

class DeadlockCondition(str, Enum):
    NO_VIABLE_ACTIONS = "no_viable_actions"          # 角色无行动空间
    CHARACTER_STALEMATE = "character_stalemate"      # 角色互不妥协僵持
    WORLD_STUCK = "world_stuck"                      # 世界状态停滞不前
    PROLONGED_INVALID_INPUT = "prolonged_invalid_input"  # 长期无效输入


# 解套策略文本模板
_RESOLUTION_TEMPLATES: dict[DeadlockCondition, list[str]] = {
    DeadlockCondition.NO_VIABLE_ACTIONS: [
        "就在你陷入困境之际，远处传来一声异响，新的变局悄然而至……",
        "忽然，一个意外的变数打破了僵局——",
        "命运似乎不打算让局面就此停滞。一道新的力量介入了眼前的困境。",
    ],
    DeadlockCondition.CHARACTER_STALEMATE: [
        "双方的对峙在无声中被一个外来闯入者打断——",
        "就在两方僵持之时，一个中立的第三方出现了。",
        "时间流逝，沉默本身成为了另一种语言；直到外部的变化强制带来了新的可能。",
    ],
    DeadlockCondition.WORLD_STUCK: [
        "时间推进了数日……世界不会等待犹豫者。",
        "局势自然演化，无论你是否准备好，事件已经发生了改变——",
        "一场预料之外的天象/事件/来访打破了原本的停滞状态。",
    ],
    DeadlockCondition.PROLONGED_INVALID_INPUT: [
        "（系统提示）请选择：A. 等待观察 / B. 主动出击 / C. 撤退保全。",
        "（DM提示）当前情景需要你做出决断，以下三条路等待选择：\n[选项 A]：静待时机\n[选项 B]：果断行动\n[选项 C]：另辟蹊径",
        "等待太久会有代价——请从以下选项中选择你的行动：\n[选项 A]：出声\n[选项 B]：隐藏\n[选项 C]：撤离",
    ],
}

# 连续重复输入的最大容忍次数
_REPEAT_THRESHOLD = 3
# 无决策进展的最大连续轮数
_STAGNATION_THRESHOLD = 5


class DeadlockBreaker:
    """
    死锁检测与解套。
    调用 detect() 判断是否陷入死锁，调用 resolve() 生成解套叙事文本。
    """

    def detect(self, session: "InteractiveSession") -> DeadlockCondition | None:
        """
        检测是否存在死锁条件。
        返回第一个检测到的 DeadlockCondition，否则返回 None。
        """
        recent = session.history[-_STAGNATION_THRESHOLD:]
        if not recent:
            return None

        # -- 检测1：长期无效输入（用户连续输入相同/空内容）
        user_msgs = [t.content for t in recent if t.who == "user"]
        if len(user_msgs) >= _REPEAT_THRESHOLD:
            last_n = user_msgs[-_REPEAT_THRESHOLD:]
            if len(set(m.strip() for m in last_n if m.strip())) <= 1:
                return DeadlockCondition.PROLONGED_INVALID_INPUT

        # -- 检测2：角色僵持（DM 片段中连续出现互不妥协关键词）
        dm_msgs = [t.content for t in recent if t.who == "dm"]
        stalemate_keywords = {"僵持", "对峙", "拒绝", "不肯", "沉默", "无法推进", "陷入僵局"}
        stalemate_count = sum(
            1 for msg in dm_msgs if any(kw in msg for kw in stalemate_keywords)
        )
        if stalemate_count >= 3:
            return DeadlockCondition.CHARACTER_STALEMATE

        # -- 检测3：世界状态停滞（DM 片段中场景地点未变且回合数多）
        if len(session.history) >= 20 and session.scene_pressure <= 2.0:
            return DeadlockCondition.WORLD_STUCK

        # -- 检测4：无可行行动（DM 片段中含"无法"/"做不到"等超过2次）
        no_action_keywords = {"无法继续", "做不到", "没有办法", "无路可走", "陷入绝境"}
        no_action_count = sum(
            1 for msg in dm_msgs if any(kw in msg for kw in no_action_keywords)
        )
        if no_action_count >= 2:
            return DeadlockCondition.NO_VIABLE_ACTIONS

        return None

    async def resolve(
        self,
        condition: DeadlockCondition,
        session: "InteractiveSession",
    ) -> str:
        """
        生成解套叙事文本。
        优先使用 LLM 生成个性化解套，失败时降级到模板。
        """
        import random
        templates = _RESOLUTION_TEMPLATES.get(condition, [])
        fallback = templates[0] if templates else "局势发生了变化，新的机遇出现了。"

        try:
            from narrative_os.execution.llm_router import LLMRequest, LLMRouter, ModelTier
            router = LLMRouter()
            prompt = (
                f"TRPG 会话陷入死锁：{condition.value}。\n"
                f"最近场景压力：{session.scene_pressure:.1f}/10\n"
                f"最近 DM 叙述（最后150字）：{session.history[-1].content[-150:] if session.history else ''}\n"
                f"请生成一段50字以内的解套叙事，打破僵局，符合世界观设定。直接输出叙事文本，不要前缀。"
            )
            req = LLMRequest(
                task_type="deadlock_resolution",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=100,
                temperature=0.9,
                skill_name="deadlock_breaker",
                tier_override=ModelTier.SMALL,
            )
            resp = await router.call(req)
            text = resp.content.strip()
            if text:
                return text
        except Exception:
            pass

        return random.choice(templates) if templates else fallback


# ------------------------------------------------------------------ #
# 全局 SaveStore 注册表（session_id → SaveStore）                        #
# ------------------------------------------------------------------ #

_save_stores: dict[str, SaveStore] = {}


def get_save_store(session_id: str) -> SaveStore:
    """获取指定 session 的 SaveStore（不存在时自动创建）。"""
    if session_id not in _save_stores:
        _save_stores[session_id] = SaveStore()
    return _save_stores[session_id]
