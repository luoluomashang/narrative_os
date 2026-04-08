"""tests/test_agents/test_editor.py — EditorAgent 单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.editor import EditedChapter, EditorAgent
from narrative_os.agents.writer import ChapterDraft
from narrative_os.skills.humanize import HumanizeOutput
from narrative_os.skills.scene import SceneOutput


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_draft(chapter: int = 1, text: str = "原始草稿内容") -> ChapterDraft:
    return ChapterDraft(
        chapter=chapter,
        volume=1,
        scenes=[SceneOutput(text=text, word_count=len(text), chapter=chapter)],
        draft_text=text,
        total_words=len(text),
        avg_tension=0.6,
        hook_score=0.7,
    )


def _make_critic_report(passed: bool = True) -> CriticReport:
    return CriticReport(passed=passed)


def _make_humanize_output(
    original: str,
    humanized: str,
    change_ratio: float = 0.15,
) -> HumanizeOutput:
    return HumanizeOutput(
        original_text=original,
        humanized_text=humanized,
        change_ratio=change_ratio,
        applied_rules=["句式变化", "去除 AI 词汇"],
        model_used="mock",
    )


# ------------------------------------------------------------------ #
# EditorAgent                                                           #
# ------------------------------------------------------------------ #

class TestEditorAgent:
    async def test_edit_returns_edited_chapter(self, monkeypatch):
        agent = EditorAgent()
        draft = _make_draft(chapter=3, text="原始内容，需要润色。")
        report = _make_critic_report()

        monkeypatch.setattr(
            agent._humanizer, "humanize",
            AsyncMock(return_value=_make_humanize_output(
                original=draft.draft_text,
                humanized="润色后的内容，更具人情味的表达方式。",
            ))
        )

        edited = await agent.edit(draft, report)

        assert isinstance(edited, EditedChapter)
        assert edited.chapter == 3
        assert edited.text == "润色后的内容，更具人情味的表达方式。"

    async def test_edit_word_count_reflects_final_text(self, monkeypatch):
        agent = EditorAgent()
        draft = _make_draft(text="原始文字内容")
        report = _make_critic_report()
        humanized = "这是经过润色修改之后的最终稿，字数发生了变化。"

        monkeypatch.setattr(
            agent._humanizer, "humanize",
            AsyncMock(return_value=_make_humanize_output(original="原始文字内容", humanized=humanized))
        )

        edited = await agent.edit(draft, report)
        assert edited.word_count == len(humanized)

    async def test_edit_preserves_applied_rules(self, monkeypatch):
        agent = EditorAgent()
        draft = _make_draft()
        report = _make_critic_report()

        monkeypatch.setattr(
            agent._humanizer, "humanize",
            AsyncMock(return_value=_make_humanize_output(
                original=draft.draft_text,
                humanized="润色后文本",
            ))
        )

        edited = await agent.edit(draft, report)
        assert "句式变化" in edited.applied_rules

    async def test_edit_low_change_ratio_still_returns(self, monkeypatch):
        """change_ratio < 0.05 时不应崩溃，正常返回结果。"""
        agent = EditorAgent()
        draft = _make_draft(text="接近原文的内容。")
        report = _make_critic_report()

        monkeypatch.setattr(
            agent._humanizer, "humanize",
            AsyncMock(return_value=_make_humanize_output(
                original=draft.draft_text,
                humanized=draft.draft_text,   # 完全一样
                change_ratio=0.0,
            ))
        )

        edited = await agent.edit(draft, report)
        assert isinstance(edited, EditedChapter)
        assert edited.change_ratio == 0.0

    async def test_volume_propagated(self, monkeypatch):
        agent = EditorAgent()
        draft = ChapterDraft(
            chapter=2, volume=3,
            scenes=[],
            draft_text="文本",
            total_words=2,
        )
        report = _make_critic_report()

        monkeypatch.setattr(
            agent._humanizer, "humanize",
            AsyncMock(return_value=_make_humanize_output(original="文本", humanized="文本2"))
        )

        edited = await agent.edit(draft, report)
        assert edited.volume == 3
