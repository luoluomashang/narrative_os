"""tests/test_skills_phase4/test_metrics.py — NarrativeMetrics 单元测试"""

from __future__ import annotations

import pytest

from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, BehaviorConstraint, CharacterState
from narrative_os.core.plot import NodeType, PlotGraph
from narrative_os.skills.consistency import ConsistencyReport
from narrative_os.skills.metrics import (
    ArcProgressInfo,
    ChapterMetrics,
    NarrativeMetrics,
    NarrativeMetricsCalc,
)
from narrative_os.skills.scene import SceneOutput


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_draft(
    chapter: int = 1,
    total_words: int = 1800,
    avg_tension: float = 0.7,
    hook_score: float = 0.75,
    scenes_tensions: list[float] | None = None,
) -> ChapterDraft:
    tensions = scenes_tensions or [0.3, 0.65, 0.9]
    scenes = [
        SceneOutput(text="场景文本", word_count=total_words // len(tensions),
                    tension_score=t, hook_score=hook_score, chapter=chapter)
        for t in tensions
    ]
    return ChapterDraft(
        chapter=chapter,
        volume=1,
        scenes=scenes,
        draft_text="".join(s.text for s in scenes),
        total_words=total_words,
        avg_tension=avg_tension,
        hook_score=hook_score,
    )


def _make_graph_with_climax(chapter: int = 1) -> PlotGraph:
    g = PlotGraph()
    g.create_event(f"ch{chapter}_01", type=NodeType.SETUP,   summary="开场", tension=0.2)
    g.create_event(f"ch{chapter}_02", type=NodeType.CLIMAX,  summary="高潮", tension=0.9)
    g.create_event(f"ch{chapter}_03", type=NodeType.RESOLUTION, summary="收场", tension=0.3)
    return g


def _make_character(name: str, arc_stage: str = ArcStage.DEFENSIVE) -> CharacterState:
    return CharacterState(name=name, traits=[], arc_stage=arc_stage)


# ------------------------------------------------------------------ #
# ChapterMetrics                                                        #
# ------------------------------------------------------------------ #

class TestChapterMetricsModel:
    def test_defaults(self):
        m = ChapterMetrics(chapter=1)
        assert m.consistency_score == 1.0
        assert m.tension_trend == "flat"

    def test_fields(self):
        m = ChapterMetrics(chapter=3, overall_score=0.82, pacing_score=0.65)
        assert m.chapter == 3
        assert m.overall_score == 0.82


# ------------------------------------------------------------------ #
# tension_trend                                                         #
# ------------------------------------------------------------------ #

class TestTensionTrend:
    def test_rising(self):
        draft = _make_draft(scenes_tensions=[0.2, 0.5, 0.8, 0.9])
        trend = NarrativeMetricsCalc._tension_trend(draft)
        assert trend == "rising"

    def test_falling(self):
        draft = _make_draft(scenes_tensions=[0.9, 0.7, 0.4, 0.2])
        trend = NarrativeMetricsCalc._tension_trend(draft)
        assert trend == "falling"

    def test_volatile(self):
        draft = _make_draft(scenes_tensions=[0.2, 0.9, 0.2, 0.9])
        trend = NarrativeMetricsCalc._tension_trend(draft)
        assert trend == "volatile"

    def test_flat_single_scene(self):
        draft = _make_draft(scenes_tensions=[0.5])
        trend = NarrativeMetricsCalc._tension_trend(draft)
        assert trend == "flat"


# ------------------------------------------------------------------ #
# pacing_score                                                          #
# ------------------------------------------------------------------ #

class TestPacingScore:
    def test_varied_pacing_high_score(self):
        draft = _make_draft(scenes_tensions=[0.2, 0.6, 0.9, 0.4])
        score = NarrativeMetricsCalc._pacing_score(draft)
        assert 0.5 <= score <= 1.0

    def test_flat_pacing_low_score(self):
        draft = _make_draft(scenes_tensions=[0.5, 0.5, 0.5, 0.5])
        score = NarrativeMetricsCalc._pacing_score(draft)
        assert score < 0.7   # 全平评分偏低

    def test_single_scene_mid_score(self):
        draft = _make_draft(scenes_tensions=[0.7])
        score = NarrativeMetricsCalc._pacing_score(draft)
        assert 0.5 <= score <= 0.7


# ------------------------------------------------------------------ #
# payoff_density                                                        #
# ------------------------------------------------------------------ #

class TestPayoffDensity:
    def test_two_out_of_three_climax(self):
        g = PlotGraph()
        g.create_event("ch1_01", type=NodeType.CLIMAX, summary="高1")
        g.create_event("ch1_02", type=NodeType.CLIMAX, summary="高2")
        g.create_event("ch1_03", type=NodeType.SETUP,  summary="开场")
        density = NarrativeMetricsCalc._payoff_density(g, chapter=1)
        assert abs(density - 2/3) < 0.01

    def test_no_climax(self):
        g = PlotGraph()
        g.create_event("ch2_01", type=NodeType.SETUP, summary="开场")
        assert NarrativeMetricsCalc._payoff_density(g, chapter=2) == 0.0

    def test_no_graph(self):
        assert NarrativeMetricsCalc._payoff_density(None, chapter=1) == 0.0

    def test_wrong_chapter_nodes_ignored(self):
        """不属于当前章号的节点不计入密度。"""
        g = PlotGraph()
        g.create_event("ch5_01", type=NodeType.CLIMAX, summary="其他章高潮")
        density = NarrativeMetricsCalc._payoff_density(g, chapter=1)
        assert density == 0.0


# ------------------------------------------------------------------ #
# evaluate_chapter                                                      #
# ------------------------------------------------------------------ #

class TestEvaluateChapter:
    def test_returns_chapter_metrics(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft(chapter=2, total_words=1800, avg_tension=0.7, hook_score=0.75)
        m = calc.evaluate_chapter(draft, word_count_target=2000)
        assert isinstance(m, ChapterMetrics)
        assert m.chapter == 2

    def test_consistency_score_from_report(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft()
        report = ConsistencyReport(passed=True, issues=[], score=0.85)
        m = calc.evaluate_chapter(draft, consistency_report=report)
        assert abs(m.consistency_score - 0.85) < 0.01

    def test_word_efficiency_capped_at_1(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft(total_words=5000)
        m = calc.evaluate_chapter(draft, word_count_target=2000)
        assert m.word_efficiency == 1.0

    def test_overall_score_in_range(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft()
        m = calc.evaluate_chapter(draft)
        assert 0.0 <= m.overall_score <= 1.0

    def test_payoff_density_from_graph(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft(chapter=3)
        graph = _make_graph_with_climax(chapter=3)
        m = calc.evaluate_chapter(draft, plot_graph=graph)
        # 3 节点中 1 个 climax → 约 0.333
        assert 0.3 <= m.payoff_density <= 0.4


# ------------------------------------------------------------------ #
# evaluate_volume                                                       #
# ------------------------------------------------------------------ #

class TestEvaluateVolume:
    def test_tension_curve_length(self):
        calc = NarrativeMetricsCalc()
        drafts = [_make_draft(chapter=i) for i in range(1, 6)]
        metrics = [calc.evaluate_chapter(d) for d in drafts]
        vol = calc.evaluate_volume(metrics)
        assert len(vol.volume_tension_curve) == 5

    def test_avg_scores(self):
        calc = NarrativeMetricsCalc()
        drafts = [_make_draft(chapter=i) for i in range(1, 4)]
        metrics = [calc.evaluate_chapter(d) for d in drafts]
        vol = calc.evaluate_volume(metrics)
        assert 0.0 <= vol.avg_overall_score <= 1.0

    def test_arc_summaries(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft()
        ch_m = [calc.evaluate_chapter(draft)]
        chars = [
            _make_character("甲", ArcStage.CRACKING),
            _make_character("乙", ArcStage.TRANSFORMED),
        ]
        vol = calc.evaluate_volume(ch_m, characters=chars)
        names = [a.character for a in vol.arc_summaries]
        assert "甲" in names
        assert "乙" in names
        transformed = next(a for a in vol.arc_summaries if a.character == "乙")
        assert transformed.arc_complete is True

    def test_empty_input(self):
        calc = NarrativeMetricsCalc()
        vol = calc.evaluate_volume([])
        assert vol.avg_overall_score == 0.0

    def test_summary_text(self):
        calc = NarrativeMetricsCalc()
        draft = _make_draft()
        m = calc.evaluate_volume([calc.evaluate_chapter(draft)])
        text = m.summary_text()
        assert "章" in text and "综合" in text
