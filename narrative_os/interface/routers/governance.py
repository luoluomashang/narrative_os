"""routers/governance.py — ChangeSet / Canon Commit 路由模块（Phase 1 + Phase 4）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from narrative_os.interface.services.governance_service import GovernanceService, get_governance_service

from narrative_os.schemas.governance import (
    ChangeSetApproveResponse,
    ChangeSetDetail,
    ChangeSetListItem,
    ChangeSetRejectResponse,
)

router = APIRouter(tags=["governance"])


def _svc() -> GovernanceService:
    return get_governance_service()


@router.get("/projects/{project_id}/changesets", response_model=list[ChangeSetListItem], summary="获取待审变更集列表")
async def list_changesets(
    project_id: str,
    svc: GovernanceService = Depends(_svc),
) -> list[ChangeSetListItem]:
    return [ChangeSetListItem.model_validate(item) for item in svc.list_changesets(project_id)]


@router.get("/projects/{project_id}/changesets/{changeset_id}", response_model=ChangeSetDetail, summary="查看变更集详情")
async def get_changeset(
    project_id: str,
    changeset_id: str,
    svc: GovernanceService = Depends(_svc),
) -> ChangeSetDetail:
    return ChangeSetDetail.model_validate(svc.get_changeset(project_id, changeset_id))


@router.post("/projects/{project_id}/changesets/{changeset_id}/approve", response_model=ChangeSetApproveResponse, summary="批量批准并提交正史")
async def approve_changeset(
    project_id: str,
    changeset_id: str,
    svc: GovernanceService = Depends(_svc),
) -> ChangeSetApproveResponse:
    return ChangeSetApproveResponse.model_validate(svc.approve_changeset(project_id, changeset_id))


@router.post("/projects/{project_id}/changesets/{changeset_id}/reject", response_model=ChangeSetRejectResponse, summary="驳回整个变更集")
async def reject_changeset(
    project_id: str,
    changeset_id: str,
    svc: GovernanceService = Depends(_svc),
) -> ChangeSetRejectResponse:
    return ChangeSetRejectResponse.model_validate(svc.reject_changeset(project_id, changeset_id))
