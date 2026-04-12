"""
agents/editor.py — Phase 3: Editor Agent

职责：
  - 接收通过审查的 ChapterDraft + CriticReport
  - 运行 Humanizer 对全文去 AI 痕迹
  - 输出：EditedChapter（最终可发布文本）

处理策略：
  - 若 change_ratio < 0.05（LLM 改动极小），记录警告但不阻塞
  - 最终文本写入 EditedChapter.text
  - word_count = 最终文本字数
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.writer import ChapterDraft
from narrative_os.execution.llm_router import (
    LLMRouter,
    RoutingStrategy,
    get_default_routing_strategy,
    router as default_router,
)
from narrative_os.infra.logging import logger
from narrative_os.schemas.traces import Artifact, ArtifactType
from narrative_os.skills.humanize import Humanizer


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class EditedChapter(BaseModel):
    """Editor Agent 最终输出。"""
    chapter: int
    volume: int = 1
    text: str
    word_count: int
    change_ratio: float = 0.0
    applied_rules: list[str] = []
    model_used: str = ""


# ------------------------------------------------------------------ #
# EditorAgent                                                           #
# ------------------------------------------------------------------ #

class EditorAgent:
    """
    文本润色 Agent（去 AI 痕迹）。

    用法：
        agent = EditorAgent()
        edited = await agent.edit(draft, critic_report, strategy)
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or default_router
        self._humanizer = Humanizer(router=self._router)

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def edit(
        self,
        draft: ChapterDraft,
        critic_report: CriticReport,  # noqa: ARG002 — 保留接口，未来可传入风格指令
        strategy: RoutingStrategy = get_default_routing_strategy(),
        style_focus: list[str] | None = None,
        run_context: Any | None = None,
    ) -> EditedChapter:
        """对草稿进行人性化润色。"""
        if "此段内容待补充" in draft.draft_text:
            logger.warn("editor_skip_placeholder_draft", chapter=draft.chapter)
            humanize_output = None
            final_text = draft.draft_text
            change_ratio = 0.0
            applied_rules: list[str] = []
            model_used = "editor_bypassed"
        else:
            humanize_output = await self._humanizer.humanize(
                text=draft.draft_text,
                style_focus=style_focus,
            )
            final_text = humanize_output.humanized_text
            change_ratio = humanize_output.change_ratio
            applied_rules = humanize_output.applied_rules
            model_used = humanize_output.model_used

        if humanize_output is not None and humanize_output.change_ratio < 0.05:
            logger.warn(
                "editor_low_change_ratio",
                chapter=draft.chapter,
                change_ratio=humanize_output.change_ratio,
            )

        word_count = len(final_text)

        logger.info(
            "editor_agent_complete",
            chapter=draft.chapter,
            words=word_count,
            change_ratio=humanize_output.change_ratio,
        )

        result = EditedChapter(
            chapter=draft.chapter,
            volume=draft.volume,
            text=final_text,
            word_count=word_count,
            change_ratio=change_ratio,
            applied_rules=applied_rules,
            model_used=model_used,
        )
        if run_context is not None:
            await run_context.emit_artifact(
                Artifact(
                    artifact_type=ArtifactType.FINAL_TEXT,
                    agent_name="editor",
                    input_summary=draft.draft_text[:200],
                    output_content=result.text,
                    quality_scores={
                        "change_ratio": result.change_ratio,
                        "quality_score": critic_report.quality_score,
                    },
                    token_in=run_context.last_token_in,
                    token_out=run_context.last_token_out,
                    latency_ms=run_context.last_latency_ms,
                )
            )
        return result
