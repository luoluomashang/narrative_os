from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_story_plan_repository_persists_fallback_mapping(tmp_path, monkeypatch):
    db_path = tmp_path / "story_plan.db"
    monkeypatch.setenv("NARRATIVE_DB_URL", f"sqlite+aiosqlite:///{db_path}")

    import narrative_os.infra.database as dbm
    await dbm.init_db()

    from narrative_os.agents.planner import PlannedNode, PlannerOutput
    from narrative_os.core.story_plan_repository import StoryPlanRepository

    repository = StoryPlanRepository()
    output = PlannerOutput(
        chapter_outline="主角进入北境，发现宗门异动。",
        planned_nodes=[
            PlannedNode(id="beat-1", type="setup", summary="进入北境", tension=0.3, characters=["主角"]),
            PlannedNode(id="beat-2", type="conflict", summary="宗门异动", tension=0.8, characters=["主角", "长老"]),
        ],
        dialogue_goals=["确认异动来源"],
        tension_curve=[("setup", 0.3), ("conflict", 0.8)],
        hook_suggestion="长老突然失踪",
    )

    saved = await repository.save_planner_output(
        project_id="proj-story",
        chapter_num=7,
        volume_num=2,
        planner_output=output,
        source_run_id="run-77",
        estimated_total_words=2400,
    )

    assert saved.project_id == "proj-story"
    assert saved.chapter_num == 7
    assert saved.volume_num == 2
    assert saved.hook == "长老突然失踪"
    assert saved.dialogue_goals == ["确认异动来源"]
    assert len(saved.scene_beats) == 2
    assert saved.scene_beats[0].beat_key == "beat-1"
    assert saved.scene_beats[1].source_node_ids == ["beat-2"]
    assert saved.scene_beats[0].estimated_words == 1200

    loaded = await repository.get_chapter_plan("proj-story", 7, 2)
    assert loaded is not None
    assert loaded.summary == "主角进入北境，发现宗门异动。"
    assert loaded.source_run_id == "run-77"
    assert [beat.label for beat in loaded.scene_beats] == ["setup", "conflict"]


@pytest.mark.asyncio
async def test_chapter_service_plan_chapter_persists_story_plan(monkeypatch):
    from narrative_os.agents.planner import PlannedNode, PlannerOutput
    from narrative_os.interface.services.chapter_service import ChapterService

    save_mock = pytest.AsyncMock(return_value=None) if hasattr(pytest, 'AsyncMock') else None
    if save_mock is None:
        from unittest.mock import AsyncMock
        save_mock = AsyncMock(return_value=None)

    class _Repo:
        async def save_planner_output(self, **kwargs):
            return await save_mock(**kwargs)

    req = type(
        "Req",
        (),
        {
            "chapter": 5,
            "volume": 1,
            "target_summary": "摘要",
            "word_count_target": 1800,
            "previous_hook": "",
            "character_names": [],
            "world_rules": [],
            "constraints": [],
            "project_id": "proj-service",
        },
    )()

    output = PlannerOutput(
        chapter_outline="章节规划",
        planned_nodes=[PlannedNode(id="n1", summary="场景一", tension=0.5, characters=[])],
        hook_suggestion="下章钩子",
    )

    from unittest.mock import AsyncMock, patch

    service = ChapterService(story_plan_repository=_Repo())
    with patch("narrative_os.agents.planner.PlannerAgent.plan", new=AsyncMock(return_value=output)):
        result = await service.plan_chapter(req)

    assert result.chapter_outline == "章节规划"
    save_mock.assert_awaited_once()
    assert save_mock.await_args.kwargs["project_id"] == "proj-service"
    assert save_mock.await_args.kwargs["chapter_num"] == 5
