from __future__ import annotations

from datetime import datetime, timezone

import pytest

from narrative_os.infra.models import ApprovalCheckpointRecord, ArtifactRecord, RunRecord, RunStepRecord
from narrative_os.interface.services.trace_service import TraceService


class _Repository:
    async def get_run(self, db, run_id):
        return RunRecord(
            id=run_id,
            project_id="proj-trace",
            run_type="chapter_generation",
            status="failed",
            chapter_num=3,
            session_id=None,
            total_cost_usd=0.12,
            correlation_id="corr-run",
            failure_type="persistence_error",
            failure_message="sqlite commit failed",
            root_cause_step_id="step-2",
            started_at=datetime.now(timezone.utc),
        )

    async def list_steps(self, db, run_id):
        return [
            RunStepRecord(
                id="step-2",
                run_id=run_id,
                step_index=2,
                agent_name="writer",
                status="failed",
                correlation_id="corr-step",
                failure_type="persistence_error",
                failure_message="sqlite commit failed",
                started_at=datetime.now(timezone.utc),
            )
        ]

    async def list_artifacts(self, db, run_id):
        return [
            ArtifactRecord(
                id="artifact-1",
                run_id=run_id,
                step_id="step-2",
                artifact_type="draft",
                agent_name="writer",
                input_summary="input",
                output_content="output",
                correlation_id="corr-step",
                quality_scores="{}",
                token_in=11,
                token_out=22,
                latency_ms=33,
                retry_count=0,
            )
        ]

    async def get_latest_checkpoint(self, db, run_id):
        return ApprovalCheckpointRecord(
            id="checkpoint-1",
            run_id=run_id,
            correlation_id="corr-run",
            reason="need approval",
            context="ctx",
            created_at=datetime.now(timezone.utc),
            decision=None,
        )


@pytest.mark.asyncio
async def test_trace_service_exposes_root_cause_metadata():
    service = TraceService(repository=_Repository())

    run = await service.get_run(db=None, run_id="run-1")

    assert run.correlation_id == "corr-run"
    assert run.root_cause is not None
    assert run.root_cause.type.value == "persistence_error"
    assert run.root_cause.step_id == "step-2"
    assert run.steps[0].failure_message == "sqlite commit failed"
    assert run.steps[0].artifact is not None
    assert run.steps[0].artifact.correlation_id == "corr-step"


@pytest.mark.asyncio
async def test_trace_service_marks_paused_run_as_approval_root_cause():
    class _PausedRepository(_Repository):
        async def get_run(self, db, run_id):
            record = await super().get_run(db, run_id)
            record.status = "paused"
            record.failure_type = "approval_paused"
            record.failure_message = "waiting for operator"
            return record

    service = TraceService(repository=_PausedRepository())
    run = await service.get_run(db=None, run_id="run-2")

    assert run.root_cause is not None
    assert run.root_cause.type.value == "approval_paused"
    assert run.root_cause.message == "need approval"