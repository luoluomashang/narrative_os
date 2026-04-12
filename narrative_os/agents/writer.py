"""
agents/writer.py — Phase 3: Writer Agent

职责：
  - 接收 PlannerOutput + WriteContext，逐场景调用 SceneGenerator
  - 将所有场景拼合成完整章节草稿
  - 输出：ChapterDraft（文本 + 统计 + 各场景子报告）

场景划分策略：
  - 依据 PlannerOutput.planned_nodes 将目标字数分配到各场景
  - setup/resolution 节点优先分配较少字数，climax 节点优先分配较多字数

输出（ChapterDraft）：
  chapter         章号
  volume          卷号
  scenes          每个 SceneOutput 列表
  draft_text      拼合后的完整章节文本
  total_words     实际总字数
  avg_tension     平均张力分
  hook_score      最后一个场景的 hook_score
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.agents.planner import PlannedNode, PlannerOutput
from narrative_os.execution.context_builder import WriteContext
from narrative_os.execution.narrative_compiler import AuthoringRuntimePackage
from narrative_os.execution.llm_router import (
    LLMRouter,
    RoutingStrategy,
    get_default_routing_strategy,
    router as default_router,
)
from narrative_os.infra.logging import logger
from narrative_os.schemas.traces import Artifact, ArtifactType
from narrative_os.skills.scene import SceneGenerator, SceneOutput


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class ChapterDraft(BaseModel):
    """Writer Agent 输出的章节草稿。"""
    chapter: int
    volume: int = 1
    scenes: list[SceneOutput] = Field(default_factory=list)
    draft_text: str = ""
    total_words: int = 0
    avg_tension: float = 0.0
    hook_score: float = 0.0


# ------------------------------------------------------------------ #
# WriterAgent                                                           #
# ------------------------------------------------------------------ #

class WriterAgent:
    """
    章节写作 Agent。

    用法：
        agent = WriterAgent()
        draft = await agent.write(planner_output, write_context, strategy)
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or default_router
        self._scene_gen = SceneGenerator(router=self._router)

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def write(
        self,
        plan: PlannerOutput,
        context_package: AuthoringRuntimePackage | WriteContext,
        strategy: RoutingStrategy = get_default_routing_strategy(),
        run_context: Any | None = None,
        retry_count: int = 0,
        retry_reason: str | None = None,
    ) -> ChapterDraft:
        """根据剧情规划生成章节草稿。"""
        package = _coerce_context_package(context_package, plan)
        context = package.write_context
        chapter = context.chapter_target.chapter
        volume = context.chapter_target.volume
        scenes: list[SceneOutput] = []

        # 分配字数权重
        word_budgets = _allocate_word_budgets(
            nodes=plan.planned_nodes,
            total_target=context.chapter_target.word_count_target,
        )

        for i, node in enumerate(plan.planned_nodes):
            budget = word_budgets[i]
            enriched_ctx = _enrich_context_for_node(context, node, budget)

            from narrative_os.execution.llm_router import LLMRequest, ModelTier
            scene_req = LLMRequest(
                task_type="scene_generation",
                messages=[],  # SceneGenerator 内部会重新构建
                skill_name="writer_agent",
                agent_name="writer",
                max_tokens=max(512, budget // 2),
            )
            try:
                scene = await self._scene_gen.generate(
                    context=enriched_ctx,
                    req=scene_req,
                    strategy=strategy,
                )
            except Exception as exc:  # pylint: disable=broad-except
                logger.warn("scene_generation_failed",
                               chapter=chapter, node=node.id, error=str(exc))
                scene = _fallback_scene(node, budget, chapter, volume)
            scenes.append(scene)

        draft_text = "\n\n".join(s.text for s in scenes if s.text)
        total_words = sum(s.word_count for s in scenes)
        avg_tension = (sum(s.tension_score for s in scenes) / len(scenes)) if scenes else 0.0
        hook_score = scenes[-1].hook_score if scenes else 0.0

        logger.info("writer_agent_complete",
                    chapter=chapter, scenes=len(scenes), total_words=total_words)

        draft = ChapterDraft(
            chapter=chapter,
            volume=volume,
            scenes=scenes,
            draft_text=draft_text,
            total_words=total_words,
            avg_tension=round(avg_tension, 3),
            hook_score=round(hook_score, 3),
        )
        if run_context is not None:
            await run_context.emit_artifact(
                Artifact(
                    artifact_type=ArtifactType.DRAFT,
                    agent_name="writer",
                        input_summary=package.to_system_prompt()[:200],
                    output_content=draft.draft_text,
                    quality_scores={
                        "avg_tension": draft.avg_tension,
                        "hook_score": draft.hook_score,
                    },
                    token_in=run_context.last_token_in,
                    token_out=run_context.last_token_out,
                    latency_ms=run_context.last_latency_ms,
                    retry_count=retry_count,
                    retry_reason=retry_reason,
                )
            )
        return draft


# ------------------------------------------------------------------ #
# Helpers                                                               #
# ------------------------------------------------------------------ #

_TENSION_WEIGHT: dict[str, float] = {
    "setup": 0.7,
    "conflict": 1.0,
    "climax": 1.4,
    "resolution": 0.6,
    "branch": 0.9,
}


def _allocate_word_budgets(nodes: list[PlannedNode], total_target: int) -> list[int]:
    """按场景类型权重分配目标字数。"""
    if not nodes:
        return []
    weights = [_TENSION_WEIGHT.get(n.type, 1.0) for n in nodes]
    total_w = sum(weights)
    budgets = [max(200, int(total_target * w / total_w)) for w in weights]
    # 修正误差
    diff = total_target - sum(budgets)
    if budgets:
        budgets[-1] += diff
    return budgets


def _enrich_context_for_node(context: WriteContext, node: PlannedNode, budget: int) -> WriteContext:
    """在原有 WriteContext 基础上注入节点信息。"""
    import copy
    ctx = copy.copy(context)

    new_target = context.chapter_target.model_copy(update={
        "target_summary": f"[{node.type.upper()}] {node.summary}",
        "word_count_target": budget,
        "tension_target": node.tension,
    })
    ctx.chapter_target = new_target
    return ctx


def _fallback_scene(node: PlannedNode, budget: int, chapter: int, volume: int) -> SceneOutput:
    """LLM 调用失败时的兜底场景。"""
    placeholder = f"【{node.summary}】（此段内容待补充）"
    return SceneOutput(
        text=placeholder,
        word_count=len(placeholder),
        tension_score=node.tension,
        hook_score=0.3,
        chapter=chapter,
        volume=volume,
        model_used="fallback",
        attempts=0,
    )


def _coerce_context_package(
    context_package: AuthoringRuntimePackage | WriteContext,
    plan: PlannerOutput,
) -> AuthoringRuntimePackage:
    if isinstance(context_package, AuthoringRuntimePackage):
        return context_package

    return AuthoringRuntimePackage(
        project_id="legacy",
        chapter=context_package.chapter_target.chapter,
        write_context=context_package,
        previous_hook="",
        current_volume_goal=plan.chapter_outline,
        author_memory_anchors=list(context_package.long_term_anchors),
    )
