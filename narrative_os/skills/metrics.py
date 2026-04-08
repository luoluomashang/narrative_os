"""
skills/metrics.py — Phase 4: 叙事质量指标系统（Narrative Metrics）

职责：
  - 对已完成章节（或多章节序列）计算量化指标
  - 输出：NarrativeMetrics 报告，包含爽点密度、节奏曲线、张力趋势等
  - 纯本地计算（无 LLM 调用），可频繁调用

核心指标：
  payoff_density       爽点密度   — climax 节点占所有情节节点的比率
  pacing_score         节奏分     — 张力方差（太平或太激烈均得中低分）
  tension_trend        张力趋势   — "rising" / "falling" / "volatile" / "flat"
  character_arcs       角色成长评估 — 每个角色 arc_stage 阶段跨越数
  consistency_score    来自最近 ConsistencyReport.score
  word_efficiency      字效分     — 实际字数 / 等价目标 (0~1)

章节序列级别（多章分析）：
  volume_tension_curve   每章平均张力序列
  climax_distribution    高潮章节分布热度图（列表 int 权重）
  arc_completion_rate    已完成角色成长弧段的比例

注册：
  SkillRegistry 注册为 "narrative_metrics"
"""

from __future__ import annotations

import statistics
from typing import Any

from pydantic import BaseModel, Field

from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, CharacterState
from narrative_os.core.plot import NodeType, PlotGraph
from narrative_os.skills.consistency import ConsistencyReport
from narrative_os.skills.dsl import SkillRegistry


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class ArcProgressInfo(BaseModel):
    """单角色成长弧进度。"""
    character: str
    current_stage: str
    stages_advanced: int = 0       # 从起点到现在经过几个阶段（0~4）
    arc_complete: bool = False


class ChapterMetrics(BaseModel):
    """单章指标快照。"""
    chapter: int
    volume: int = 1
    word_count: int = 0
    avg_tension: float = 0.0
    hook_score: float = 0.0
    payoff_density: float = 0.0
    pacing_score: float = 0.0
    tension_trend: str = "flat"    # rising | falling | volatile | flat
    consistency_score: float = 1.0
    word_efficiency: float = 1.0
    overall_score: float = 0.0


class NarrativeMetrics(BaseModel):
    """多章叙事质量综合报告。"""
    chapters: list[ChapterMetrics] = Field(default_factory=list)

    # 卷级聚合
    volume_tension_curve: list[float] = Field(default_factory=list)
    climax_distribution: list[int] = Field(default_factory=list)
    arc_summaries: list[ArcProgressInfo] = Field(default_factory=list)

    # 聚合分
    avg_overall_score: float = 0.0
    avg_consistency: float = 1.0
    avg_payoff_density: float = 0.0

    def summary_text(self) -> str:
        lines = [
            f"叙事指标汇总 | {len(self.chapters)} 章",
            f"  综合平均分：{self.avg_overall_score:.2f}",
            f"  平均一致性：{self.avg_consistency:.2f}",
            f"  爽点密度均值：{self.avg_payoff_density:.2f}",
        ]
        if self.volume_tension_curve:
            trend = " → ".join(f"{t:.2f}" for t in self.volume_tension_curve[:8])
            lines.append(f"  张力曲线：{trend}")
        return "\n".join(lines)


# ------------------------------------------------------------------ #
# NarrativeMetricsCalc                                                  #
# ------------------------------------------------------------------ #

# ArcStage 顺序（用于计算成长跨度）
_ARC_ORDER = [
    ArcStage.DEFENSIVE,
    ArcStage.CRACKING,
    ArcStage.COMPENSATING,
    ArcStage.ACCEPTING,
    ArcStage.TRANSFORMED,
]


class NarrativeMetricsCalc:
    """
    叙事指标计算器（无 LLM）。

    用法：
        calc = NarrativeMetricsCalc()
        metrics = calc.evaluate_chapter(draft, plot_graph, characters,
                                        consistency_report, word_count_target)
        volume_report = calc.evaluate_volume(chapter_metrics_list, characters)
    """

    # ---------------------------------------------------------------- #
    # 单章评估                                                           #
    # ---------------------------------------------------------------- #

    def evaluate_chapter(
        self,
        draft: ChapterDraft,
        plot_graph: PlotGraph | None = None,
        characters: list[CharacterState] | None = None,
        consistency_report: ConsistencyReport | None = None,
        word_count_target: int = 2000,
    ) -> ChapterMetrics:
        # 爽点密度
        payoff = self._payoff_density(plot_graph, draft.chapter)

        # 节奏分
        pacing = self._pacing_score(draft)

        # 张力趋势
        trend = self._tension_trend(draft)

        # 一致性分
        cons_score = consistency_report.score if consistency_report else 1.0

        # 字效分
        word_eff = min(1.0, draft.total_words / max(1, word_count_target))

        # 综合分 = 加权平均
        overall = self._overall_score(
            tension=draft.avg_tension,
            hook=draft.hook_score,
            payoff=payoff,
            pacing=pacing,
            consistency=cons_score,
            word_eff=word_eff,
        )

        return ChapterMetrics(
            chapter=draft.chapter,
            volume=draft.volume,
            word_count=draft.total_words,
            avg_tension=round(draft.avg_tension, 3),
            hook_score=round(draft.hook_score, 3),
            payoff_density=round(payoff, 3),
            pacing_score=round(pacing, 3),
            tension_trend=trend,
            consistency_score=round(cons_score, 3),
            word_efficiency=round(word_eff, 3),
            overall_score=round(overall, 3),
        )

    # ---------------------------------------------------------------- #
    # 卷级聚合                                                           #
    # ---------------------------------------------------------------- #

    def evaluate_volume(
        self,
        chapter_metrics: list[ChapterMetrics],
        characters: list[CharacterState] | None = None,
    ) -> NarrativeMetrics:
        if not chapter_metrics:
            return NarrativeMetrics()

        tension_curve = [m.avg_tension for m in chapter_metrics]
        climax_dist = [
            1 if m.payoff_density >= 0.4 else 0
            for m in chapter_metrics
        ]
        arc_summaries = self._arc_summaries(characters or [])

        avg_overall = statistics.mean(m.overall_score for m in chapter_metrics)
        avg_cons = statistics.mean(m.consistency_score for m in chapter_metrics)
        avg_payoff = statistics.mean(m.payoff_density for m in chapter_metrics)

        return NarrativeMetrics(
            chapters=list(chapter_metrics),
            volume_tension_curve=tension_curve,
            climax_distribution=climax_dist,
            arc_summaries=arc_summaries,
            avg_overall_score=round(avg_overall, 3),
            avg_consistency=round(avg_cons, 3),
            avg_payoff_density=round(avg_payoff, 3),
        )

    # ---------------------------------------------------------------- #
    # 指标计算子方法                                                      #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _payoff_density(graph: PlotGraph | None, chapter: int) -> float:
        """climax 类型节点 / 全部属于本章的节点。"""
        if graph is None:
            return 0.0
        total = climax_count = 0
        prefix = f"ch{chapter}_"
        for node_id, node in graph._nodes.items():  # type: ignore[attr-defined]
            if not str(node_id).startswith(prefix):
                continue
            total += 1
            if node.type == NodeType.CLIMAX:
                climax_count += 1
        return climax_count / max(1, total)

    @staticmethod
    def _pacing_score(draft: ChapterDraft) -> float:
        """
        节奏分 = 基于各场景张力方差。
        最优：既不全平也不全激烈 → 中等方差得分最高。
        """
        if not draft.scenes:
            return 0.5
        tensions = [s.tension_score for s in draft.scenes]
        if len(tensions) < 2:
            return 0.6   # 单场景给中分
        var = statistics.variance(tensions)
        # 经验曲线：方差 0.02~0.08 得分最高（~1.0），过低/过高递减
        ideal_var = 0.05
        distance = abs(var - ideal_var)
        score = max(0.0, 1.0 - distance / 0.15)
        return min(1.0, score)

    @staticmethod
    def _tension_trend(draft: ChapterDraft) -> str:
        """通过张力序列判断整体趋势。"""
        if not draft.scenes or len(draft.scenes) < 2:
            return "flat"
        tensions = [s.tension_score for s in draft.scenes]
        rises = sum(1 for a, b in zip(tensions, tensions[1:]) if b > a)
        falls = sum(1 for a, b in zip(tensions, tensions[1:]) if b < a)
        n = len(tensions) - 1
        rises_ratio = rises / max(1, n)
        falls_ratio = falls / max(1, n)
        # 检查 volatile 优先（两方向均显著）
        if rises_ratio >= 0.30 and falls_ratio >= 0.30:
            return "volatile"
        if rises_ratio >= 0.70:
            return "rising"
        if falls_ratio >= 0.70:
            return "falling"
        return "flat"

    @staticmethod
    def _overall_score(
        tension: float,
        hook: float,
        payoff: float,
        pacing: float,
        consistency: float,
        word_eff: float,
    ) -> float:
        """加权综合分。"""
        return min(1.0, (
            tension     * 0.20
            + hook      * 0.20
            + payoff    * 0.15
            + pacing    * 0.10
            + consistency * 0.25
            + word_eff  * 0.10
        ))

    @staticmethod
    def _arc_summaries(characters: list[CharacterState]) -> list[ArcProgressInfo]:
        """计算每个角色的弧段进度。"""
        result = []
        for char in characters:
            stage = char.arc_stage
            try:
                idx = _ARC_ORDER.index(stage)
            except ValueError:
                idx = 0
            complete = (stage == ArcStage.TRANSFORMED)
            result.append(ArcProgressInfo(
                character=char.name,
                current_stage=str(stage),
                stages_advanced=idx,
                arc_complete=complete,
            ))
        return result


# ------------------------------------------------------------------ #
# SkillRegistry 注册                                                    #
# ------------------------------------------------------------------ #

_calc = NarrativeMetricsCalc()

def _metrics_handler(inputs: dict[str, Any]) -> dict[str, Any]:
    """SkillDSL 适配器。
    期望 inputs: {draft: ChapterDraft, ...}
    """
    draft = inputs.get("draft")
    if not isinstance(draft, ChapterDraft):
        return {"error": "draft must be a ChapterDraft instance"}
    metrics = _calc.evaluate_chapter(
        draft=draft,
        plot_graph=inputs.get("plot_graph"),
        characters=inputs.get("characters", []),
        consistency_report=inputs.get("consistency_report"),
        word_count_target=inputs.get("word_count_target", 2000),
    )
    return metrics.model_dump()


SkillRegistry.instance().register_fn("narrative_metrics", _metrics_handler)
