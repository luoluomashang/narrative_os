"""core/story_plan_repository.py — 多尺度剧情模型持久化入口。"""
from __future__ import annotations

import json

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from narrative_os.agents.planner import PlannerOutput
from narrative_os.infra.database import AsyncSessionLocal, ensure_database_runtime
from narrative_os.infra.models import (
    BookPlanRecord,
    ChapterPlanRecord,
    SceneBeatRecord,
    VolumePlanRecord,
)
from narrative_os.schemas.story_plans import BookPlan, ChapterPlan, SceneBeat, VolumePlan


class StoryPlanRepository:
    async def save_planner_output(
        self,
        *,
        project_id: str,
        chapter_num: int,
        volume_num: int,
        planner_output: PlannerOutput,
        source_run_id: str | None = None,
        estimated_total_words: int = 0,
        user_id: str = "local",
    ) -> ChapterPlan:
        chapter_plan = ChapterPlan.from_planner_output(
            project_id=project_id,
            chapter_num=chapter_num,
            volume_num=volume_num,
            planner_output=planner_output,
            source_run_id=source_run_id,
            estimated_total_words=estimated_total_words,
            user_id=user_id,
        )
        return await self.save_chapter_plan(chapter_plan)

    async def save_chapter_plan(self, chapter_plan: ChapterPlan) -> ChapterPlan:
        await ensure_database_runtime()
        async with AsyncSessionLocal() as session:
            book = await self._ensure_book_plan(session, chapter_plan.project_id, chapter_plan.volume_num, chapter_plan.user_id)
            volume = await self._ensure_volume_plan(session, book, chapter_plan)

            result = await session.execute(
                select(ChapterPlanRecord)
                .where(ChapterPlanRecord.project_id == chapter_plan.project_id)
                .where(ChapterPlanRecord.volume_num == chapter_plan.volume_num)
                .where(ChapterPlanRecord.chapter_num == chapter_plan.chapter_num)
            )
            record = result.scalar_one_or_none()
            if record is None:
                record = ChapterPlanRecord(
                    volume_plan_id=volume.id,
                    project_id=chapter_plan.project_id,
                    chapter_num=chapter_plan.chapter_num,
                    volume_num=chapter_plan.volume_num,
                )
                session.add(record)
                await session.flush()
            else:
                record.volume_plan_id = volume.id

            record.title = chapter_plan.title
            record.summary = chapter_plan.summary
            record.hook = chapter_plan.hook
            record.tension_target = chapter_plan.tension_target
            record.dialogue_goals_json = json.dumps(chapter_plan.dialogue_goals, ensure_ascii=False)
            record.legacy_outline_text = chapter_plan.legacy_outline_text
            record.source_run_id = chapter_plan.source_run_id
            record.user_id = chapter_plan.user_id

            await session.execute(delete(SceneBeatRecord).where(SceneBeatRecord.chapter_plan_id == record.id))
            await session.flush()
            for beat in chapter_plan.scene_beats:
                session.add(
                    SceneBeatRecord(
                        chapter_plan_id=record.id,
                        beat_index=beat.beat_index,
                        beat_key=beat.beat_key,
                        label=beat.label,
                        objective=beat.objective,
                        conflict=beat.conflict,
                        outcome=beat.outcome,
                        tension=beat.tension,
                        location=beat.location,
                        characters_json=json.dumps(beat.characters, ensure_ascii=False),
                        source_node_ids_json=json.dumps(beat.source_node_ids, ensure_ascii=False),
                        estimated_words=beat.estimated_words,
                        user_id=beat.user_id,
                    )
                )

            await session.commit()
            return await self.get_chapter_plan(chapter_plan.project_id, chapter_plan.chapter_num, chapter_plan.volume_num, session=session) or chapter_plan

    async def get_chapter_plan(
        self,
        project_id: str,
        chapter_num: int,
        volume_num: int = 1,
        *,
        session: AsyncSession | None = None,
    ) -> ChapterPlan | None:
        if session is None:
            await ensure_database_runtime()
            async with AsyncSessionLocal() as own_session:
                return await self.get_chapter_plan(project_id, chapter_num, volume_num, session=own_session)

        result = await session.execute(
            select(ChapterPlanRecord)
            .options(selectinload(ChapterPlanRecord.scene_beats))
            .where(ChapterPlanRecord.project_id == project_id)
            .where(ChapterPlanRecord.volume_num == volume_num)
            .where(ChapterPlanRecord.chapter_num == chapter_num)
        )
        record = result.scalar_one_or_none()
        if record is None:
            return None
        return self._serialize_chapter_plan(record)

    async def _ensure_book_plan(
        self,
        session: AsyncSession,
        project_id: str,
        volume_num: int,
        user_id: str,
    ) -> BookPlanRecord:
        result = await session.execute(
            select(BookPlanRecord).where(BookPlanRecord.project_id == project_id)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = BookPlanRecord(project_id=project_id, total_volumes=max(1, volume_num), user_id=user_id)
            session.add(record)
            await session.flush()
        else:
            record.total_volumes = max(record.total_volumes, volume_num)
        return record

    async def _ensure_volume_plan(
        self,
        session: AsyncSession,
        book: BookPlanRecord,
        chapter_plan: ChapterPlan,
    ) -> VolumePlanRecord:
        result = await session.execute(
            select(VolumePlanRecord)
            .where(VolumePlanRecord.book_plan_id == book.id)
            .where(VolumePlanRecord.volume_num == chapter_plan.volume_num)
        )
        record = result.scalar_one_or_none()
        if record is None:
            record = VolumePlanRecord(
                book_plan_id=book.id,
                project_id=chapter_plan.project_id,
                volume_num=chapter_plan.volume_num,
                title=f"第{chapter_plan.volume_num}卷",
                arc_summary=chapter_plan.summary[:500],
                user_id=chapter_plan.user_id,
            )
            session.add(record)
            await session.flush()
        else:
            if not record.arc_summary:
                record.arc_summary = chapter_plan.summary[:500]
        return record

    def _serialize_chapter_plan(self, record: ChapterPlanRecord) -> ChapterPlan:
        beats = [
            SceneBeat(
                beat_index=beat.beat_index,
                beat_key=beat.beat_key,
                label=beat.label,
                objective=beat.objective,
                conflict=beat.conflict,
                outcome=beat.outcome,
                tension=beat.tension,
                location=beat.location,
                characters=self._loads_list(beat.characters_json),
                source_node_ids=self._loads_list(beat.source_node_ids_json),
                estimated_words=beat.estimated_words,
                user_id=beat.user_id,
            )
            for beat in sorted(record.scene_beats, key=lambda item: item.beat_index)
        ]
        return ChapterPlan(
            project_id=record.project_id,
            chapter_num=record.chapter_num,
            volume_num=record.volume_num,
            title=record.title,
            summary=record.summary,
            hook=record.hook,
            tension_target=record.tension_target,
            dialogue_goals=self._loads_list(record.dialogue_goals_json),
            legacy_outline_text=record.legacy_outline_text,
            source_run_id=record.source_run_id,
            user_id=record.user_id,
            scene_beats=beats,
        )

    def _loads_list(self, payload: str) -> list[str]:
        try:
            value = json.loads(payload or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []


_story_plan_repository: StoryPlanRepository | None = None


def get_story_plan_repository() -> StoryPlanRepository:
    global _story_plan_repository
    if _story_plan_repository is None:
        _story_plan_repository = StoryPlanRepository()
    return _story_plan_repository