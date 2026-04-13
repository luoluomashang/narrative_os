"""core/benchmark_repository.py — Benchmark 持久化入口。"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Iterable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.infra.models import (
    ArtifactRecord,
    AuthorSkillRecord,
    BenchmarkProfileRecord,
    BenchmarkScoreRecord,
    BenchmarkSnippetRecord,
    BenchmarkSourceRecord,
    RunRecord,
    RunStepRecord,
    SettingRecord,
)


class BenchmarkRepository:
    async def create_sources(
        self,
        db: AsyncSession,
        records: list[BenchmarkSourceRecord],
    ) -> list[BenchmarkSourceRecord]:
        db.add_all(records)
        await db.flush()
        return records

    async def get_sources_by_ids(
        self,
        db: AsyncSession,
        project_id: str,
        source_ids: Iterable[str],
    ) -> list[BenchmarkSourceRecord]:
        source_ids = list(source_ids)
        if not source_ids:
            return []
        result = await db.execute(
            select(BenchmarkSourceRecord)
            .where(BenchmarkSourceRecord.project_id == project_id)
            .where(BenchmarkSourceRecord.id.in_(source_ids))
            .order_by(BenchmarkSourceRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def create_run_with_profile(
        self,
        db: AsyncSession,
        *,
        run: RunRecord,
        profile: BenchmarkProfileRecord,
        snippets: list[BenchmarkSnippetRecord] | None = None,
        author_skill: AuthorSkillRecord | None = None,
        step_records: list[RunStepRecord],
        artifact_records: list[ArtifactRecord],
    ) -> None:
        db.add(run)
        db.add(profile)
        db.add_all(step_records)
        db.add_all(artifact_records)
        if snippets:
            db.add_all(snippets)
        if author_skill is not None:
            db.add(author_skill)
        await db.commit()

    async def get_run(self, db: AsyncSession, run_id: str) -> RunRecord | None:
        return await db.get(RunRecord, run_id)

    async def get_profile_by_run(
        self,
        db: AsyncSession,
        run_id: str,
    ) -> BenchmarkProfileRecord | None:
        result = await db.execute(
            select(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.run_id == run_id)
            .order_by(BenchmarkProfileRecord.created_at.desc())
        )
        return result.scalars().first()

    async def get_author_skill_by_run(
        self,
        db: AsyncSession,
        run_id: str,
    ) -> AuthorSkillRecord | None:
        result = await db.execute(
            select(AuthorSkillRecord)
            .where(AuthorSkillRecord.run_id == run_id)
            .order_by(AuthorSkillRecord.created_at.desc())
        )
        return result.scalars().first()

    async def get_author_skill(self, db: AsyncSession, skill_id: str) -> AuthorSkillRecord | None:
        return await db.get(AuthorSkillRecord, skill_id)

    async def list_author_skills(
        self,
        db: AsyncSession,
        *,
        author_name: str | None = None,
        limit: int = 50,
    ) -> list[AuthorSkillRecord]:
        stmt = select(AuthorSkillRecord).order_by(AuthorSkillRecord.created_at.desc()).limit(limit)
        if author_name:
            stmt = stmt.where(AuthorSkillRecord.author_name == author_name)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def get_profile(
        self,
        db: AsyncSession,
        project_id: str,
        profile_id: str,
    ) -> BenchmarkProfileRecord | None:
        result = await db.execute(
            select(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.project_id == project_id)
            .where(BenchmarkProfileRecord.id == profile_id)
        )
        return result.scalars().first()

    async def get_active_profile(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> BenchmarkProfileRecord | None:
        result = await db.execute(
            select(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.project_id == project_id)
            .where(BenchmarkProfileRecord.profile_type == "project_benchmark")
            .where(BenchmarkProfileRecord.status == "active")
            .order_by(BenchmarkProfileRecord.activated_at.desc(), BenchmarkProfileRecord.created_at.desc())
        )
        return result.scalars().first()

    async def get_latest_profile(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> BenchmarkProfileRecord | None:
        result = await db.execute(
            select(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.project_id == project_id)
            .where(BenchmarkProfileRecord.profile_type == "project_benchmark")
            .order_by(BenchmarkProfileRecord.created_at.desc())
        )
        return result.scalars().first()

    async def list_snippets_by_profile(
        self,
        db: AsyncSession,
        project_id: str,
        profile_id: str,
        *,
        scene_type: str | None = None,
        limit: int = 60,
    ) -> list[BenchmarkSnippetRecord]:
        stmt = (
            select(BenchmarkSnippetRecord)
            .where(BenchmarkSnippetRecord.project_id == project_id)
            .where(BenchmarkSnippetRecord.profile_id == profile_id)
            .order_by(BenchmarkSnippetRecord.anchor_score.desc(), BenchmarkSnippetRecord.created_at.asc())
            .limit(limit)
        )
        if scene_type:
            stmt = stmt.where(BenchmarkSnippetRecord.scene_type == scene_type)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_snippets_by_profile(
        self,
        db: AsyncSession,
        profile_id: str,
    ) -> int:
        result = await db.execute(
            select(BenchmarkSnippetRecord.id).where(BenchmarkSnippetRecord.profile_id == profile_id)
        )
        return len(result.scalars().all())

    async def activate_profile(
        self,
        db: AsyncSession,
        project_id: str,
        profile_id: str,
        *,
        activated_at: datetime,
    ) -> BenchmarkProfileRecord | None:
        await db.execute(
            update(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.project_id == project_id)
            .where(BenchmarkProfileRecord.profile_type == "project_benchmark")
            .values(status="draft", activated_at=None)
        )
        await db.execute(
            update(BenchmarkProfileRecord)
            .where(BenchmarkProfileRecord.project_id == project_id)
            .where(BenchmarkProfileRecord.id == profile_id)
            .values(status="active", activated_at=activated_at)
        )
        await db.commit()
        return await self.get_profile(db, project_id, profile_id)

    async def get_step_by_run_and_agent(
        self,
        db: AsyncSession,
        run_id: str,
        agent_name: str,
    ) -> RunStepRecord | None:
        result = await db.execute(
            select(RunStepRecord)
            .where(RunStepRecord.run_id == run_id)
            .where(RunStepRecord.agent_name == agent_name)
            .order_by(RunStepRecord.step_index.desc())
        )
        return result.scalars().first()

    async def get_last_step(self, db: AsyncSession, run_id: str) -> RunStepRecord | None:
        result = await db.execute(
            select(RunStepRecord)
            .where(RunStepRecord.run_id == run_id)
            .order_by(RunStepRecord.step_index.desc())
        )
        return result.scalars().first()

    async def create_score(
        self,
        db: AsyncSession,
        score: BenchmarkScoreRecord,
        artifact: ArtifactRecord | None = None,
    ) -> None:
        db.add(score)
        if artifact is not None:
            db.add(artifact)
        await db.commit()

    async def list_scores_by_project(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> list[BenchmarkScoreRecord]:
        result = await db.execute(
            select(BenchmarkScoreRecord)
            .where(BenchmarkScoreRecord.project_id == project_id)
            .order_by(BenchmarkScoreRecord.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_project_setting(
        self,
        db: AsyncSession,
        project_id: str,
        key: str,
    ) -> object | None:
        record = await db.get(SettingRecord, f"{project_id}__{key}")
        if record is None:
            return None
        try:
            return json.loads(record.value_json)
        except json.JSONDecodeError:
            return None

    async def upsert_project_setting(
        self,
        db: AsyncSession,
        project_id: str,
        key: str,
        value: object,
    ) -> None:
        compound_key = f"{project_id}__{key}"
        record = await db.get(SettingRecord, compound_key)
        payload = json.dumps(value, ensure_ascii=False)
        if record is None:
            db.add(
                SettingRecord(
                    key=compound_key,
                    value_json=payload,
                    scope="project",
                    project_id=project_id,
                )
            )
        else:
            record.value_json = payload
        await db.commit()


_benchmark_repository: BenchmarkRepository | None = None


def get_benchmark_repository() -> BenchmarkRepository:
    global _benchmark_repository
    if _benchmark_repository is None:
        _benchmark_repository = BenchmarkRepository()
    return _benchmark_repository