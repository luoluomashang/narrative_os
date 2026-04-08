"""tests/test_agents/test_planner.py — PlannerAgent 单元测试"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from narrative_os.agents.planner import (
    PlannerAgent,
    PlannerInput,
    PlannedNode,
    PlannerOutput,
    _extract_json,
)
from narrative_os.core.plot import PlotGraph


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _dispatch_tuple(content: str):
    """_dispatch returns (content, prompt_tokens, completion_tokens)."""
    return (content, 10, 20)


VALID_JSON_RESP = json.dumps({
    "outline": "第3章：主角闯入禁地，引发冲突",
    "nodes": [
        {"id": "ch3_01", "type": "setup", "summary": "场景建立", "tension": 0.2, "characters": ["李明"]},
        {"id": "ch3_02", "type": "conflict", "summary": "禁地警报", "tension": 0.7, "characters": ["李明"]},
        {"id": "ch3_03", "type": "climax",  "summary": "BOSS 现身", "tension": 0.9, "characters": ["李明", "BOSS"]},
    ],
    "edges": [
        {"from": "ch3_01", "to": "ch3_02", "relation": "causal"},
        {"from": "ch3_02", "to": "ch3_03", "relation": "causal"},
    ],
    "dialogue_goals": ["主角展现坚毅", "引出 BOSS 动机"],
    "hook": {"description": "门外传来脚步声", "type": "suspense"},
})


# ------------------------------------------------------------------ #
# _extract_json                                                         #
# ------------------------------------------------------------------ #

class TestExtractJson:
    def test_plain_json(self):
        data = _extract_json('{"a": 1}')
        assert data == {"a": 1}

    def test_json_code_block(self):
        text = '```json\n{"a": 2}\n```'
        assert _extract_json(text) == {"a": 2}

    def test_json_embedded_in_text(self):
        text = 'Here is the result:\n{"key": "val"}\nDone.'
        assert _extract_json(text) == {"key": "val"}

    def test_invalid_returns_none(self):
        assert _extract_json("not json at all") is None


# ------------------------------------------------------------------ #
# PlannerInput                                                          #
# ------------------------------------------------------------------ #

class TestPlannerInput:
    def test_defaults(self):
        inp = PlannerInput(chapter=1, target_summary="测试")
        assert inp.volume == 1
        assert inp.word_count_target == 2000
        assert inp.character_names == []

    def test_full(self):
        inp = PlannerInput(
            chapter=5, volume=2, target_summary="高潮",
            character_names=["甲", "乙"], constraints=["不得出现现代科技"],
        )
        assert inp.chapter == 5
        assert "甲" in inp.character_names


# ------------------------------------------------------------------ #
# PlannerOutput                                                         #
# ------------------------------------------------------------------ #

class TestPlannerOutput:
    def test_apply_to_graph(self):
        out = PlannerOutput(
            chapter_outline="测试大纲",
            planned_nodes=[
                PlannedNode(id="ch1_01", type="setup", summary="开场", tension=0.2),
                PlannedNode(id="ch1_02", type="climax", summary="高潮", tension=0.9),
            ],
            edge_pairs=[("ch1_01", "ch1_02", "causal")],
        )
        g = PlotGraph()
        out.apply_to_graph(g)
        assert g.node_count == 2
        assert g.edge_count == 1

    def test_apply_to_graph_skips_duplicate_nodes(self):
        g = PlotGraph()
        g.create_event("ch1_01", summary="已有节点")
        out = PlannerOutput(
            chapter_outline="",
            planned_nodes=[PlannedNode(id="ch1_01", type="setup", summary="重复")],
        )
        out.apply_to_graph(g)
        assert g.node_count == 1  # 仍然只有 1 个


# ------------------------------------------------------------------ #
# PlannerAgent                                                          #
# ------------------------------------------------------------------ #

class TestPlannerAgent:
    async def test_plan_returns_output(self, monkeypatch):
        agent = PlannerAgent()
        monkeypatch.setattr(agent._router, "_dispatch",
                            AsyncMock(return_value=_dispatch_tuple(VALID_JSON_RESP)))
        monkeypatch.setattr(agent._router, "_record_cost", lambda *a, **kw: None)

        inp = PlannerInput(chapter=3, target_summary="主角觉醒")
        result = await agent.plan(inp)

        assert isinstance(result, PlannerOutput)
        assert len(result.planned_nodes) == 3
        assert result.planned_nodes[0].id == "ch3_01"
        assert result.hook_type == "suspense"

    async def test_plan_applies_graph(self, monkeypatch):
        agent = PlannerAgent()
        monkeypatch.setattr(agent._router, "_dispatch",
                            AsyncMock(return_value=_dispatch_tuple(VALID_JSON_RESP)))
        monkeypatch.setattr(agent._router, "_record_cost", lambda *a, **kw: None)

        graph = PlotGraph()
        inp = PlannerInput(chapter=3, target_summary="主角觉醒")
        result = await agent.plan(inp)
        result.apply_to_graph(graph)

        assert graph.node_count == 3

    async def test_plan_fallback_on_invalid_json(self, monkeypatch):
        agent = PlannerAgent()
        monkeypatch.setattr(agent._router, "_dispatch",
                            AsyncMock(return_value=_dispatch_tuple("无效 JSON 文本")))
        monkeypatch.setattr(agent._router, "_record_cost", lambda *a, **kw: None)

        inp = PlannerInput(chapter=7, target_summary="测试降级")
        result = await agent.plan(inp)

        assert isinstance(result, PlannerOutput)
        assert len(result.planned_nodes) == 3       # 降级骨架
        assert result.planned_nodes[0].id == "ch7_01"

    async def test_tension_curve_matches_nodes(self, monkeypatch):
        agent = PlannerAgent()
        monkeypatch.setattr(agent._router, "_dispatch",
                            AsyncMock(return_value=_dispatch_tuple(VALID_JSON_RESP)))
        monkeypatch.setattr(agent._router, "_record_cost", lambda *a, **kw: None)

        inp = PlannerInput(chapter=3, target_summary="高张力章节")
        result = await agent.plan(inp)

        assert len(result.tension_curve) == len(result.planned_nodes)
        assert all(isinstance(t, float) for _, t in result.tension_curve)
