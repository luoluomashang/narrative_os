"""
agents/sandbox_simulator.py — Phase 3: 角色 Agenda 沙盘推演

职责：
  - 每轮互动后，对活跃角色（非玩家受控）根据 Drive + Social + Runtime 生成本轮 agenda
  - 角色之间可互相作用（无需用户参与）
  - 输出 AgendaDelta 列表

依赖：阶段二 CharacterState 四层模型 + 阶段一 WorldRepository（可选）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from narrative_os.core.interactive_modes import ControlMode
from narrative_os.execution.prompt_utils import plain_text_contract

if TYPE_CHECKING:
    from narrative_os.core.character import CharacterState
    from narrative_os.core.world import WorldState


# ------------------------------------------------------------------ #
# AgendaDelta                                                          #
# ------------------------------------------------------------------ #

class AgendaDelta(BaseModel):
    """单个角色本轮推演结果。"""
    character_name: str
    agenda_text: str = ""             # 本轮行动意图描述
    location_change: str | None = None
    relationship_updates: dict[str, float] = Field(default_factory=dict)
    # 简化关系变化 {target_name: delta}
    events_generated: list[str] = Field(default_factory=list)
    # 生成的世界事件描述


# ------------------------------------------------------------------ #
# SandboxSimulator                                                     #
# ------------------------------------------------------------------ #

class SandboxSimulator:
    """
    角色 Agenda 沙盘推演器。

    在 USER_DRIVEN/SEMI_AGENT 模式下，对非主角的活跃角色推演行动意图；
    在 DIRECTOR 模式下，可推演所有角色（包含主角）。
    """

    def __init__(self) -> None:
        from narrative_os.execution.llm_router import LLMRouter
        self._router = LLMRouter()

    async def simulate_turn(
        self,
        active_characters: "list[CharacterState]",
        world_state: "WorldState | None",
        recent_events: list[str],
        control_mode: ControlMode = ControlMode.USER_DRIVEN,
        protagonist_name: str = "",
    ) -> list[AgendaDelta]:
        """
        推演本轮所有非受控角色的 agenda。

        Args:
            active_characters: 本轮在场角色列表
            world_state: 当前世界状态（可选）
            recent_events: 最近事件列表（字符串）
            control_mode: 当前控制模式
            protagonist_name: 玩家主角名称（USER_DRIVEN 下跳过推演）

        Returns:
            每个被推演角色的 AgendaDelta 列表
        """
        results: list[AgendaDelta] = []

        for char in active_characters:
            # MODE1：纯用户驱动时，跳过主角推演
            if control_mode == ControlMode.USER_DRIVEN and char.name == protagonist_name:
                continue

            delta = await self._simulate_character(
                char, world_state, recent_events, control_mode
            )
            if delta:
                results.append(delta)

        return results

    async def _simulate_character(
        self,
        char: "CharacterState",
        world_state: "WorldState | None",
        recent_events: list[str],
        control_mode: ControlMode,
    ) -> AgendaDelta | None:
        """为单个角色生成本轮 agenda。优先 LLM，失败时使用 Drive 层规则推断。"""
        try:
            return await self._llm_simulate(char, world_state, recent_events, control_mode)
        except Exception:
            return self._heuristic_simulate(char, recent_events)

    async def _llm_simulate(
        self,
        char: "CharacterState",
        world_state: "WorldState | None",
        recent_events: list[str],
        control_mode: ControlMode,
    ) -> AgendaDelta:
        """用 LLM 推演角色 agenda。"""
        from narrative_os.execution.llm_router import LLMRequest, ModelTier

        # 构建角色摘要
        drive_text = ""
        if char.drive is not None:
            d = char.drive
            parts = []
            if d.core_desire:
                parts.append(f"欲望={d.core_desire}")
            if d.core_fear:
                parts.append(f"恐惧={d.core_fear}")
            if d.current_obsession:
                parts.append(f"执念={d.current_obsession}")
            if d.short_term_goal:
                parts.append(f"短期目标={d.short_term_goal}")
            drive_text = "，".join(parts)

        world_rules = ""
        if world_state is not None:
            world_rules = "；".join(world_state.rules_of_world[:3])

        events_text = "；".join(recent_events[-3:]) if recent_events else "无"

        prompt = "\n\n".join(
            [
                "\n".join(
                    [
                        f"角色：{char.name}（{char.personality or char.description or '无描述'}）",
                        f"Drive：{drive_text or '未设定'}",
                        f"当前情绪：{char.emotion}，当前弧光阶段：{char.arc_stage}",
                        f"世界规则（前3条）：{world_rules or '无'}",
                        f"最近事件：{events_text}",
                        f"控制模式：{control_mode.value}",
                    ]
                ),
                plain_text_contract(
                    "请推断该角色本轮会主动做什么（1-2句话，第三人称，不超过60字）。",
                    "如有位置变化，括号内注明；如有关系变化，在最后一行输出「[关系变化] 角色名:±0.1」。",
                    "直接输出推演结果，无需前缀。",
                ),
            ]
        )

        from narrative_os.execution.llm_router import LLMRouter
        router = LLMRouter()
        req = LLMRequest(
            task_type="agenda_simulation",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=120,
            temperature=0.75,
            skill_name="sandbox_simulator",
            tier_override=ModelTier.SMALL,
        )
        resp = await router.call(req)
        raw = resp.content.strip()

        # 解析关系变化
        rel_updates: dict[str, float] = {}
        lines = raw.splitlines()
        agenda_lines = []
        for line in lines:
            if line.startswith("[关系变化]"):
                for part in line.replace("[关系变化]", "").split(","):
                    part = part.strip()
                    if ":" in part:
                        name, val = part.rsplit(":", 1)
                        try:
                            rel_updates[name.strip()] = float(val.strip())
                        except ValueError:
                            pass
            else:
                agenda_lines.append(line)

        agenda_text = " ".join(agenda_lines).strip()

        # 解析位置变化（括号内容）
        import re
        location_match = re.search(r"（移至(.+?)）|（前往(.+?)）", agenda_text)
        location_change = None
        if location_match:
            location_change = location_match.group(1) or location_match.group(2)

        return AgendaDelta(
            character_name=char.name,
            agenda_text=agenda_text,
            location_change=location_change,
            relationship_updates=rel_updates,
            events_generated=[agenda_text] if agenda_text else [],
        )

    def _heuristic_simulate(
        self,
        char: "CharacterState",
        recent_events: list[str],
    ) -> AgendaDelta:
        """基于 Drive 层规则的启发式推断（LLM 不可用时的降级）。"""
        agenda = ""
        if char.drive is not None:
            d = char.drive
            if d.current_obsession:
                agenda = f"{char.name} 执着于「{d.current_obsession}」，继续追求目标。"
            elif d.short_term_goal:
                agenda = f"{char.name} 正朝着「{d.short_term_goal}」行动。"
        if not agenda:
            agenda = f"{char.name} 审视局势，保持警戒。"
        return AgendaDelta(character_name=char.name, agenda_text=agenda)
