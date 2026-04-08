"""tests/test_orchestrator/test_graph.py — LangGraph 编排图单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.editor import EditedChapter
from narrative_os.agents.planner import PlannedNode, PlannerOutput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.plot import PlotGraph
from narrative_os.execution.context_builder import ChapterTarget, WriteContext
from narrative_os.orchestrator.graph import (
    MAX_RETRIES,
    AgentGraphState,
    build_graph,
    should_rewrite,
    planner_node,
    writer_node,
    critic_node,
    editor_node,
    memory_update_node,
    retry_increment_node,
)
from narrative_os.skills.consistency import ConsistencyReport
from narrative_os.skills.scene import SceneOutput


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _base_state(**overrides) -> AgentGraphState:
    state: AgentGraphState = {
        "chapter": 1,
        "volume": 1,
        "target_summary": "测试章节",
        "word_count_target": 1500,
        "previous_hook": "",
        "existing_arc_summary": "",
        "character_names": [],
        "world_rules": [],
        "constraints": [],
        "strategy": "QUALITY_FIRST",
        "plot_graph": None,
        "characters": [],
        "world": None,
        "memory": None,
        "planner_output": None,
        "write_context": None,
        "chapter_draft": None,
        "critic_report": None,
        "edited_chapter": None,
        "retry_count": 0,
        "error_message": "",
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _make_plan() -> PlannerOutput:
    return PlannerOutput(
        chapter_outline="测试大纲",
        planned_nodes=[
            PlannedNode(id="ch1_01", type="setup",    summary="开场", tension=0.2),
            PlannedNode(id="ch1_02", type="climax",   summary="高潮", tension=0.9),
        ],
        edge_pairs=[("ch1_01", "ch1_02", "causal")],
        hook_suggestion="结尾悬念",
        hook_type="suspense",
        tension_curve=[("ch1_01", 0.2), ("ch1_02", 0.9)],
    )


def _make_draft(chapter: int = 1, passed_hook: float = 0.8) -> ChapterDraft:
    return ChapterDraft(
        chapter=chapter,
        volume=1,
        scenes=[SceneOutput(text="场景文本", word_count=800, chapter=chapter)],
        draft_text="场景文本",
        total_words=800,
        avg_tension=0.7,
        hook_score=passed_hook,
    )


def _make_write_context() -> WriteContext:
    return WriteContext(
        chapter_target=ChapterTarget(chapter=1, volume=1, word_count_target=1500)
    )


def _passing_critic() -> CriticReport:
    return CriticReport(
        passed=True,
        quality_score=0.75,
        hook_score=0.8,
        consistency_report=ConsistencyReport(passed=True, issues=[], score=1.0),
    )


def _failing_critic() -> CriticReport:
    return CriticReport(
        passed=False,
        quality_score=0.3,
        hook_score=0.2,
        rewrite_instructions=["提升张力", "加强钩子"],
    )


# ------------------------------------------------------------------ #
# should_rewrite 路由函数                                               #
# ------------------------------------------------------------------ #

class TestShouldRewrite:
    def test_passes_to_editor(self):
        state = _base_state(
            critic_report=_passing_critic(),
            retry_count=0,
        )
        assert should_rewrite(state) == "editor"

    def test_fails_to_retry_writer(self):
        state = _base_state(
            critic_report=_failing_critic(),
            retry_count=0,
        )
        assert should_rewrite(state) == "retry_writer"

    def test_max_retries_forces_editor(self):
        state = _base_state(
            critic_report=_failing_critic(),
            retry_count=MAX_RETRIES,
        )
        assert should_rewrite(state) == "editor"

    def test_none_report_goes_to_editor(self):
        state = _base_state(critic_report=None, retry_count=0)
        assert should_rewrite(state) == "editor"


# ------------------------------------------------------------------ #
# retry_increment_node                                                  #
# ------------------------------------------------------------------ #

class TestRetryIncrementNode:
    async def test_increments_count(self):
        state = _base_state(retry_count=1)
        result = await retry_increment_node(state)
        assert result["retry_count"] == 2

    async def test_starts_from_zero(self):
        state = _base_state(retry_count=0)
        result = await retry_increment_node(state)
        assert result["retry_count"] == 1


# ------------------------------------------------------------------ #
# memory_update_node                                                    #
# ------------------------------------------------------------------ #

class TestMemoryUpdateNode:
    async def test_no_memory_no_error(self):
        edited = EditedChapter(chapter=1, volume=1, text="文本", word_count=2)
        state = _base_state(memory=None, edited_chapter=edited)
        result = await memory_update_node(state)
        assert result == {}

    async def test_stores_to_memory(self):
        mock_mem = MagicMock()
        mock_mem.store_paragraph = MagicMock()
        edited = EditedChapter(chapter=2, volume=1, text="最终文本内容", word_count=6)
        state = _base_state(memory=mock_mem, edited_chapter=edited)

        await memory_update_node(state)

        mock_mem.store_paragraph.assert_called_once()
        call_kwargs = mock_mem.store_paragraph.call_args
        assert call_kwargs[1]["chapter"] == 2 or call_kwargs[0][1] == 2

    async def test_memory_error_is_silent(self):
        """store_paragraph 抛出异常时不影响后续流程。"""
        mock_mem = MagicMock()
        mock_mem.store_paragraph = MagicMock(side_effect=RuntimeError("存储失败"))
        edited = EditedChapter(chapter=1, volume=1, text="文本", word_count=2)
        state = _base_state(memory=mock_mem, edited_chapter=edited)

        result = await memory_update_node(state)
        # 不抛出异常，返回空字典
        assert result == {}


# ------------------------------------------------------------------ #
# build_graph                                                           #
# ------------------------------------------------------------------ #

class TestBuildGraph:
    def test_graph_has_all_nodes(self):
        g = build_graph()
        # LangGraph 1.x: 节点存储在 _nodes 属性中
        nodes = set(g.nodes.keys()) if hasattr(g, "nodes") else set()
        expected = {"planner", "writer", "critic", "retry_increment", "editor", "memory_update"}
        for name in expected:
            assert name in nodes, f"Missing node: {name}"

    def test_graph_compiles_without_error(self):
        from langgraph.checkpoint.memory import MemorySaver
        from narrative_os.orchestrator.graph import compile_graph
        app = compile_graph(MemorySaver())
        assert app is not None


# ------------------------------------------------------------------ #
# run_chapter 端到端（全 Mock）                                          #
# ------------------------------------------------------------------ #

class TestRunChapterEndToEnd:
    async def test_full_pipeline_passes(self, monkeypatch):
        """Mock 所有 Agent，验证端到端流程返回 EditedChapter。"""
        from narrative_os.orchestrator.graph import run_chapter

        plan = _make_plan()
        draft = _make_draft(chapter=1)
        ctx = _make_write_context()
        edited = EditedChapter(chapter=1, volume=1, text="最终稿", word_count=3)

        # Mock PlannerAgent.plan
        monkeypatch.setattr(
            "narrative_os.orchestrator.graph.PlannerAgent.plan",
            AsyncMock(return_value=plan),
        )
        # Mock _build_write_context
        monkeypatch.setattr(
            "narrative_os.orchestrator.graph._build_write_context",
            AsyncMock(return_value=ctx),
        )
        # Mock WriterAgent.write
        monkeypatch.setattr(
            "narrative_os.orchestrator.graph.WriterAgent.write",
            AsyncMock(return_value=draft),
        )
        # Mock CriticAgent.review
        monkeypatch.setattr(
            "narrative_os.orchestrator.graph.CriticAgent.review",
            AsyncMock(return_value=_passing_critic()),
        )
        # Mock EditorAgent.edit
        monkeypatch.setattr(
            "narrative_os.orchestrator.graph.EditorAgent.edit",
            AsyncMock(return_value=edited),
        )

        result = await run_chapter(chapter=1, target_summary="测试", thread_id="test-001")

        assert result["edited_chapter"] is not None
        assert result["edited_chapter"].text == "最终稿"

    async def test_retry_logic(self, monkeypatch):
        """Critic 失败 → Writer 重试 → Critic 再次通过时最终完成。"""
        from narrative_os.orchestrator.graph import run_chapter

        plan = _make_plan()
        draft = _make_draft(chapter=2)
        ctx = _make_write_context()
        edited = EditedChapter(chapter=2, volume=1, text="重试后最终稿", word_count=6)

        critic_calls = [0]

        async def critic_side_effect(self, draft, context, **kwargs):
            critic_calls[0] += 1
            if critic_calls[0] == 1:
                return _failing_critic()   # 第一次失败
            return _passing_critic()       # 第二次通过

        monkeypatch.setattr("narrative_os.orchestrator.graph.PlannerAgent.plan",
                            AsyncMock(return_value=plan))
        monkeypatch.setattr("narrative_os.orchestrator.graph._build_write_context",
                            AsyncMock(return_value=ctx))
        monkeypatch.setattr("narrative_os.orchestrator.graph.WriterAgent.write",
                            AsyncMock(return_value=draft))
        monkeypatch.setattr("narrative_os.orchestrator.graph.CriticAgent.review",
                            critic_side_effect)
        monkeypatch.setattr("narrative_os.orchestrator.graph.EditorAgent.edit",
                            AsyncMock(return_value=edited))

        result = await run_chapter(chapter=2, target_summary="重试测试", thread_id="test-002")

        assert result["edited_chapter"] is not None
        assert critic_calls[0] == 2  # 确认调用了 2 次
