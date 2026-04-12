"""
execution/narrative_compiler.py — Phase 4.3: 叙事编译中台（NarrativeCompiler）

在现有 ContextBuilder 9-Gate 基础上新增：
  Gate 10  世界书 Lore 检索注入（按当前场景/角色/地点召回相关词条 summary）
  Gate 11  互动控制层注入（当前控制模式、AI 接管范围）

新特性：
  - token 预算裁剪：超出预算时优先裁剪低优先级 Gate
  - 支持两种输出包：AuthoringRuntimePackage / InteractiveRuntimePackage

迁移策略：
  NarrativeCompiler 新建，现有 ContextBuilder 调用保持不变。
  NarrativeCompiler.compile_authoring() 内部调用 ContextBuilder.build() 并叠加 Gate 10。
  NarrativeCompiler.compile_interactive() 叠加 Gate 10 + 11。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from narrative_os.execution.context_builder import (
    ChapterTarget,
    ContextBuilder,
    WriteContext,
)

if TYPE_CHECKING:
    from narrative_os.agents.interactive import InteractiveSession
    from narrative_os.core.character import CharacterState
    from narrative_os.core.interactive_modes import ControlMode
    from narrative_os.core.lorebook import LoreEntry, Lorebook
    from narrative_os.core.memory import MemorySystem
    from narrative_os.core.plot import PlotGraph
    from narrative_os.core.world import WorldState


# ------------------------------------------------------------------ #
# 输出包模型                                                            #
# ------------------------------------------------------------------ #

class LoreInjection(BaseModel):
    """Gate 10 注入的 Lore 片段（summary 列表）。"""
    entries: list[dict[str, str]] = Field(default_factory=list)
    # [{"title": ..., "summary": ..., "type": ...}]
    total_tokens_estimate: int = 0

    def to_prompt_block(self) -> str:
        if not self.entries:
            return ""
        lines = ["## 世界知识（Lorebook 注入）"]
        for e in self.entries:
            lines.append(f"**{e.get('title', '')}**（{e.get('type', '')}）：{e.get('summary', '')}")
        return "\n".join(lines) + "\n"


class ControlLayerInjection(BaseModel):
    """Gate 11 注入的互动控制层信息。"""
    control_mode: str = ""
    ai_controlled_characters: list[str] = Field(default_factory=list)
    allow_protagonist_proxy: bool = False
    director_intervention: bool = False

    def to_prompt_block(self) -> str:
        lines = ["## 互动控制层（Gate 11）"]
        lines.append(f"控制模式：{self.control_mode}")
        if self.ai_controlled_characters:
            lines.append(f"AI 接管角色：{'、'.join(self.ai_controlled_characters)}")
        lines.append(f"主角代理：{'允许' if self.allow_protagonist_proxy else '禁止'}")
        if self.director_intervention:
            lines.append("导演干预：激活")
        return "\n".join(lines) + "\n"


class AuthoringInputError(ValueError):
    """写作模式编译前置条件不满足。"""


class AuthoringRuntimePackage(BaseModel):
    """写作模式编译输出包。"""
    project_id: str
    chapter: int
    write_context: WriteContext
    previous_hook: str = ""
    current_volume_goal: str = ""
    author_memory_anchors: list[str] = Field(default_factory=list)
    lore_injection: LoreInjection = Field(default_factory=LoreInjection)
    # 预算裁剪摘要
    gates_trimmed: list[str] = Field(default_factory=list)
    total_token_estimate: int = 0

    @property
    def chapter_target(self) -> ChapterTarget:
        return self.write_context.chapter_target

    @property
    def long_term_anchors(self) -> list[str]:
        return self.write_context.long_term_anchors

    @property
    def short_term_memory(self) -> list[str]:
        return self.write_context.short_term_memory

    def to_system_prompt(self) -> str:
        """合并 WriteContext + Lore 注入，输出完整 system prompt。"""
        base = self.write_context.to_system_prompt()
        lore_block = self.lore_injection.to_prompt_block()
        if lore_block:
            base = base + "\n" + lore_block
        if self.gates_trimmed:
            base += f"\n<!-- 裁剪的 Gate: {', '.join(self.gates_trimmed)} -->"
        return base


class InteractiveRuntimePackage(BaseModel):
    """互动模式编译输出包。"""
    project_id: str
    session_id: str
    write_context: WriteContext
    lore_injection: LoreInjection = Field(default_factory=LoreInjection)
    control_layer: ControlLayerInjection = Field(default_factory=ControlLayerInjection)
    gates_trimmed: list[str] = Field(default_factory=list)
    total_token_estimate: int = 0

    def to_system_prompt(self) -> str:
        base = self.write_context.to_system_prompt()
        lore_block = self.lore_injection.to_prompt_block()
        ctrl_block = self.control_layer.to_prompt_block()
        if lore_block:
            base = base + "\n" + lore_block
        if ctrl_block:
            base = base + "\n" + ctrl_block
        if self.gates_trimmed:
            base += f"\n<!-- 裁剪的 Gate: {', '.join(self.gates_trimmed)} -->"
        return base


# ------------------------------------------------------------------ #
# NarrativeCompiler                                                     #
# ------------------------------------------------------------------ #

# Gate 优先级（数字越小优先级越高，裁剪时从大到小删除）
_GATE_PRIORITY: dict[str, int] = {
    "gate1_chapter": 0,
    "gate2_plot": 1,
    "gate3_characters": 2,
    "gate4_world": 3,
    "gate7_constraints": 4,
    "gate10_lore": 5,
    "gate5_short_memory": 6,
    "gate9_style": 7,
    "gate6_long_term": 8,
    "gate11_control": 9,   # 互动模式专用，最低
}

# 各 Gate 的粗略 token 估算（字符数 / 3.5 ≈ tokens）
_GATE_TOKEN_ESTIMATES: dict[str, int] = {
    "gate1_chapter": 120,
    "gate2_plot": 300,
    "gate3_characters": 400,
    "gate4_world": 200,
    "gate7_constraints": 250,
    "gate10_lore": 500,
    "gate5_short_memory": 400,
    "gate9_style": 150,
    "gate6_long_term": 300,
    "gate11_control": 80,
}


class NarrativeCompiler:
    """
    叙事编译中台。

    比 ContextBuilder 多两个 Gate（10, 11），支持 token 预算裁剪。
    写作模式调用 compile_authoring()，互动模式调用 compile_interactive()。
    """

    def __init__(self) -> None:
        self._cb = ContextBuilder()

    # ---------------------------------------------------------------- #
    # 写作模式编译                                                       #
    # ---------------------------------------------------------------- #

    def compile_authoring(
        self,
        project_id: str,
        chapter_target: ChapterTarget,
        plot_graph: "PlotGraph | None" = None,
        characters: "list[CharacterState] | None" = None,
        world: "WorldState | None" = None,
        memory: "MemorySystem | None" = None,
        lorebook: "Lorebook | None" = None,
        previous_hook: str | None = None,
        current_volume_goal: str | None = None,
        author_memory_anchors: list[str] | None = None,
        require_complete_inputs: bool = False,
        token_budget: int = 8000,
    ) -> AuthoringRuntimePackage:
        """
        写作模式编译（Gate 1-10）。

        Gate 10 使用 lorebook.get_for_scene() 按当前章节场景召回世界知识。
        """
        strict_authoring = require_complete_inputs or any(
            value is not None
            for value in (previous_hook, current_volume_goal, author_memory_anchors)
        )
        if strict_authoring:
            self._validate_authoring_inputs(
                world=world,
                characters=characters,
                previous_hook=previous_hook,
                current_volume_goal=current_volume_goal,
                author_memory_anchors=author_memory_anchors,
                require_complete_inputs=require_complete_inputs,
            )

        ctx = self._cb.build(
            chapter_target=chapter_target,
            plot_graph=plot_graph,
            characters=characters,
            world=world,
            memory=memory,
            project_id=project_id,
        )

        explicit_anchors = list(author_memory_anchors or [])
        if explicit_anchors:
            ctx.long_term_anchors = [*explicit_anchors, *ctx.long_term_anchors]
        if previous_hook:
            ctx.short_term_memory = [f"上一章 Hook：{previous_hook}", *ctx.short_term_memory]
        if current_volume_goal:
            goal_prefix = f"当前卷目标：{current_volume_goal}"
            ctx.plot_summary = (
                f"{goal_prefix}\n{ctx.plot_summary}".strip()
                if ctx.plot_summary
                else goal_prefix
            )

        # Gate 10: Lore 注入
        lore_inj = LoreInjection()
        if lorebook is not None:
            location = ""
            char_names: list[str] = [c.name for c in (characters or [])]
            faction_names: list[str] = list(ctx.world.active_factions)[:3]
            lore_entries = lorebook.get_for_scene(
                location=location,
                characters=char_names,
                factions=faction_names,
            )
            lore_inj.entries = [
                {"title": e.title, "summary": e.summary, "type": e.entry_type.value}
                for e in lore_entries
            ]
            lore_inj.total_tokens_estimate = sum(
                len(e["summary"]) // 3 for e in lore_inj.entries
            )

        gates_trimmed = _apply_token_budget(
            ctx, lore_inj, None, token_budget, mode="authoring"
        )

        return AuthoringRuntimePackage(
            project_id=project_id,
            chapter=chapter_target.chapter,
            write_context=ctx,
            previous_hook=previous_hook or "",
            current_volume_goal=current_volume_goal or "",
            author_memory_anchors=explicit_anchors,
            lore_injection=lore_inj,
            gates_trimmed=gates_trimmed,
            total_token_estimate=_estimate_tokens(ctx, lore_inj, None),
        )

    def _validate_authoring_inputs(
        self,
        *,
        world: "WorldState | None",
        characters: "list[CharacterState] | None",
        previous_hook: str | None,
        current_volume_goal: str | None,
        author_memory_anchors: list[str] | None,
        require_complete_inputs: bool,
    ) -> None:
        if world is None or _is_empty_world_state(world):
            raise AuthoringInputError("WorldState 尚未发布，无法构建写作编译包。")

        if characters is None:
            raise AuthoringInputError("缺少 CharacterSnapshot 输入，无法构建写作编译包。")

        if require_complete_inputs and not characters:
            raise AuthoringInputError("当前项目尚无角色卡，无法开始写作。")

        missing_drive = [character.name for character in characters if character.drive is None]
        if require_complete_inputs and missing_drive:
            names = "、".join(missing_drive[:5])
            raise AuthoringInputError(f"以下角色缺少 Drive 层：{names}")

        if previous_hook is None:
            raise AuthoringInputError("上一章 hook 未显式提供。")

        if author_memory_anchors is None:
            raise AuthoringInputError("最近三章记忆锚点未显式提供。")

        if current_volume_goal is None:
            raise AuthoringInputError("当前卷目标未显式提供。")

        if require_complete_inputs and not current_volume_goal.strip():
            raise AuthoringInputError("PlotGraph 缺少当前卷目标，无法开始写作。")

    # ---------------------------------------------------------------- #
    # 互动模式编译                                                       #
    # ---------------------------------------------------------------- #

    def compile_interactive(
        self,
        project_id: str,
        session: "InteractiveSession",
        world: "WorldState | None" = None,
        characters: "list[CharacterState] | None" = None,
        lorebook: "Lorebook | None" = None,
        token_budget: int = 6000,
    ) -> InteractiveRuntimePackage:
        """
        互动模式编译（Gate 1-11）。

        Gate 10: Lore 按场景召回
        Gate 11: 控制模式注入
        """
        # 用 session 信息构造最简 ChapterTarget
        chapter_target = ChapterTarget(
            chapter=session.turn,
            target_summary=session.world_summary[:100] if session.world_summary else "",
            word_count_target=200,
        )

        ctx = self._cb.build(
            chapter_target=chapter_target,
            characters=characters,
            world=world,
            project_id=project_id,
        )

        # Gate 10: Lore 注入
        lore_inj = LoreInjection()
        if lorebook is not None:
            char_names = [c.name for c in (characters or [])]
            lore_entries = lorebook.get_for_scene(characters=char_names)
            lore_inj.entries = [
                {"title": e.title, "summary": e.summary, "type": e.entry_type.value}
                for e in lore_entries
            ]
            lore_inj.total_tokens_estimate = sum(
                len(e["summary"]) // 3 for e in lore_inj.entries
            )

        # Gate 11: 控制层注入
        ctrl = ControlLayerInjection(
            control_mode=session.control_mode.value if hasattr(session, "control_mode") else "user_driven",
            ai_controlled_characters=list(
                session.mode_config.ai_controlled_characters
                if hasattr(session, "mode_config") else []
            ),
            allow_protagonist_proxy=(
                session.mode_config.allow_protagonist_proxy
                if hasattr(session, "mode_config") else False
            ),
            director_intervention=(
                session.mode_config.director_intervention_enabled
                if hasattr(session, "mode_config") else False
            ),
        )

        gates_trimmed = _apply_token_budget(
            ctx, lore_inj, ctrl, token_budget, mode="interactive"
        )

        return InteractiveRuntimePackage(
            project_id=project_id,
            session_id=session.session_id,
            write_context=ctx,
            lore_injection=lore_inj,
            control_layer=ctrl,
            gates_trimmed=gates_trimmed,
            total_token_estimate=_estimate_tokens(ctx, lore_inj, ctrl),
        )


# ------------------------------------------------------------------ #
# Token 预算裁剪                                                        #
# ------------------------------------------------------------------ #

def _estimate_tokens(
    ctx: WriteContext,
    lore_inj: LoreInjection,
    ctrl: ControlLayerInjection | None,
) -> int:
    """粗估整体 token 数（字符数 / 3）。"""
    base = len(ctx.to_system_prompt()) // 3
    lore = lore_inj.total_tokens_estimate
    ctrl_tokens = len(ctrl.to_prompt_block()) // 3 if ctrl else 0
    return base + lore + ctrl_tokens


def _apply_token_budget(
    ctx: WriteContext,
    lore_inj: LoreInjection,
    ctrl: ControlLayerInjection | None,
    budget: int,
    mode: str,
) -> list[str]:
    """
    超出 token 预算时，按 Gate 优先级从低到高裁剪。
    返回被裁剪的 Gate 名称列表。
    """
    trimmed: list[str] = []
    total = _estimate_tokens(ctx, lore_inj, ctrl)
    if total <= budget:
        return trimmed

    # 裁剪顺序：按优先级从低到高（即数字从大到小不必要的先删）
    if total > budget:
        # 先裁 lore
        if lore_inj.entries:
            # 每次删最后一条 lore entry
            while lore_inj.entries and _estimate_tokens(ctx, lore_inj, ctrl) > budget:
                lore_inj.entries.pop()
            trimmed.append("gate10_lore_partial")
        total = _estimate_tokens(ctx, lore_inj, ctrl)

    if total > budget:
        # 裁 style
        ctx.style_summary = ""
        trimmed.append("gate9_style")
        total = _estimate_tokens(ctx, lore_inj, ctrl)

    if total > budget:
        # 裁 long_term_anchors
        ctx.long_term_anchors = []
        trimmed.append("gate6_long_term")
        total = _estimate_tokens(ctx, lore_inj, ctrl)

    if total > budget:
        # 裁 short_term_memory
        ctx.short_term_memory = ctx.short_term_memory[-1:]
        trimmed.append("gate5_short_memory_partial")

    return trimmed


def _is_empty_world_state(world: "WorldState") -> bool:
    return not any([
        getattr(world, "factions", {}),
        getattr(world, "geography", {}),
        getattr(world, "timeline", []),
        getattr(world, "rules_of_world", []),
        getattr(getattr(world, "power_system", None), "name", ""),
        getattr(getattr(world, "power_system", None), "rules", []),
    ])
