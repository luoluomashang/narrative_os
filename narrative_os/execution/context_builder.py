"""
execution/context_builder.py — Phase 2: 写前上下文组装器（9-Gate Pre-Write Context）

在每次生成场景/章节前，经由 9 个"关卡"组装出完整上下文包，
确保 Writer Agent 拿到的信息精确、充分、不冲突。

9 Gate 顺序：
  Gate 1  当前章节元信息（目标/章号/字数档位）
  Gate 2  活跃情节节点（PlotGraph 当前节点 + 前置依赖摘要）
  Gate 3  在场角色状态快照（emotion/goal/arc_stage/relationships）
  Gate 4  世界状态快照（势力/设定/时间线最近事件）
  Gate 5  短期记忆检索（近 3 章语义检索摘要）
  Gate 6  长期锚点检索（全书关键锚点）
  Gate 7  写作约束包（来自 methodology.yaml + writing_rules.yaml）
  Gate 8  爽感/张力目标（期望 tension_target、hook_type）
  Gate 9  风格注入（style_rules.yaml 当前档位摘要 + human_touch_rules）

UI 映射：写前上下文面板（可折叠的 Accordion，逐 Gate 展示）
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from narrative_os.infra.config import load_yaml

if TYPE_CHECKING:
    from narrative_os.core.character import CharacterState
    from narrative_os.core.memory import MemorySystem
    from narrative_os.core.plot import PlotGraph
    from narrative_os.core.world import WorldState


# ------------------------------------------------------------------ #
# 输出数据模型                                                          #
# ------------------------------------------------------------------ #

class ChapterTarget(BaseModel):
    chapter: int
    volume: int = 1
    target_summary: str = ""
    word_count_target: int = 2000
    tension_target: float = 0.6
    hook_type: str = "suspense"   # suspense / revelation / cliffhanger / emotional


class CharacterSnapshot(BaseModel):
    name: str
    emotion: str
    goal: str
    arc_stage: str
    relationships: dict[str, float] = Field(default_factory=dict)
    recent_events: list[str] = Field(default_factory=list)


class WorldSnapshot(BaseModel):
    active_factions: list[str] = Field(default_factory=list)
    recent_timeline: list[str] = Field(default_factory=list)
    power_system_name: str = ""
    key_rules: list[str] = Field(default_factory=list)


class ConstraintPack(BaseModel):
    hard_rules: list[str] = Field(default_factory=list)
    style_directives: list[str] = Field(default_factory=list)
    human_touch_hints: list[str] = Field(default_factory=list)


class WriteContext(BaseModel):
    """Gate 1-9 组装完成的完整写前上下文。传给 Writer skill 作为 system prompt 原材料。"""
    # Gate 1
    chapter_target: ChapterTarget
    # Gate 2
    active_plot_nodes: list[dict[str, Any]] = Field(default_factory=list)
    plot_summary: str = ""
    # Gate 3
    characters: list[CharacterSnapshot] = Field(default_factory=list)
    # Gate 4
    world: WorldSnapshot = Field(default_factory=WorldSnapshot)
    # Gate 5
    short_term_memory: list[str] = Field(default_factory=list)
    # Gate 6
    long_term_anchors: list[str] = Field(default_factory=list)
    # Gate 7
    constraints: ConstraintPack = Field(default_factory=ConstraintPack)
    # Gate 8 (merged into chapter_target.tension_target / hook_type)
    # Gate 9
    style_summary: str = ""

    def to_system_prompt(self) -> str:
        """将上下文渲染为 system prompt 文本，供 LLMRouter 使用。"""
        lines: list[str] = ["# 写前上下文（Narrative OS 自动组装）\n"]

        ct = self.chapter_target
        lines.append(
            f"## 当前章节\n"
            f"卷 {ct.volume} / 章 {ct.chapter}｜目标字数 {ct.word_count_target} 字\n"
            f"章节定位：{ct.target_summary}\n"
            f"张力目标：{ct.tension_target:.0%}｜钩子类型：{ct.hook_type}\n"
        )

        if self.active_plot_nodes:
            lines.append("## 活跃情节节点")
            for n in self.active_plot_nodes[:5]:
                lines.append(f"- [{n.get('type','')}] {n.get('summary','')}")
            if self.plot_summary:
                lines.append(f"\n情节背景：{self.plot_summary}")
            lines.append("")

        if self.characters:
            lines.append("## 在场角色")
            for c in self.characters:
                lines.append(
                    f"- **{c.name}**：情绪={c.emotion}，目标={c.goal}，弧光={c.arc_stage}"
                )
            lines.append("")

        w = self.world
        if w.active_factions or w.recent_timeline:
            lines.append("## 世界状态")
            if w.power_system_name:
                lines.append(f"力量体系：{w.power_system_name}")
            if w.active_factions:
                lines.append(f"活跃势力：{'、'.join(w.active_factions[:5])}")
            if w.recent_timeline:
                lines.append("近期事件：" + "；".join(w.recent_timeline[-3:]))
            if w.key_rules:
                lines.append("世界法则：" + " / ".join(w.key_rules[:3]))
            lines.append("")

        if self.short_term_memory:
            lines.append("## 短期记忆（近章摘要）")
            for s in self.short_term_memory[-3:]:
                lines.append(f"- {s}")
            lines.append("")

        if self.long_term_anchors:
            lines.append("## 长期锚点")
            for a in self.long_term_anchors[:5]:
                lines.append(f"- {a}")
            lines.append("")

        c = self.constraints
        if c.hard_rules:
            lines.append("## 硬性约束（不得违反）")
            for r in c.hard_rules[:8]:
                lines.append(f"- {r}")
            lines.append("")

        if c.style_directives:
            lines.append("## 文风指令")
            for d in c.style_directives[:5]:
                lines.append(f"- {d}")
            lines.append("")

        if c.human_touch_hints:
            lines.append("## 人味注入提示")
            for h in c.human_touch_hints[:3]:
                lines.append(f"- {h}")
            lines.append("")

        if self.style_summary:
            lines.append(f"## 风格摘要\n{self.style_summary}\n")

        return "\n".join(lines)


# ------------------------------------------------------------------ #
# ContextBuilder                                                        #
# ------------------------------------------------------------------ #

class ContextBuilder:
    """
    9-Gate 上下文组装器。

    用法：
        cb = ContextBuilder()
        ctx = cb.build(
            chapter_target=ChapterTarget(chapter=3, target_summary="主角被围攻"),
            plot_graph=graph,
            characters=[hero_state],
            world=world_state,
            memory=memory_system,
        )
        system_prompt = ctx.to_system_prompt()
    """

    def __init__(self) -> None:
        self._writing_rules: dict = {}
        self._style_rules: dict = {}
        self._human_touch: dict = {}
        self._methodology: dict = {}
        self._loaded = False

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        try:
            self._writing_rules = load_yaml("writing_rules")
        except FileNotFoundError:
            self._writing_rules = {}
        try:
            self._style_rules = load_yaml("style_rules")
        except FileNotFoundError:
            self._style_rules = {}
        try:
            self._human_touch = load_yaml("human_touch_rules")
        except FileNotFoundError:
            self._human_touch = {}
        try:
            self._methodology = load_yaml("methodology")
        except FileNotFoundError:
            self._methodology = {}
        self._loaded = True

    # ---------------------------------------------------------------- #
    # Main entry                                                        #
    # ---------------------------------------------------------------- #

    def build(
        self,
        chapter_target: ChapterTarget,
        plot_graph: "PlotGraph | None" = None,
        characters: "list[CharacterState] | None" = None,
        world: "WorldState | None" = None,
        memory: "MemorySystem | None" = None,
    ) -> WriteContext:
        self._ensure_loaded()

        ctx = WriteContext(chapter_target=chapter_target)

        # Gate 2: 情节节点
        if plot_graph is not None:
            ctx.active_plot_nodes, ctx.plot_summary = self._gate2_plot(plot_graph)

        # Gate 3: 角色快照
        if characters:
            ctx.characters = self._gate3_characters(characters)

        # Gate 4: 世界快照
        if world is not None:
            ctx.world = self._gate4_world(world)

        # Gate 5+6: 记忆检索
        if memory is not None:
            ctx.short_term_memory, ctx.long_term_anchors = self._gate5_6_memory(
                memory, chapter_target
            )

        # Gate 7: 约束包
        ctx.constraints = self._gate7_constraints()

        # Gate 9: 风格注入
        ctx.style_summary = self._gate9_style()

        return ctx

    # ---------------------------------------------------------------- #
    # Gates                                                             #
    # ---------------------------------------------------------------- #

    def _gate2_plot(
        self, graph: "PlotGraph"
    ) -> tuple[list[dict], str]:
        nodes = []
        for node_id, node in graph._nodes.items():
            if node.status in ("pending", "active"):
                nodes.append({
                    "id": node_id,
                    "type": node.type.value if hasattr(node.type, "value") else str(node.type),
                    "summary": node.summary,
                    "tension": node.tension,
                    "status": node.status.value if hasattr(node.status, "value") else str(node.status),
                })
        # 按张力排序，高张力优先
        nodes.sort(key=lambda n: n["tension"], reverse=True)

        curve = graph.get_tension_curve()
        peak = max((t for _, t in curve), default=0.0)
        summary = f"当前情节峰值张力 {peak:.0%}，活跃节点 {len(nodes)} 个。"
        return nodes, summary

    def _gate3_characters(
        self, characters: "list[CharacterState]"
    ) -> list[CharacterSnapshot]:
        snaps = []
        for ch in characters:
            arc = ch.get_arc_progression()
            snaps.append(CharacterSnapshot(
                name=ch.name,
                emotion=ch.emotion,
                goal=ch.goal,
                arc_stage=arc.get("current_stage_name", ""),
                relationships=dict(list(ch.relationships.items())[:5]),
                recent_events=list(ch.memory[-3:]) if ch.memory else [],
            ))
        return snaps

    def _gate4_world(self, world: "WorldState") -> WorldSnapshot:
        factions = list(world.factions.keys())
        timeline = [e.description for e in world.timeline[-5:]]
        return WorldSnapshot(
            active_factions=factions,
            recent_timeline=timeline,
            power_system_name=world.power_system.name if world.power_system else "",
            key_rules=world.rules_of_world[:5],
        )

    def _gate5_6_memory(
        self, memory: "MemorySystem", ct: ChapterTarget
    ) -> tuple[list[str], list[str]]:
        query = ct.target_summary or f"第{ct.chapter}章"

        # 短期：近章内容
        short_results = memory.retrieve(query, layer="short_term", top_k=3)
        short = [r.content[:200] for r in short_results]

        # 长期：锚点
        anchor_results = memory.get_recent_anchors(n=5)
        anchors = [r.content[:200] for r in anchor_results]

        return short, anchors

    def _gate7_constraints(self) -> ConstraintPack:
        hard: list[str] = []
        style: list[str] = []
        human: list[str] = []

        # 来自 writing_rules.yaml
        for rule in self._writing_rules.get("rules", []):
            if isinstance(rule, dict):
                text = rule.get("content") or rule.get("rule") or ""
                if text:
                    hard.append(text[:120])

        # 来自 style_rules.yaml → style_directives
        for d in self._style_rules.get("style_directives", [])[:6]:
            if isinstance(d, dict):
                text = d.get("content", "")[:120]
                if text:
                    style.append(text)

        # 来自 human_touch_rules.yaml → imperfection_injection examples
        imp = self._human_touch.get("imperfection_injection", {})
        for sub in imp.values():
            if isinstance(sub, dict):
                for ex in sub.get("examples", [])[:2]:
                    human.append(ex)
        if not human:
            human = ["偶尔让角色犹豫、改口或自嘲", "用细小动作代替直白心理描写"]

        return ConstraintPack(
            hard_rules=hard[:8],
            style_directives=style[:6],
            human_touch_hints=human[:4],
        )

    def _gate9_style(self) -> str:
        goal = self._style_rules.get("core_goal", "")
        if isinstance(goal, str):
            return goal[:300]
        return ""
