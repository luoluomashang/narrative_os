"""
agents/planner.py — Phase 3: Planner Agent

职责：
  - 接收章节目标（目标摘要 + 卷号/章号），生成结构化剧情骨架
  - 输出：PlotGraph（新增节点 + 边）+ 对话目标列表  
  - 使用 LARGE tier LLM（高潮/规划任务）
  - 骨架生成完成后写入 PlotGraph，更新 NarrativeState

输入（AgentInput）：
  chapter         当前章号
  volume          当前卷号
  target_summary  本章剧情定位（用户提供或上一章钩子推导）
  existing_graph  现有 PlotGraph（可选，供续写参考）
  characters      角色状态列表（可选）
  world           世界状态（可选）
  constraints     额外约束（来自 methodology.yaml 或用户）

输出（PlannerOutput）：
  chapter_outline     章节大纲文本（关键事件列表）
  plot_nodes          新增 PlotNode 列表（供 PlotGraph.create_event）
  plot_edges          新增 PlotEdge 列表（供 PlotGraph.link_events）
  dialogue_goals      对话目标列表（传给 WriterAgent）
  tension_curve       预计张力曲线（[(节点ID, tension), ...]）
  hook_suggestion     结尾钩子建议（描述 + 类型）

UI 映射：左侧剧情结构面板 → "规划" 按钮触发此 Agent
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.core.plot import NodeType, PlotEdge, PlotGraph, PlotNode
from narrative_os.execution.llm_router import (
    LLMRequest,
    LLMRouter,
    ModelTier,
    RoutingStrategy,
    get_default_routing_strategy,
    router as default_router,
)
from narrative_os.execution.prompt_utils import build_planner_system_prompt, parse_json_response
from narrative_os.infra.logging import logger
from narrative_os.schemas.traces import Artifact, ArtifactType


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class PlannerInput(BaseModel):
    """Planner Agent 输入。"""
    chapter: int
    volume: int = 1
    target_summary: str
    word_count_target: int = 2000
    previous_hook: str = ""
    existing_arc_summary: str = ""   # 前 N 章的情节摘要
    character_names: list[str] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    motivation_context: str = ""     # 角色动机冲突参考（由上层注入）


class PlannedNode(BaseModel):
    """LLM 输出的单个情节节点（结构化）。"""
    id: str
    type: str = "conflict"
    summary: str
    tension: float = 0.5
    characters: list[str] = Field(default_factory=list)


class PlannerOutput(BaseModel):
    """Planner Agent 输出。"""
    chapter_outline: str             # 大纲文本
    planned_nodes: list[PlannedNode] = Field(default_factory=list)
    edge_pairs: list[tuple[str, str, str]] = Field(default_factory=list)  # (from, to, relation)
    dialogue_goals: list[str] = Field(default_factory=list)
    tension_curve: list[tuple[str, float]] = Field(default_factory=list)
    hook_suggestion: str = ""
    hook_type: str = "suspense"      # suspense / revelation / cliffhanger / emotional
    raw_llm_output: str = ""

    def apply_to_graph(self, graph: PlotGraph) -> None:
        """将规划结果写入 PlotGraph。"""
        for n in self.planned_nodes:
            node_type = NodeType(n.type) if n.type in {t.value for t in NodeType} else NodeType.CONFLICT
            try:
                graph.create_event(n.id, type=node_type, summary=n.summary,
                                   tension=n.tension, characters=n.characters)
            except ValueError:
                pass  # 节点已存在，跳过
        for from_id, to_id, relation in self.edge_pairs:
            try:
                graph.link_events(from_id, to_id, relation=relation)
            except (KeyError, ValueError):
                pass


# ------------------------------------------------------------------ #
# PlannerAgent                                                          #
# ------------------------------------------------------------------ #

class PlannerAgent:
    """
    剧情规划 Agent。

    用法：
        agent = PlannerAgent()
        output = await agent.plan(planner_input)
        output.apply_to_graph(existing_graph)
    """

        SYSTEM_PROMPT = build_planner_system_prompt()

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or default_router

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def plan(
        self,
        inp: PlannerInput,
        strategy: RoutingStrategy = get_default_routing_strategy(),
        run_context: Any | None = None,
    ) -> PlannerOutput:
        user_msg = self._build_user_message(inp)
        req = LLMRequest(
            task_type="plot_planning",
            system_prompt=self.SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            strategy=strategy,
            tier_override=ModelTier.LARGE,
            max_tokens=1024,
            temperature=0.7,
            skill_name="planner_agent",
            agent_name="planner",
        )
        resp = await self._router.call(req)
        if run_context is not None:
            run_context.last_latency_ms = getattr(resp, "latency_ms", 0)
            run_context.last_token_in = getattr(resp, "tokens_in", 0)
            run_context.last_token_out = getattr(resp, "tokens_out", 0)
        logger.info("planner_agent_complete",
                    chapter=inp.chapter, latency_ms=resp.latency_ms)
        output = self._parse_output(resp.content, inp.chapter)
        if run_context is not None:
            await run_context.emit_artifact(
                Artifact(
                    artifact_type=ArtifactType.OUTLINE,
                    agent_name="planner",
                    input_summary=user_msg[:200],
                    output_content=output.raw_llm_output or output.chapter_outline,
                    quality_scores={
                        "node_count": float(len(output.planned_nodes)),
                        "dialogue_goals": float(len(output.dialogue_goals)),
                    },
                    token_in=run_context.last_token_in,
                    token_out=run_context.last_token_out,
                    latency_ms=run_context.last_latency_ms,
                )
            )
        return output

    # ---------------------------------------------------------------- #
    # Helpers                                                           #
    # ---------------------------------------------------------------- #

    def _build_user_message(self, inp: PlannerInput) -> str:
        lines = [
            f"## 任务：卷{inp.volume} 第{inp.chapter}章剧情规划",
            f"章节定位：{inp.target_summary}",
            f"目标字数：{inp.word_count_target}",
        ]
        if inp.previous_hook:
            lines.append(f"上章钩子：{inp.previous_hook}")
        if inp.existing_arc_summary:
            lines.append(f"前情摘要：{inp.existing_arc_summary}")
        if inp.character_names:
            lines.append(f"在场角色：{'、'.join(inp.character_names)}")
        if inp.world_rules:
            lines.append("世界法则：" + " / ".join(inp.world_rules[:3]))
        if inp.constraints:
            lines.append("额外约束：" + "；".join(inp.constraints[:3]))
        if inp.motivation_context:
            lines.append("")
            lines.append(inp.motivation_context)
        lines.append("\n请生成结构化剧情骨架（JSON 格式）：")
        return "\n".join(lines)

    def _parse_output(self, raw: str, chapter: int) -> PlannerOutput:
        """解析 LLM 输出的 JSON，失败时提供降级骨架。"""
        data = _extract_json(raw)
        if data is None:
            return self._fallback_output(raw, chapter)

        nodes = [
            PlannedNode(
                id=n.get("id", f"ch{chapter}_{i+1:02d}"),
                type=n.get("type", "conflict"),
                summary=n.get("summary", ""),
                tension=float(n.get("tension", 0.5)),
                characters=n.get("characters", []),
            )
            for i, n in enumerate(data.get("nodes", []))
        ]
        edges = [
            (e.get("from", ""), e.get("to", ""), e.get("relation", "causal"))
            for e in data.get("edges", [])
            if e.get("from") and e.get("to")
        ]
        hook = data.get("hook", {})
        tension_curve = [(n.id, n.tension) for n in nodes]

        return PlannerOutput(
            chapter_outline=data.get("outline", ""),
            planned_nodes=nodes,
            edge_pairs=edges,
            dialogue_goals=data.get("dialogue_goals", []),
            tension_curve=tension_curve,
            hook_suggestion=hook.get("description", "") if isinstance(hook, dict) else "",
            hook_type=hook.get("type", "suspense") if isinstance(hook, dict) else "suspense",
            raw_llm_output=raw,
        )

    def _fallback_output(self, raw: str, chapter: int) -> PlannerOutput:
        """解析失败时的降级输出（保留 raw 文本供人工处理）。"""
        return PlannerOutput(
            chapter_outline=raw[:300],
            planned_nodes=[
                PlannedNode(id=f"ch{chapter}_01", type="setup", summary="场景建立", tension=0.2),
                PlannedNode(id=f"ch{chapter}_02", type="conflict", summary="冲突展开", tension=0.7),
                PlannedNode(id=f"ch{chapter}_03", type="climax", summary="高潮对决", tension=0.9),
            ],
            edge_pairs=[
                (f"ch{chapter}_01", f"ch{chapter}_02", "causal"),
                (f"ch{chapter}_02", f"ch{chapter}_03", "causal"),
            ],
            hook_suggestion="下一步悬念",
            hook_type="suspense",
            raw_llm_output=raw,
        )


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _extract_json(text: str) -> dict[str, Any] | None:
    """从 LLM 输出中提取第一个 JSON 对象。"""
    parsed = parse_json_response(text, expect="object")
    return parsed if isinstance(parsed, dict) else None


# ------------------------------------------------------------------ #
# 角色动机上下文                                                         #
# ------------------------------------------------------------------ #

def build_motivation_context(characters: "list[Any]") -> str:
    """
    为 Planner 提供动机驱动的场景规划提示。

    参数为 list[CharacterState]，使用 Any 避免循环导入。
    调用方在构建 PlannerInput 时将结果传入 motivation_context 字段。
    """
    lines: list[str] = []
    for char in characters:
        motivations = getattr(char, "motivations", [])
        high = [m for m in motivations if m.tension >= 0.6]
        if high:
            desires = "、".join(m.desire for m in high)
            lines.append(f"- {char.name}：当前高张力驱动为「{desires}」，适合安排关键冲突")
    if not lines:
        return ""
    return "角色动机冲突参考（供 Planner 规划时参考，无需全部采用）：\n" + "\n".join(lines)
