"""tests/test_agents/test_critic.py — CriticAgent 单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from narrative_os.agents.critic import CriticAgent, CriticReport
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, BehaviorConstraint, CharacterState
from narrative_os.execution.context_builder import ChapterTarget, WriteContext
from narrative_os.skills.consistency import ConsistencyIssue, ConsistencyReport
from narrative_os.skills.scene import SceneOutput


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_draft(
    chapter: int = 1,
    total_words: int = 1600,
    avg_tension: float = 0.7,
    hook_score: float = 0.8,
    text: str = "章节内容示例，用于测试目的。",
) -> ChapterDraft:
    scenes = [
        SceneOutput(
            text=text,
            word_count=total_words,
            tension_score=avg_tension,
            hook_score=hook_score,
            chapter=chapter,
        )
    ]
    return ChapterDraft(
        chapter=chapter,
        volume=1,
        scenes=scenes,
        draft_text=text,
        total_words=total_words,
        avg_tension=avg_tension,
        hook_score=hook_score,
    )


def _make_context(chapter: int = 1, target_words: int = 2000) -> WriteContext:
    return WriteContext(
        chapter_target=ChapterTarget(
            chapter=chapter, volume=1,
            target_summary="测试",
            word_count_target=target_words,
        )
    )


def _good_consistency_report() -> ConsistencyReport:
    return ConsistencyReport(passed=True, issues=[], score=1.0)


def _bad_consistency_report() -> ConsistencyReport:
    hard_issue = ConsistencyIssue(
        dimension="character",
        severity="hard",
        description="角色行为矛盾",
        suggestion="修正行为描写",
        source_rule="constraint_check",
    )
    return ConsistencyReport(passed=False, issues=[hard_issue], score=0.4)


# ------------------------------------------------------------------ #
# CriticReport                                                          #
# ------------------------------------------------------------------ #

class TestCriticReport:
    def test_rewrite_instructions_default_empty(self):
        r = CriticReport(passed=True)
        assert r.rewrite_instructions == []

    def test_fields(self):
        r = CriticReport(
            passed=False,
            quality_score=0.4,
            hook_score=0.3,
            rewrite_instructions=["提升张力", "补充钩子"],
        )
        assert len(r.rewrite_instructions) == 2


# ------------------------------------------------------------------ #
# CriticAgent                                                           #
# ------------------------------------------------------------------ #

class TestCriticAgent:
    async def test_passes_high_quality_draft(self, monkeypatch):
        agent = CriticAgent()
        draft = _make_draft(total_words=1800, avg_tension=0.8, hook_score=0.9)
        ctx = _make_context(target_words=2000)

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_good_consistency_report()))

        report = await agent.review(draft, ctx)

        assert report.passed is True
        assert report.quality_score >= agent.quality_threshold
        assert report.hook_score >= agent.hook_threshold

    async def test_fails_low_hook_score(self, monkeypatch):
        agent = CriticAgent()
        draft = _make_draft(total_words=1800, avg_tension=0.8, hook_score=0.2)
        ctx = _make_context(target_words=2000)

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_good_consistency_report()))

        report = await agent.review(draft, ctx)

        assert report.passed is False
        assert any("钩子" in instr for instr in report.rewrite_instructions)

    async def test_fails_hard_consistency_issue(self, monkeypatch):
        agent = CriticAgent()
        draft = _make_draft(total_words=1800, avg_tension=0.8, hook_score=0.9)
        ctx = _make_context(target_words=2000)

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_bad_consistency_report()))

        report = await agent.review(draft, ctx)

        assert report.passed is False
        assert report.consistency_report is not None
        assert "[一致性修复]" in " ".join(report.rewrite_instructions)

    async def test_review_summary_contains_status(self, monkeypatch):
        agent = CriticAgent()
        draft = _make_draft(total_words=1800, avg_tension=0.8, hook_score=0.9)
        ctx = _make_context()

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_good_consistency_report()))

        report = await agent.review(draft, ctx)

        assert "通过" in report.review_summary or "待修改" in report.review_summary

    async def test_consistency_failure_gracefully_handled(self, monkeypatch):
        """ConsistencyChecker 抛出异常时 Critic 不崩溃。"""
        agent = CriticAgent()
        draft = _make_draft(total_words=1800, avg_tension=0.8, hook_score=0.9)
        ctx = _make_context()

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(side_effect=RuntimeError("模拟错误")))

        report = await agent.review(draft, ctx)

        assert isinstance(report, CriticReport)

    async def test_low_word_count_adds_instruction(self, monkeypatch):
        agent = CriticAgent()
        draft = _make_draft(total_words=300, avg_tension=0.2, hook_score=0.2)
        ctx = _make_context(target_words=2000)

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_good_consistency_report()))

        report = await agent.review(draft, ctx)

        assert report.passed is False
        assert any("字数" in i or "篇幅" in i for i in report.rewrite_instructions)

    async def test_custom_thresholds_respected(self, monkeypatch):
        """使用较低阈值时应更容易通过。"""
        agent = CriticAgent(quality_threshold=0.1, hook_threshold=0.1)
        draft = _make_draft(total_words=500, avg_tension=0.3, hook_score=0.3)
        ctx = _make_context(target_words=2000)

        monkeypatch.setattr(agent._consistency, "check",
                            AsyncMock(return_value=_good_consistency_report()))

        report = await agent.review(draft, ctx)
        assert report.passed is True
