"""tests/test_agents/test_writer.py — WriterAgent 单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from narrative_os.agents.planner import PlannedNode, PlannerOutput
from narrative_os.agents.writer import ChapterDraft, WriterAgent, _allocate_word_budgets
from narrative_os.execution.context_builder import ChapterTarget, WriteContext
from narrative_os.execution.llm_router import Backend, LLMResponse
from narrative_os.skills.scene import SceneOutput


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _make_plan(chapter: int = 1) -> PlannerOutput:
    return PlannerOutput(
        chapter_outline="测试大纲",
        planned_nodes=[
            PlannedNode(id=f"ch{chapter}_01", type="setup",    summary="开场", tension=0.2),
            PlannedNode(id=f"ch{chapter}_02", type="conflict", summary="冲突", tension=0.7),
            PlannedNode(id=f"ch{chapter}_03", type="climax",   summary="高潮", tension=0.9),
        ],
        edge_pairs=[(f"ch{chapter}_01", f"ch{chapter}_02", "causal")],
        hook_suggestion="结尾悬念",
        hook_type="suspense",
    )


def _make_context(chapter: int = 1) -> WriteContext:
    return WriteContext(
        chapter_target=ChapterTarget(
            chapter=chapter, volume=1,
            target_summary="测试章节",
            word_count_target=1500,
        )
    )


def _make_scene(chapter: int, text: str = "场景内容") -> SceneOutput:
    return SceneOutput(
        text=text,
        word_count=len(text),
        tension_score=0.6,
        hook_score=0.55,
        chapter=chapter,
        volume=1,
        model_used="mock",
        attempts=1,
    )


# ------------------------------------------------------------------ #
# _allocate_word_budgets                                                #
# ------------------------------------------------------------------ #

class TestAllocateWordBudgets:
    def test_sums_to_target(self):
        nodes = [
            PlannedNode(id="n1", type="setup", summary="a"),
            PlannedNode(id="n2", type="conflict", summary="b"),
            PlannedNode(id="n3", type="climax",  summary="c"),
        ]
        budgets = _allocate_word_budgets(nodes, 1500)
        assert sum(budgets) == 1500

    def test_climax_gets_most(self):
        nodes = [
            PlannedNode(id="n1", type="setup",   summary="a"),
            PlannedNode(id="n2", type="climax",  summary="c"),
            PlannedNode(id="n3", type="resolution", summary="r"),
        ]
        budgets = _allocate_word_budgets(nodes, 3000)
        assert budgets[1] > budgets[0]   # climax > setup
        assert budgets[1] > budgets[2]   # climax > resolution

    def test_empty_nodes_returns_empty(self):
        assert _allocate_word_budgets([], 2000) == []


# ------------------------------------------------------------------ #
# WriterAgent                                                           #
# ------------------------------------------------------------------ #

class TestWriterAgent:
    async def test_write_returns_draft(self, monkeypatch):
        agent = WriterAgent()
        plan = _make_plan(chapter=2)
        ctx = _make_context(chapter=2)

        async def fake_generate(context, req, strategy):
            return _make_scene(chapter=2, text="这是模拟场景文本，字数充足以通过测试验证。")

        monkeypatch.setattr(agent._scene_gen, "generate", fake_generate)

        draft = await agent.write(plan, ctx)

        assert isinstance(draft, ChapterDraft)
        assert draft.chapter == 2
        assert len(draft.scenes) == 3
        assert draft.total_words > 0
        assert draft.draft_text != ""

    async def test_draft_text_joins_scenes(self, monkeypatch):
        agent = WriterAgent()
        plan = _make_plan(chapter=1)
        ctx = _make_context(chapter=1)
        texts = ["第一幕内容。", "第二幕内容。", "第三幕内容。"]
        call_idx = [0]

        async def fake_generate(context, req, strategy):
            t = texts[call_idx[0]]
            call_idx[0] += 1
            return _make_scene(chapter=1, text=t)

        monkeypatch.setattr(agent._scene_gen, "generate", fake_generate)

        draft = await agent.write(plan, ctx)

        assert "第一幕内容。" in draft.draft_text
        assert "第三幕内容。" in draft.draft_text

    async def test_hook_score_from_last_scene(self, monkeypatch):
        agent = WriterAgent()
        plan = _make_plan(chapter=5)
        ctx = _make_context(chapter=5)
        call_idx = [0]
        scores = [0.3, 0.5, 0.85]

        async def fake_generate(context, req, strategy):
            s = _make_scene(5)
            s = s.model_copy(update={"hook_score": scores[call_idx[0]]})
            call_idx[0] += 1
            return s

        monkeypatch.setattr(agent._scene_gen, "generate", fake_generate)

        draft = await agent.write(plan, ctx)
        assert abs(draft.hook_score - 0.85) < 0.01

    async def test_fallback_on_scene_error(self, monkeypatch):
        """SceneGenerator 抛出异常时应使用兜底场景。"""
        agent = WriterAgent()
        plan = _make_plan(chapter=4)
        ctx = _make_context(chapter=4)

        async def raising_generate(context, req, strategy):
            raise RuntimeError("LLM 超时")

        monkeypatch.setattr(agent._scene_gen, "generate", raising_generate)

        draft = await agent.write(plan, ctx)
        assert draft.chapter == 4
        assert len(draft.scenes) == 3
        assert all("待补充" in s.text for s in draft.scenes)
