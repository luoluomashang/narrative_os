"""services/trace_service.py — 执行追踪服务。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.infra.models import (
    ApprovalCheckpointRecord,
    ArtifactRecord,
    RunRecord,
    RunStepRecord,
)
from narrative_os.schemas.traces import (
    ApprovalCheckpoint,
    Artifact,
    ArtifactType,
    Run,
    RunApprovalResponse,
    RunListResponse,
    RunStatus,
    RunStep,
    RunType,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class TraceService:
    async def list_runs(self, db: AsyncSession, project_id: str) -> RunListResponse:
        result = await db.execute(
            select(RunRecord)
            .where(RunRecord.project_id == project_id)
            .order_by(RunRecord.started_at.desc())
        )
        runs = [self._serialize_run_record(record) for record in result.scalars().all()]
        return RunListResponse(items=runs)

    async def get_run(self, db: AsyncSession, run_id: str, include_steps: bool = True) -> Run:
        run = await db.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Run '{run_id}' 不存在。", "code": "NOT_FOUND"},
            )

        steps: list[RunStep] = []
        if include_steps:
            step_result = await db.execute(
                select(RunStepRecord)
                .where(RunStepRecord.run_id == run_id)
                .order_by(RunStepRecord.step_index.asc())
            )
            artifact_result = await db.execute(
                select(ArtifactRecord)
                .where(ArtifactRecord.run_id == run_id)
                .order_by(ArtifactRecord.created_at.asc())
            )
            latest_artifact_by_step: dict[str, ArtifactRecord] = {}
            for artifact in artifact_result.scalars().all():
                latest_artifact_by_step[artifact.step_id] = artifact
            for step in step_result.scalars().all():
                steps.append(self._serialize_step_record(step, latest_artifact_by_step.get(step.id)))

        checkpoint = await self._get_latest_checkpoint(db, run_id)
        return self._serialize_run_record(run, steps=steps, checkpoint=checkpoint)

    async def approve_run(self, db: AsyncSession, run_id: str, decision: str) -> RunApprovalResponse:
        run = await db.get(RunRecord, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Run '{run_id}' 不存在。", "code": "NOT_FOUND"},
            )

        checkpoint_record = await self._get_latest_checkpoint_record(db, run_id)
        if checkpoint_record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Run '{run_id}' 没有待审批检查点。", "code": "NOT_FOUND"},
            )

        checkpoint_record.decision = decision
        checkpoint_record.resolved_at = datetime.now(timezone.utc)
        if decision == "approve":
            run.status = RunStatus.COMPLETED.value
            run.ended_at = datetime.now(timezone.utc)
        elif decision == "retry":
            run.status = RunStatus.RUNNING.value
            run.ended_at = None
        else:
            run.status = RunStatus.FAILED.value
            run.ended_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(run)
        await db.refresh(checkpoint_record)
        return RunApprovalResponse(
            run_id=run.id,
            status=RunStatus(run.status),
            checkpoint=self._serialize_checkpoint_record(checkpoint_record),
        )

    async def _get_latest_checkpoint(self, db: AsyncSession, run_id: str) -> ApprovalCheckpoint | None:
        record = await self._get_latest_checkpoint_record(db, run_id)
        if record is None:
            return None
        return self._serialize_checkpoint_record(record)

    async def _get_latest_checkpoint_record(
        self,
        db: AsyncSession,
        run_id: str,
    ) -> ApprovalCheckpointRecord | None:
        result = await db.execute(
            select(ApprovalCheckpointRecord)
            .where(ApprovalCheckpointRecord.run_id == run_id)
            .order_by(ApprovalCheckpointRecord.created_at.desc())
        )
        return result.scalars().first()

    def _serialize_run_record(
        self,
        record: RunRecord,
        *,
        steps: list[RunStep] | None = None,
        checkpoint: ApprovalCheckpoint | None = None,
    ) -> Run:
        return Run(
            run_id=record.id,
            project_id=record.project_id,
            run_type=RunType(record.run_type),
            status=RunStatus(record.status),
            chapter_num=record.chapter_num,
            session_id=record.session_id,
            steps=steps or [],
            started_at=_iso(record.started_at) or "",
            ended_at=_iso(record.ended_at),
            total_cost_usd=record.total_cost_usd,
            approval_checkpoint=checkpoint,
        )

    def _serialize_step_record(
        self,
        record: RunStepRecord,
        artifact: ArtifactRecord | None,
    ) -> RunStep:
        return RunStep(
            step_id=record.id,
            run_id=record.run_id,
            step_index=record.step_index,
            agent_name=record.agent_name,
            status=RunStatus(record.status),
            artifact=self._serialize_artifact_record(artifact) if artifact is not None else None,
            started_at=_iso(record.started_at) or "",
            ended_at=_iso(record.ended_at),
        )

    def _serialize_artifact_record(self, record: ArtifactRecord) -> Artifact:
        quality_scores = {}
        try:
            quality_scores = json.loads(record.quality_scores or "{}")
        except json.JSONDecodeError:
            quality_scores = {}
        return Artifact(
            artifact_id=record.id,
            run_id=record.run_id,
            step_id=record.step_id,
            artifact_type=ArtifactType(record.artifact_type),
            agent_name=record.agent_name,
            input_summary=record.input_summary,
            output_content=record.output_content,
            quality_scores=quality_scores,
            token_in=record.token_in,
            token_out=record.token_out,
            latency_ms=record.latency_ms,
            retry_count=record.retry_count,
            retry_reason=record.retry_reason,
        )

    def _serialize_checkpoint_record(self, record: ApprovalCheckpointRecord) -> ApprovalCheckpoint:
        return ApprovalCheckpoint(
            checkpoint_id=record.id,
            run_id=record.run_id,
            reason=record.reason,
            context=record.context,
            created_at=_iso(record.created_at) or "",
            resolved_at=_iso(record.resolved_at),
            decision=record.decision,
        )


_trace_service: TraceService | None = None


def get_trace_service() -> TraceService:
    global _trace_service
    if _trace_service is None:
        _trace_service = TraceService()
    return _trace_service
