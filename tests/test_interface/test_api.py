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

    async def test_run_success_includes_benchmark_scores(self, monkeypatch):
        from narrative_os.schemas.benchmark import BenchmarkScore

        state = {
            "edited_chapter": _edited_chapter_mock(chapter=4),
            "critic_report": _critic_mock(),
            "retry_count": 0,
        }
        monkeypatch.setattr(
            "narrative_os.interface.api.run_chapter",
            AsyncMock(return_value=state),
        )
        benchmark_service = MagicMock()
        benchmark_service.score_text = AsyncMock(return_value=BenchmarkScore(
            score_id="score-1",
            project_id="default",
            run_id=None,
            chapter=4,
            profile_id="profile-1",
            humanness_score=0.71,
            adherence_score=0.83,
            dimension_scores={"scene_alignment": 0.83},
            violations=["对白密度偏高"],
            recommendations=[],
            created_at="2025-01-01T00:00:00Z",
        ))
        monkeypatch.setattr(
            "narrative_os.interface.services.benchmark_service.get_benchmark_service",
            lambda: benchmark_service,
        )

        async with await _client() as c:
            resp = await c.post("/chapters/run", json={
                "chapter": 4, "target_summary": "带对标评分的章节",
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["benchmark_adherence_score"] == pytest.approx(0.83)
        assert data["benchmark_humanness_score"] == pytest.approx(0.71)
        assert data["benchmark_violations"] == ["对白密度偏高"]

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

    async def test_project_status_reads_persisted_concept(self, monkeypatch):
        state = MagicMock(
            project_name="demo",
            current_chapter=0,
            current_volume=1,
            total_word_count=0,
            one_sentence="",
            chapters=[],
        )
        mgr = MagicMock()
        mgr.load_state.return_value = state
        mgr.state = state
        mgr.load_kb.return_value = {}
        mgr.list_versions.return_value = []

        world_repo = MagicMock()
        world_repo.has_published_world.return_value = False

        character_repo = MagicMock()
        character_repo.list_characters.return_value = []

        canon_commit = MagicMock()
        canon_commit.list_changesets.return_value = []

        class _FakeSession:
            async def __aenter__(self):
                return object()

            async def __aexit__(self, exc_type, exc, tb):
                return False

        concept = MagicMock(one_sentence="一句话概念", one_paragraph="", genre_tags=[])

        monkeypatch.setattr("narrative_os.interface.api.StateManager", MagicMock(return_value=mgr))
        monkeypatch.setattr("narrative_os.core.state.StateManager", MagicMock(return_value=mgr))
        monkeypatch.setattr("narrative_os.core.world_repository.get_world_repository", lambda: world_repo)
        monkeypatch.setattr("narrative_os.core.character_repository.get_character_repository", lambda: character_repo)
        monkeypatch.setattr("narrative_os.core.evolution.get_canon_commit", lambda _project_id: canon_commit)
        monkeypatch.setattr("narrative_os.infra.database.AsyncSessionLocal", lambda: _FakeSession())
        monkeypatch.setattr(
            "narrative_os.interface.services.world_service.WorldService.get_concept",
            AsyncMock(return_value=concept),
        )

        async with await _client() as c:
            resp = await c.get("/projects/demo/status")

        assert resp.status_code == 200
        data = resp.json()
        concept_node = next(node for node in data["workflow_nodes"] if node["step_id"] == "concept")
        assert concept_node["status"] == "completed"
        assert concept_node["statistic"] == "概念已初始化"


class TestWritingContextEndpoint:
    async def test_writing_context_returns_region_names(self, monkeypatch):
        from narrative_os.core.world import FactionState, WorldState

        world_repo = MagicMock()
        world_repo.get_published_world_state.return_value = WorldState(
            factions={
                "faction_001": FactionState(id="faction_001", name="雾灯会"),
            },
            geography={
                "region_001": {"id": "region_001", "name": "残忆外环"},
                "region_002": {"id": "region_002", "name": "灰塔内城"},
            },
            rules_of_world=["记忆有价"],
        )

        runtime = MagicMock(
            current_location="外环集市",
            current_agenda="调查禁城入口",
            current_pressure=0.2,
            recent_key_events=["找到残缺地图"],
        )
        character = MagicMock(name="沈烬")
        character.name = "沈烬"
        character.drive = MagicMock()
        character.runtime = runtime

        character_repo = MagicMock()
        character_repo.list_characters.return_value = [character]

        state_mgr = MagicMock()
        state_mgr.load_state.return_value = MagicMock()
        state_mgr.load_kb.return_value = {}
        state_mgr.get_last_hook.return_value = ""

        canon_commit = MagicMock()
        canon_commit.list_changesets.return_value = []

        monkeypatch.setattr("narrative_os.core.state.StateManager", MagicMock(return_value=state_mgr))
        monkeypatch.setattr("narrative_os.core.character_repository.get_character_repository", lambda: character_repo)
        monkeypatch.setattr("narrative_os.core.world_repository.get_world_repository", lambda: world_repo)
        monkeypatch.setattr("narrative_os.core.evolution.get_canon_commit", lambda _project_id: canon_commit)

        async with await _client() as c:
            resp = await c.get("/projects/demo/writing-context?chapter=1")

        assert resp.status_code == 200
        data = resp.json()
        assert data["world"]["factions"] == ["雾灯会"]
        assert data["world"]["regions"] == ["残忆外环", "灰塔内城"]
        assert data["world"]["rules"] == ["记忆有价"]


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
