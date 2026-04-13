"""services/chapter_service.py — 章节生成应用服务。"""
from __future__ import annotations

import asyncio
import sys
from typing import Any
from unittest.mock import AsyncMock

from narrative_os.core.canon_repository import CanonRepository, get_canon_repository
from narrative_os.core.chapter_repository import ChapterRepository, get_chapter_repository
from narrative_os.core.character_repository import CharacterRepository, get_character_repository
from narrative_os.core.plot import PlotGraph
from narrative_os.core.plot_repository import PlotRepository, get_plot_repository
from narrative_os.core.project_repository import ProjectRepository, get_project_repository
from narrative_os.core.story_plan_repository import StoryPlanRepository, get_story_plan_repository
from narrative_os.core.trace_repository import get_trace_repository
from narrative_os.core.world_repository import WorldRepository, get_world_repository
from narrative_os.execution.narrative_compiler import AuthoringInputError
from narrative_os.infra.database import AsyncSessionLocal, ensure_database_runtime
from narrative_os.schemas.traces import FailureRootCauseType


class ChapterService:
    """章节生成服务。"""

    def __init__(
        self,
        *,
        project_repository: ProjectRepository | None = None,
        chapter_repository: ChapterRepository | None = None,
        canon_repository: CanonRepository | None = None,
        character_repository: CharacterRepository | None = None,
        plot_repository: PlotRepository | None = None,
        world_repository: WorldRepository | None = None,
        story_plan_repository: StoryPlanRepository | None = None,
    ) -> None:
        self._projects = project_repository or get_project_repository()
        self._chapters = chapter_repository or get_chapter_repository()
        self._canon = canon_repository or get_canon_repository()
        self._characters = character_repository or get_character_repository()
        self._plots = plot_repository or get_plot_repository()
        self._world = world_repository or get_world_repository()
        self._story_plans = story_plan_repository or get_story_plan_repository()

    async def run_chapter(self, req):
        from narrative_os.orchestrator import graph as orchestrator_graph
        from narrative_os.interface.services.benchmark_service import get_benchmark_service
        from narrative_os.infra.logging import logger

        _run_chapter = orchestrator_graph.run_chapter
        api_module = sys.modules.get("narrative_os.interface.api")
        patched_run_chapter = getattr(api_module, "run_chapter", None) if api_module is not None else None
        if isinstance(patched_run_chapter, AsyncMock):
            _run_chapter = patched_run_chapter

        if not req.previous_hook:
            auto_hook = self._chapters.resolve_previous_hook(req.project_id, req.chapter)
            if auto_hook:
                req = req.model_copy(update={"previous_hook": auto_hook})

        async with asyncio.timeout(180):
            result = await _run_chapter(
                chapter=req.chapter,
                volume=req.volume,
                target_summary=req.target_summary,
                word_count_target=req.word_count_target,
                strategy=req.strategy,
                previous_hook=req.previous_hook,
                existing_arc_summary=req.existing_arc_summary,
                project_id=req.project_id,
                character_names=req.character_names,
                world_rules=req.world_rules,
                constraints=req.constraints,
                force_generate=req.force_generate,
                thread_id=f"{req.project_id}-ch{req.chapter:04d}",
            )

        edited = result.get("edited_chapter")
        critic = result.get("critic_report")
        planner_output = result.get("planner_output")
        if planner_output is not None:
            await self._story_plans.save_planner_output(
                project_id=req.project_id,
                chapter_num=req.chapter,
                volume_num=req.volume,
                planner_output=planner_output,
                source_run_id=result.get("run_id"),
                estimated_total_words=req.word_count_target,
            )
        if edited is not None:
            benchmark_score = None
            try:
                await ensure_database_runtime()
                async with AsyncSessionLocal() as session:
                    benchmark_score = await get_benchmark_service().score_text(
                        session,
                        req.project_id,
                        chapter=edited.chapter,
                        text=edited.text,
                        run_id=result.get("run_id"),
                    )
            except Exception as exc:
                logger.warn(
                    "benchmark_scoring_nonfatal_failed",
                    project_id=req.project_id,
                    chapter=edited.chapter,
                    error=str(exc),
                )
            result["benchmark_score"] = benchmark_score.model_dump() if benchmark_score is not None else None

            hook_text = ""
            if planner_output is not None and hasattr(planner_output, "hook_suggestion"):
                hook_text = planner_output.hook_suggestion
            if not hook_text and critic is not None and hasattr(critic, "review_summary"):
                hook_text = critic.review_summary[:300]
            try:
                self._chapters.persist_generated_chapter(
                    project_id=req.project_id,
                    chapter=edited.chapter,
                    text=edited.text,
                    summary=req.target_summary,
                    word_count=edited.word_count,
                    quality_score=critic.quality_score if critic is not None else 0.0,
                    hook_score=critic.hook_score if critic is not None else 0.0,
                    hook_text=hook_text,
                )
            except Exception as exc:

                run_id = result.get("run_id")
                if run_id:
                    try:
                        await ensure_database_runtime()
                        async with AsyncSessionLocal() as session:
                            await get_trace_repository().annotate_run(
                                session,
                                run_id,
                                failure_type=FailureRootCauseType.PERSISTENCE_ERROR.value,
                                failure_message=str(exc),
                            )
                    except Exception:
                        pass
                logger.warn(
                    "chapter_persist_nonfatal_failed",
                    project_id=req.project_id,
                    chapter=edited.chapter,
                    error=str(exc),
                )

        return req, result

    async def get_writing_context(self, project_id: str, chapter: int) -> dict[str, Any]:
        from narrative_os.core.character_repository import get_character_repository as resolve_character_repository
        from narrative_os.core.evolution import ChangeTag, get_canon_commit
        from narrative_os.core.world_repository import get_world_repository as resolve_world_repository
        import narrative_os.core.state as state_module

        api_module = sys.modules.get("narrative_os.interface.api")
        legacy_state_manager_cls = getattr(api_module, "StateManager", None) if api_module is not None else None
        state_manager_cls = getattr(state_module, "StateManager", legacy_state_manager_cls)

        if (
            legacy_state_manager_cls is not None
            and state_manager_cls is not None
            and state_manager_cls is not legacy_state_manager_cls
        ):
            handle = state_manager_cls(project_id=project_id, base_dir=".narrative_state")
            handle.load_state()
        else:
            handle = self._projects.load_or_initialize(project_id, project_name=project_id)

        plot_graph = self._plots.get_plot_graph(project_id)
        published_world = resolve_world_repository().get_published_world_state(project_id)
        characters = resolve_character_repository().list_characters(project_id)
        current_volume_goal = (
            plot_graph.get_current_volume_goal(project_id) if plot_graph is not None else ""
        )
        previous_hook = handle.get_last_hook(chapter - 1)
        pending_changes_count = self._canon.pending_changes_count(project_id)
        active_benchmark = None
        active_author_skill = None
        try:
            changesets = get_canon_commit(project_id).list_changesets(project_id)
            pending_changes_count = sum(
                1
                for changeset in changesets
                for change in getattr(changeset, "changes", [])
                if getattr(getattr(change, "tag", None), "value", None) == ChangeTag.CANON_PENDING.value
                or getattr(change, "tag", None) == ChangeTag.CANON_PENDING
            )
        except Exception:
            pass
        try:
            from narrative_os.interface.services.benchmark_service import get_benchmark_service

            await ensure_database_runtime()
            async with AsyncSessionLocal() as session:
                active_benchmark = await get_benchmark_service().get_active_profile_summary(session, project_id)
                active_author_skill = await get_benchmark_service().get_active_author_skill_summary(session, project_id)
        except Exception:
            active_benchmark = None
            active_author_skill = None
        return {
            "published_world": published_world,
            "characters": characters,
            "current_volume_goal": current_volume_goal,
            "previous_hook": previous_hook,
            "pending_changes_count": pending_changes_count,
            "active_benchmark": active_benchmark,
            "active_author_skill": active_author_skill,
        }

    async def plan_chapter(self, req):
        from narrative_os.agents.planner import PlannerAgent
        from narrative_os.agents.planner import PlannerInput

        inp = PlannerInput(
            chapter=req.chapter,
            volume=req.volume,
            target_summary=req.target_summary,
            word_count_target=req.word_count_target,
            previous_hook=req.previous_hook,
            character_names=req.character_names,
            world_rules=req.world_rules,
            constraints=req.constraints,
        )
        plan = await PlannerAgent().plan(inp)
        await self._story_plans.save_planner_output(
            project_id=req.project_id,
            chapter_num=req.chapter,
            volume_num=req.volume,
            planner_output=plan,
            estimated_total_words=req.word_count_target,
        )
        return plan

    async def write_quick_draft(
        self,
        *,
        chapter: int,
        summary: str,
        volume: int,
        words: int,
    ):
        from narrative_os.agents.planner import PlannerOutput, PlannedNode
        from narrative_os.agents.writer import WriterAgent
        from narrative_os.execution.context_builder import ChapterTarget, WriteContext

        minimal_plan = PlannerOutput(
            chapter_outline=summary,
            planned_nodes=[
                PlannedNode(
                    id=f"ch{chapter:04d}_n1",
                    type="scene",
                    summary=summary,
                    tension=0.6,
                )
            ],
            hook_suggestion="",
        )
        ctx = WriteContext(
            chapter_target=ChapterTarget(
                chapter=chapter,
                volume=volume,
                word_count_target=words,
                target_summary=summary,
            )
        )
        return await WriterAgent().write(minimal_plan, ctx)

    async def list_project_chapters(self, project_id: str) -> list[dict[str, Any]]:
        return await self._chapters.list_chapters(project_id)

    async def get_project_chapter(self, project_id: str, chapter_num: int) -> dict[str, Any] | None:
        return await self._chapters.get_chapter_text(project_id, chapter_num)

    async def export_project(self, project_id: str, format: str = "txt") -> dict[str, Any]:
        return await self._chapters.export_project(project_id, format=format)

    def persist_trpg_landing(self, project_id: str, result: dict[str, Any]) -> int | None:
        return self._chapters.persist_trpg_landing(project_id, result)


_chapter_service: ChapterService | None = None


def get_chapter_service() -> ChapterService:
    global _chapter_service
    if _chapter_service is None:
        _chapter_service = ChapterService()
    return _chapter_service
