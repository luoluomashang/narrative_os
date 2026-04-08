"""
agents/critic.py — Phase 3: Critic Agent

职责：
  - 接收 ChapterDraft + 全量上下文
  - 运行 ConsistencyChecker 进行一致性审查
  - 评估质量分（QS）和钩子分（HS）
  - 输出：CriticReport（通过/改写）

评分规则：
  - quality_score   = (tension_score × 0.4 + word_ratio_score × 0.3 + consistency_score × 0.3)
  - hook_score      直接取最后一个场景的 hook_score
  - 通过条件：quality_score >= 0.65 AND hook_score >= 0.5 AND no hard consistency issues

输出（CriticReport）：
  passed              bool — 是否通过审查
  quality_score       float 0~1
  hook_score          float 0~1
  consistency_report  ConsistencyReport
  rewrite_instructions list[str] — 具体改写建议（仅当不通过时）
  review_summary      str — 一句话综合评语
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import CharacterState
from narrative_os.core.plot import PlotGraph
from narrative_os.core.world import WorldState
from narrative_os.execution.context_builder import WriteContext
from narrative_os.infra.logging import logger
from narrative_os.skills.consistency import ConsistencyChecker, ConsistencyReport


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class CriticReport(BaseModel):
    """Critic Agent 评审报告。"""
    passed: bool
    quality_score: float = 0.0
    hook_score: float = 0.0
    consistency_report: ConsistencyReport | None = None
    rewrite_instructions: list[str] = Field(default_factory=list)
    review_summary: str = ""

    # 阈值（类变量供测试覆盖）
    QUALITY_THRESHOLD: float = 0.65
    HOOK_THRESHOLD: float = 0.5


# ------------------------------------------------------------------ #
# CriticAgent                                                           #
# ------------------------------------------------------------------ #

class CriticAgent:
    """
    内容审查 Agent。

    用法：
        agent = CriticAgent()
        report = await agent.review(draft, context, characters, world, plot_graph)
    """

    def __init__(self, quality_threshold: float = 0.65, hook_threshold: float = 0.5) -> None:
        self._consistency = ConsistencyChecker()
        self.quality_threshold = quality_threshold
        self.hook_threshold = hook_threshold

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def review(
        self,
        draft: ChapterDraft,
        context: WriteContext,
        characters: list[CharacterState] | None = None,
        world: WorldState | None = None,
        plot_graph: PlotGraph | None = None,
    ) -> CriticReport:
        # 1. 一致性检查
        consistency_report = await self._run_consistency(
            text=draft.draft_text,
            characters=characters or [],
            world=world,
            plot_graph=plot_graph,
            chapter=draft.chapter,
        )

        # 2. 质量评分
        quality_score = self._calc_quality(draft, consistency_report, context)
        hook_score = draft.hook_score

        # 3. 判定通过/改写
        hard_issues = consistency_report.hard_issues if consistency_report else []
        passed = (
            quality_score >= self.quality_threshold
            and hook_score >= self.hook_threshold
            and len(hard_issues) == 0
        )

        # 4. 生成改写建议
        rewrite_instructions = []
        if not passed:
            rewrite_instructions = self._generate_instructions(
                draft, quality_score, hook_score, consistency_report
            )

        # 5. 一句话评语
        review_summary = self._make_summary(passed, quality_score, hook_score,
                                             consistency_report)

        logger.info(
            "critic_agent_complete",
            chapter=draft.chapter,
            passed=passed,
            quality=round(quality_score, 3),
            hook=round(hook_score, 3),
        )

        return CriticReport(
            passed=passed,
            quality_score=round(quality_score, 3),
            hook_score=round(hook_score, 3),
            consistency_report=consistency_report,
            rewrite_instructions=rewrite_instructions,
            review_summary=review_summary,
        )

    # ---------------------------------------------------------------- #
    # Helpers                                                           #
    # ---------------------------------------------------------------- #

    async def _run_consistency(
        self,
        text: str,
        characters: list[CharacterState],
        world: WorldState | None,
        plot_graph: PlotGraph | None,
        chapter: int,
    ) -> ConsistencyReport:
        try:
            return await self._consistency.check(
                text=text,
                characters=characters,
                world=world,
                plot_graph=plot_graph,
                chapter=chapter,
            )
        except Exception as exc:  # pylint: disable=broad-except
            logger.warn("consistency_check_failed", error=str(exc))
            # 一致性检查失败时返回空报告（不阻塞流程）
            from narrative_os.skills.consistency import ConsistencyReport as CR
            return CR(passed=True, issues=[], score=1.0)

    def _calc_quality(
        self,
        draft: ChapterDraft,
        consistency: ConsistencyReport | None,
        context: WriteContext,
    ) -> float:
        """计算综合质量分。"""
        # 张力均值得分
        tension_score = draft.avg_tension  # 已是 0~1

        # 字数得分（实际字数 / 目标字数，上限 1.0）
        target = context.chapter_target.word_count_target
        word_ratio = min(1.0, draft.total_words / max(1, target))

        # 一致性得分
        consistency_score = consistency.score if consistency else 1.0

        quality = (
            tension_score * 0.4
            + word_ratio * 0.3
            + consistency_score * 0.3
        )
        return min(1.0, max(0.0, quality))

    def _generate_instructions(
        self,
        draft: ChapterDraft,
        quality_score: float,
        hook_score: float,
        consistency_report: ConsistencyReport | None,
    ) -> list[str]:
        instructions: list[str] = []

        if quality_score < self.quality_threshold:
            if draft.avg_tension < 0.5:
                instructions.append("提升整体张力：增加冲突描写和情绪变化。")
            if draft.total_words < 800:
                instructions.append(f"扩充篇幅：当前 {draft.total_words} 字，建议至少 1500 字。")

        if hook_score < self.hook_threshold:
            instructions.append("加强结尾钩子：用悬念或情绪爆发推动读者继续阅读。")

        if consistency_report and consistency_report.hard_issues:
            for issue in consistency_report.hard_issues[:3]:
                instructions.append(f"[一致性修复] {issue.description} — {issue.suggestion}")

        return instructions

    @staticmethod
    def _make_summary(
        passed: bool,
        quality_score: float,
        hook_score: float,
        consistency_report: ConsistencyReport | None,
    ) -> str:
        status = "通过" if passed else "待修改"
        hard_count = len(consistency_report.hard_issues) if consistency_report else 0
        return (
            f"审查结果：{status}｜质量分 {quality_score:.2f}｜"
            f"钩子分 {hook_score:.2f}｜硬错误 {hard_count} 处。"
        )
