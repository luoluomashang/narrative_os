"""tests/test_interface/test_api.py — FastAPI REST API 单元测试"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from narrative_os.interface.api import app


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _edited_chapter_mock(chapter: int = 1):
    m = MagicMock()
    m.chapter = chapter
    m.volume = 1
    m.text = "最终章节文本"
    m.word_count = 6
    m.change_ratio = 0.15
    return m


def _critic_mock(passed: bool = True):
    m = MagicMock()
    m.quality_score = 0.8
    m.hook_score = 0.7
    m.passed = passed
    return m


# ------------------------------------------------------------------ #
# GET /health                                                           #
# ------------------------------------------------------------------ #

class TestHealthEndpoint:
    async def test_health_returns_200(self):
        async with await _client() as c:
            resp = await c.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ------------------------------------------------------------------ #
# POST /chapters/plan                                                   #
# ------------------------------------------------------------------ #

class TestPlanEndpoint:
    async def test_plan_success(self, monkeypatch):
        from narrative_os.agents.planner import PlannedNode, PlannerOutput

        plan = PlannerOutput(
            chapter_outline="测试大纲",
            planned_nodes=[
                PlannedNode(id="ch1_01", type="setup", summary="开场", tension=0.2),
                PlannedNode(id="ch1_02", type="climax", summary="高潮", tension=0.9),
            ],
            edge_pairs=[],
            dialogue_goals=["对话1"],
            hook_suggestion="悬念结尾",
            hook_type="suspense",
            tension_curve=[("ch1_01", 0.2), ("ch1_02", 0.9)],
        )
        monkeypatch.setattr(
            "narrative_os.interface.api.PlannerAgent.plan",
            AsyncMock(return_value=plan),
        )

        async with await _client() as c:
            resp = await c.post("/chapters/plan", json={
                "chapter": 1, "target_summary": "主角觉醒"
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter_outline"] == "测试大纲"
        assert len(data["planned_nodes"]) == 2
        assert data["hook_type"] == "suspense"

    async def test_plan_llm_failure_returns_500(self, monkeypatch):
        monkeypatch.setattr(
            "narrative_os.interface.api.PlannerAgent.plan",
            AsyncMock(side_effect=RuntimeError("LLM 超时")),
        )

        async with await _client() as c:
            resp = await c.post("/chapters/plan", json={
                "chapter": 2, "target_summary": "测试"
            })

        assert resp.status_code == 500
        assert "规划失败" in resp.json()["detail"]

    async def test_plan_missing_required_field(self):
        async with await _client() as c:
            resp = await c.post("/chapters/plan", json={"chapter": 1})  # missing target_summary
        assert resp.status_code == 422


# ------------------------------------------------------------------ #
# POST /chapters/run                                                    #
# ------------------------------------------------------------------ #

class TestRunEndpoint:
    async def test_run_success(self, monkeypatch):
        state = {
            "edited_chapter": _edited_chapter_mock(chapter=3),
            "critic_report": _critic_mock(),
            "retry_count": 0,
        }
        monkeypatch.setattr(
            "narrative_os.interface.api.run_chapter",
            AsyncMock(return_value=state),
        )

        async with await _client() as c:
            resp = await c.post("/chapters/run", json={
                "chapter": 3, "target_summary": "高潮章节",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 3
        assert data["text"] == "最终章节文本"
        assert data["passed"] is True

    async def test_run_no_edited_chapter_returns_500(self, monkeypatch):
        monkeypatch.setattr(
            "narrative_os.interface.api.run_chapter",
            AsyncMock(return_value={"edited_chapter": None, "critic_report": None,
                                    "retry_count": 0}),
        )

        async with await _client() as c:
            resp = await c.post("/chapters/run", json={
                "chapter": 1, "target_summary": "测试"
            })

        assert resp.status_code == 500

    async def test_run_llm_exception_returns_500(self, monkeypatch):
        monkeypatch.setattr(
            "narrative_os.interface.api.run_chapter",
            AsyncMock(side_effect=RuntimeError("模拟错误")),
        )

        async with await _client() as c:
            resp = await c.post("/chapters/run", json={
                "chapter": 1, "target_summary": "测试"
            })

        assert resp.status_code == 500


# ------------------------------------------------------------------ #
# GET /cost                                                             #
# ------------------------------------------------------------------ #

class TestCostEndpoint:
    async def test_cost_returns_summary(self, monkeypatch):
        from narrative_os.infra.cost import cost_ctrl
        mock_summary = {
            "used": 12345, "budget": 100000, "ratio": 0.123,
            "by_skill": {"scene_generator": 8000},
            "by_agent": {"writer": 8000},
        }
        monkeypatch.setattr(cost_ctrl, "summary", lambda: mock_summary)

        async with await _client() as c:
            resp = await c.get("/cost")

        assert resp.status_code == 200
        data = resp.json()
        assert data["used_tokens"] == 12345
        assert data["budget_tokens"] == 100000
        assert "scene_generator" in data["by_skill"]


# ------------------------------------------------------------------ #
# POST /metrics                                                         #
# ------------------------------------------------------------------ #

class TestMetricsEndpoint:
    def _draft_payload(self) -> dict:
        from narrative_os.agents.writer import ChapterDraft
        from narrative_os.skills.scene import SceneOutput
        draft = ChapterDraft(
            chapter=2, volume=1,
            scenes=[SceneOutput(text="场景文本", word_count=500, chapter=2)],
            draft_text="场景文本",
            total_words=500, avg_tension=0.6, hook_score=0.7,
        )
        return {"draft": draft.model_dump(), "word_count_target": 1000}

    async def test_metrics_success(self):
        async with await _client() as c:
            resp = await c.post("/metrics", json=self._draft_payload())

        assert resp.status_code == 200
        data = resp.json()
        assert data["chapter"] == 2
        assert 0.0 <= data["overall_score"] <= 1.0
        assert data["tension_trend"] in {"rising", "falling", "volatile", "flat"}

    async def test_invalid_draft_returns_422(self):
        async with await _client() as c:
            resp = await c.post("/metrics", json={"draft": {"bad": "data"}})
        assert resp.status_code == 422


# ------------------------------------------------------------------ #
# GET /projects/{id}/status                                             #
# ------------------------------------------------------------------ #

class TestProjectStatusEndpoint:
    async def test_unknown_project_404(self, monkeypatch):
        monkeypatch.setattr(
            "narrative_os.interface.api.StateManager",
            MagicMock(return_value=MagicMock(
                load_state=MagicMock(side_effect=FileNotFoundError("not found"))
            )),
        )

        async with await _client() as c:
            resp = await c.get("/projects/nonexistent/status")

        assert resp.status_code == 404

    async def test_project_status_500_on_generic_error(self, monkeypatch):
        """Generic exception in load_state → 500."""
        monkeypatch.setattr(
            "narrative_os.interface.api.StateManager",
            MagicMock(return_value=MagicMock(
                load_state=MagicMock(side_effect=RuntimeError("disk error"))
            )),
        )
        async with await _client() as c:
            resp = await c.get("/projects/bad_project/status")
        assert resp.status_code == 500


# ------------------------------------------------------------------ #
# TRPG session error paths                                              #
# ------------------------------------------------------------------ #

class TestSessionErrorPaths:
    async def test_step_internal_error_returns_500(self, monkeypatch):
        """When InteractiveAgent.step raises, step endpoint returns 500."""
        from narrative_os.agents.interactive import (
            InteractiveAgent, SessionConfig, SessionPhase, InteractiveSession
        )
        from narrative_os.interface.api import _sessions
        import time, uuid

        # Manually plant a session in PING_PONG state
        agent = InteractiveAgent()
        cfg = SessionConfig(project_id="test", opening_prompt="测试开场")
        session = agent.create_session(cfg)
        # Force to PING_PONG phase
        from narrative_os.agents.interactive import SessionPhase as SP
        object.__setattr__(session, "phase", SP.PING_PONG)
        sid = session.session_id
        _sessions[sid] = (session, time.time())

        monkeypatch.setattr(
            "narrative_os.interface.api._interactive_agent.step",
            AsyncMock(side_effect=RuntimeError("LLM 超时")),
        )

        async with await _client() as c:
            resp = await c.post(f"/sessions/{sid}/step",
                                json={"user_input": "我向前走"})

        # Clean up
        _sessions.pop(sid, None)
        assert resp.status_code == 500

    async def test_interrupt_error_returns_500(self, monkeypatch):
        """When interrupt raises, endpoint returns 500."""
        from narrative_os.agents.interactive import (
            InteractiveAgent, SessionConfig, SessionPhase
        )
        from narrative_os.interface.api import _sessions
        import time

        agent = InteractiveAgent()
        cfg = SessionConfig(project_id="test", opening_prompt="测试")
        session = agent.create_session(cfg)
        from narrative_os.agents.interactive import SessionPhase as SP
        object.__setattr__(session, "phase", SP.PING_PONG)
        sid = session.session_id
        _sessions[sid] = (session, time.time())

        monkeypatch.setattr(
            "narrative_os.interface.api._interactive_agent.interrupt",
            AsyncMock(side_effect=RuntimeError("帮回失败")),
        )

        async with await _client() as c:
            resp = await c.post(f"/sessions/{sid}/interrupt",
                                json={"bangui_command": "帮回主动1"})

        _sessions.pop(sid, None)
        assert resp.status_code == 500
