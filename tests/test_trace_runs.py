from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import pytest

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.editor import EditedChapter
from narrative_os.agents.planner import PlannedNode, PlannerOutput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.execution.context_builder import ChapterTarget, WriteContext
from narrative_os.interface.api import app
from narrative_os.orchestrator.graph import run_chapter
from narrative_os.schemas.traces import Artifact, ArtifactType
from narrative_os.skills.consistency import ConsistencyReport
from narrative_os.skills.scene import SceneOutput
from narrative_os.core.governance import GovernanceHook, RunPolicy, get_governance_plane


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def trace_runtime_db(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'trace_runs.db'}"
    monkeypatch.setenv("NARRATIVE_DB_URL", db_url)

    import narrative_os.infra.database as dbm

    _run(dbm.init_db())
    return db_url


@pytest.fixture()
def client(trace_runtime_db):
    return TestClient(app, raise_server_exceptions=False)


def _plan() -> PlannerOutput:
    return PlannerOutput(
        chapter_outline="测试大纲",
        planned_nodes=[
            PlannedNode(id="ch1_01", type="setup", summary="开场", tension=0.2),
            PlannedNode(id="ch1_02", type="climax", summary="冲突", tension=0.9),
        ],
        edge_pairs=[("ch1_01", "ch1_02", "causal")],
        dialogue_goals=["推进冲突"],
        tension_curve=[("ch1_01", 0.2), ("ch1_02", 0.9)],
        hook_suggestion="留下悬念",
        raw_llm_output="{\"outline\": \"测试大纲\"}",
    )


def _draft(chapter: int = 1, hook_score: float = 0.8) -> ChapterDraft:
    return ChapterDraft(
        chapter=chapter,
        volume=1,
        scenes=[SceneOutput(text="正文片段", word_count=900, tension_score=0.7, hook_score=hook_score, chapter=chapter)],
        draft_text="正文片段",
        total_words=900,
        avg_tension=0.7,
        hook_score=hook_score,
    )


def _ctx(chapter: int = 1) -> WriteContext:
    return WriteContext(chapter_target=ChapterTarget(chapter=chapter, volume=1, target_summary="追踪测试", word_count_target=1500))


def _critic(passed: bool, quality: float, hook: float, instructions: list[str] | None = None) -> CriticReport:
    return CriticReport(
        passed=passed,
        quality_score=quality,
        hook_score=hook,
        consistency_report=ConsistencyReport(passed=passed, issues=[], score=max(quality, 0.1)),
        rewrite_instructions=instructions or [],
        review_summary="审查摘要",
    )


async def _planner_side_effect(self, inp, strategy, run_context=None):
    plan = _plan()
    if run_context is not None:
        await run_context.emit_artifact(
            Artifact(
                artifact_type=ArtifactType.OUTLINE,
                agent_name="planner",
                input_summary=inp.target_summary,
                output_content=plan.chapter_outline,
                quality_scores={"node_count": float(len(plan.planned_nodes))},
            )
        )
    return plan


async def _writer_side_effect(self, plan, context, strategy, run_context=None, retry_count=0, retry_reason=None):
    draft = _draft(chapter=context.chapter_target.chapter)
    if run_context is not None:
        await run_context.emit_artifact(
            Artifact(
                artifact_type=ArtifactType.DRAFT,
                agent_name="writer",
                input_summary=context.chapter_target.target_summary,
                output_content=draft.draft_text,
                quality_scores={"avg_tension": draft.avg_tension},
                retry_count=retry_count,
                retry_reason=retry_reason,
            )
        )
    return draft


async def _critic_side_effect(self, draft, context, characters=None, world=None, plot_graph=None, run_context=None):
    report = _critic(True, 0.82, 0.88)
    if run_context is not None:
        await run_context.emit_artifact(
            Artifact(
                artifact_type=ArtifactType.CRITIQUE,
                agent_name="critic",
                input_summary=draft.draft_text,
                output_content=report.review_summary,
                quality_scores={"quality_score": report.quality_score, "hook_score": report.hook_score},
            )
        )
    return report


async def _editor_side_effect(self, draft, critic_report, strategy, run_context=None):
    edited = EditedChapter(chapter=draft.chapter, volume=draft.volume, text="最终正文", word_count=4, change_ratio=0.2)
    if run_context is not None:
        await run_context.emit_artifact(
            Artifact(
                artifact_type=ArtifactType.FINAL_TEXT,
                agent_name="editor",
                input_summary=draft.draft_text,
                output_content=edited.text,
                quality_scores={"change_ratio": edited.change_ratio},
            )
        )
    return edited


def test_run_steps_endpoint_returns_five_agent_tree(client, monkeypatch):
    project_id = f"trace-{uuid.uuid4().hex[:8]}"

    monkeypatch.setattr("narrative_os.orchestrator.graph._build_write_context", AsyncMock(return_value=_ctx()))
    monkeypatch.setattr("narrative_os.orchestrator.graph.PlannerAgent.plan", _planner_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.WriterAgent.write", _writer_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.CriticAgent.review", _critic_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.EditorAgent.edit", _editor_side_effect)

    result = _run(run_chapter(chapter=1, target_summary="追踪测试", project_id=project_id, thread_id=f"{project_id}-run"))
    run_id = result["run_id"]

    list_resp = client.get(f"/projects/{project_id}/runs")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"][0]["run_id"] == run_id

    resp = client.get(f"/runs/{run_id}/steps")
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] == run_id
    assert [step["agent_name"] for step in body["steps"]] == ["planner", "writer", "critic", "editor", "maintenance"]
    assert all(step["artifact"] is not None for step in body["steps"])


def test_retry_trace_records_retry_reason(client, monkeypatch):
    project_id = f"trace-retry-{uuid.uuid4().hex[:8]}"
    critic_calls = {"count": 0}

    async def critic_with_retry(self, draft, context, characters=None, world=None, plot_graph=None, run_context=None):
        critic_calls["count"] += 1
        if critic_calls["count"] == 1:
            report = _critic(False, 0.35, 0.2, ["加强结尾钩子"])
        else:
            report = _critic(True, 0.81, 0.77)
        if run_context is not None:
            await run_context.emit_artifact(
                Artifact(
                    artifact_type=ArtifactType.CRITIQUE,
                    agent_name="critic",
                    input_summary=draft.draft_text,
                    output_content=report.review_summary,
                    quality_scores={"quality_score": report.quality_score},
                    retry_reason="；".join(report.rewrite_instructions[:3]) if report.rewrite_instructions else None,
                )
            )
        return report

    monkeypatch.setattr("narrative_os.orchestrator.graph._build_write_context", AsyncMock(return_value=_ctx()))
    monkeypatch.setattr("narrative_os.orchestrator.graph.PlannerAgent.plan", _planner_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.WriterAgent.write", _writer_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.CriticAgent.review", critic_with_retry)
    monkeypatch.setattr("narrative_os.orchestrator.graph.EditorAgent.edit", _editor_side_effect)

    result = _run(run_chapter(chapter=1, target_summary="重试追踪", project_id=project_id, thread_id=f"{project_id}-run"))
    run_id = result["run_id"]

    resp = client.get(f"/runs/{run_id}/steps")
    assert resp.status_code == 200
    writer_step = next(step for step in resp.json()["steps"] if step["agent_name"] == "writer")
    assert writer_step["artifact"]["retry_count"] == 1
    assert "加强结尾钩子" in writer_step["artifact"]["retry_reason"]


def test_run_trace_uses_current_runtime_database(client, monkeypatch, tmp_path):
    project_id = f"trace-runtime-{uuid.uuid4().hex[:8]}"

    import narrative_os.infra.database as dbm

    active_db_url = dbm.DATABASE_URL
    legacy_db_path = tmp_path / "legacy_runtime.db"
    monkeypatch.setenv("NARRATIVE_DB_URL", f"sqlite+aiosqlite:///{legacy_db_path}")
    _run(dbm.init_db())
    monkeypatch.setenv("NARRATIVE_DB_URL", active_db_url)

    monkeypatch.setattr("narrative_os.orchestrator.graph._build_write_context", AsyncMock(return_value=_ctx()))
    monkeypatch.setattr("narrative_os.orchestrator.graph.PlannerAgent.plan", _planner_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.WriterAgent.write", _writer_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.CriticAgent.review", _critic_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.EditorAgent.edit", _editor_side_effect)

    result = _run(run_chapter(chapter=1, target_summary="运行时数据库切换", project_id=project_id, thread_id=f"{project_id}-run"))
    run_id = result["run_id"]

    list_resp = client.get(f"/projects/{project_id}/runs")
    assert list_resp.status_code == 200
    assert list_resp.json()["items"][0]["run_id"] == run_id


def test_hitl_pause_and_approve_flow(client, monkeypatch):
    project_id = f"trace-hitl-{uuid.uuid4().hex[:8]}"
    plane = get_governance_plane(project_id)
    plane.save_policy(project_id, RunPolicy(hitl_on_low_quality=True, quality_threshold=0.6))
    plane.register_hook(GovernanceHook.POST_RUN, plane.make_quality_guard(project_id))

    async def low_quality_critic(self, draft, context, characters=None, world=None, plot_graph=None, run_context=None):
        report = _critic(True, 0.42, 0.7)
        if run_context is not None:
            await run_context.emit_artifact(
                Artifact(
                    artifact_type=ArtifactType.CRITIQUE,
                    agent_name="critic",
                    input_summary=draft.draft_text,
                    output_content=report.review_summary,
                    quality_scores={"quality_score": report.quality_score},
                )
            )
        return report

    monkeypatch.setattr("narrative_os.orchestrator.graph._build_write_context", AsyncMock(return_value=_ctx()))
    monkeypatch.setattr("narrative_os.orchestrator.graph.PlannerAgent.plan", _planner_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.WriterAgent.write", _writer_side_effect)
    monkeypatch.setattr("narrative_os.orchestrator.graph.CriticAgent.review", low_quality_critic)
    monkeypatch.setattr("narrative_os.orchestrator.graph.EditorAgent.edit", _editor_side_effect)

    result = _run(run_chapter(chapter=1, target_summary="HITL 测试", project_id=project_id, thread_id=f"{project_id}-run"))
    run_id = result["run_id"]
    assert result["hitl_required"] is True

    paused = client.get(f"/runs/{run_id}")
    assert paused.status_code == 200
    assert paused.json()["status"] == "paused"
    assert paused.json()["approval_checkpoint"] is not None

    approve_resp = client.post(f"/runs/{run_id}/approve", json={"decision": "approve"})
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "completed"

    final = client.get(f"/runs/{run_id}")
    assert final.status_code == 200
    assert final.json()["status"] == "completed"
    assert final.json()["approval_checkpoint"]["decision"] == "approve"