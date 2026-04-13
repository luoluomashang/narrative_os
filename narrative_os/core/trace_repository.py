"""core/trace_repository.py — Run/Step/Artifact/Approval 持久化入口。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.infra.models import (
    ApprovalCheckpointRecord,
    ArtifactRecord,
    RunRecord,
    RunStepRecord,
)


class TraceRepository:
    async def list_runs(self, db: AsyncSession, project_id: str) -> list[RunRecord]:
        result = await db.execute(
            select(RunRecord)
            .where(RunRecord.project_id == project_id)
            .order_by(RunRecord.started_at.desc())
        )
        return list(result.scalars().all())

    async def get_run(self, db: AsyncSession, run_id: str) -> RunRecord | None:
        return await db.get(RunRecord, run_id)

    async def annotate_run(
        self,
        db: AsyncSession,
        run_id: str,
        *,
        failure_type: str | None = None,
        failure_message: str | None = None,
        root_cause_step_id: str | None = None,
    ) -> RunRecord | None:
        run = await db.get(RunRecord, run_id)
        if run is None:
            return None
        if failure_type is not None:
            run.failure_type = failure_type
        if failure_message is not None:
            run.failure_message = failure_message
        if root_cause_step_id is not None:
            run.root_cause_step_id = root_cause_step_id
        await db.commit()
        await db.refresh(run)
        return run

    async def list_steps(self, db: AsyncSession, run_id: str) -> list[RunStepRecord]:
        result = await db.execute(
            select(RunStepRecord)
            .where(RunStepRecord.run_id == run_id)
            .order_by(RunStepRecord.step_index.asc())
        )
        return list(result.scalars().all())

    async def list_artifacts(self, db: AsyncSession, run_id: str) -> list[ArtifactRecord]:
        result = await db.execute(
            select(ArtifactRecord)
            .where(ArtifactRecord.run_id == run_id)
            .order_by(ArtifactRecord.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_latest_checkpoint(self, db: AsyncSession, run_id: str) -> ApprovalCheckpointRecord | None:
        result = await db.execute(
            select(ApprovalCheckpointRecord)
            .where(ApprovalCheckpointRecord.run_id == run_id)
            .order_by(ApprovalCheckpointRecord.created_at.desc())
        )
        return result.scalars().first()

    async def apply_approval(
        self,
        db: AsyncSession,
        run: RunRecord,
        checkpoint: ApprovalCheckpointRecord,
        decision: str,
    ) -> tuple[RunRecord, ApprovalCheckpointRecord]:
        checkpoint.decision = decision
        checkpoint.resolved_at = datetime.now(timezone.utc)
        if decision == "approve":
            run.status = "completed"
            run.ended_at = datetime.now(timezone.utc)
            run.failure_type = None
            run.failure_message = None
            run.root_cause_step_id = None
        elif decision == "retry":
            run.status = "running"
            run.ended_at = None
            run.failure_type = None
            run.failure_message = None
            run.root_cause_step_id = None
        else:
            run.status = "failed"
            run.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
        await db.refresh(checkpoint)
        return run, checkpoint


_trace_repository: TraceRepository | None = None


def get_trace_repository() -> TraceRepository:
    global _trace_repository
    if _trace_repository is None:
        _trace_repository = TraceRepository()
    return _trace_repository