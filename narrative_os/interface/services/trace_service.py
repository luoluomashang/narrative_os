"""services/trace_service.py — 执行追踪服务。"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.core.trace_repository import TraceRepository, get_trace_repository
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
    FailureRootCauseType,
    Run,
    RunApprovalResponse,
    RunListResponse,
    RunRootCause,
    RunStatus,
    RunStep,
    RunType,
)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class TraceService:
    def __init__(self, repository: TraceRepository | None = None) -> None:
        self._repository = repository or get_trace_repository()

    async def list_runs(self, db: AsyncSession, project_id: str) -> RunListResponse:
        records = await self._repository.list_runs(db, project_id)
        runs = [self._serialize_run_record(record) for record in records]
        return RunListResponse(items=runs)

    async def get_run(self, db: AsyncSession, run_id: str, include_steps: bool = True) -> Run:
        run = await self._repository.get_run(db, run_id)
        if run is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Run '{run_id}' 不存在。", "code": "NOT_FOUND"},
            )

        steps: list[RunStep] = []
        if include_steps:
            step_records = await self._repository.list_steps(db, run_id)
            artifact_records = await self._repository.list_artifacts(db, run_id)
            latest_artifact_by_step: dict[str, ArtifactRecord] = {}
            for artifact in artifact_records:
                latest_artifact_by_step[artifact.step_id] = artifact
            for step in step_records:
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

        run, checkpoint_record = await self._repository.apply_approval(db, run, checkpoint_record, decision)
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
        return await self._repository.get_latest_checkpoint(db, run_id)

    def _serialize_run_record(
        self,
        record: RunRecord,
        *,
        steps: list[RunStep] | None = None,
        checkpoint: ApprovalCheckpoint | None = None,
    ) -> Run:
        resolved_steps = steps or []
        return Run(
            run_id=record.id,
            project_id=record.project_id,
            run_type=RunType(record.run_type),
            status=RunStatus(record.status),
            correlation_id=record.correlation_id or "",
            root_cause=self._serialize_root_cause(record, resolved_steps, checkpoint),
            chapter_num=record.chapter_num,
            session_id=record.session_id,
            steps=resolved_steps,
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
            correlation_id=record.correlation_id or "",
            failure_type=self._parse_failure_type(record.failure_type),
            failure_message=record.failure_message,
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
            correlation_id=record.correlation_id or "",
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
            correlation_id=record.correlation_id or "",
            reason=record.reason,
            context=record.context,
            created_at=_iso(record.created_at) or "",
            resolved_at=_iso(record.resolved_at),
            decision=record.decision,
        )

    def _serialize_root_cause(
        self,
        record: RunRecord,
        steps: list[RunStep],
        checkpoint: ApprovalCheckpoint | None,
    ) -> RunRootCause | None:
        if checkpoint is not None and record.status == RunStatus.PAUSED.value:
            return RunRootCause(
                type=FailureRootCauseType.APPROVAL_PAUSED,
                message=checkpoint.reason,
                step_id=record.root_cause_step_id,
                correlation_id=record.correlation_id or checkpoint.correlation_id,
            )

        failure_type = self._parse_failure_type(record.failure_type)
        if failure_type is not None:
            return RunRootCause(
                type=failure_type,
                message=record.failure_message or "",
                step_id=record.root_cause_step_id,
                correlation_id=record.correlation_id or "",
            )

        failed_step = next(
            (
                step
                for step in steps
                if step.failure_type is not None or step.status == RunStatus.FAILED
            ),
            None,
        )
        if failed_step is None:
            return None

        return RunRootCause(
            type=failed_step.failure_type or FailureRootCauseType.UNKNOWN,
            message=failed_step.failure_message or "",
            step_id=failed_step.step_id,
            correlation_id=failed_step.correlation_id or record.correlation_id or "",
        )

    def _parse_failure_type(self, value: str | None) -> FailureRootCauseType | None:
        if not value:
            return None
        try:
            return FailureRootCauseType(value)
        except ValueError:
            return FailureRootCauseType.UNKNOWN


_trace_service: TraceService | None = None


def get_trace_service() -> TraceService:
    global _trace_service
    if _trace_service is None:
        _trace_service = TraceService()
    return _trace_service
