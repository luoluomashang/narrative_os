"""routers/governance.py — ChangeSet / Canon Commit 路由模块（Phase 1 + Phase 4）。"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from narrative_os.schemas.governance import (
    ChangeSetApproveResponse,
    ChangeSetDetail,
    ChangeSetListItem,
    ChangeSetRejectResponse,
)

router = APIRouter(tags=["governance"])


def _changeset_status(cs) -> str:
    if any(change.tag.value == "canon_pending" for change in cs.changes):
        return "canon_pending"
    if any(change.tag.value == "draft" for change in cs.changes):
        return "draft"
    if any(change.tag.value == "canon_confirmed" for change in cs.changes):
        return "canon_confirmed"
    return "runtime_only"


@router.get("/projects/{project_id}/changesets", response_model=list[ChangeSetListItem], summary="获取待审变更集列表")
async def list_changesets(project_id: str) -> list[ChangeSetListItem]:
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    changesets = cc.list_changesets(project_id)
    return [
        {
            "changeset_id": cs.changeset_id,
            "source": cs.source.value,
            "session_id": cs.session_id,
            "commit_mode": cs.commit_mode.value,
            "changes_count": len(cs.changes),
            "pending_count": len(cs.pending_changes()),
            "confirmed_count": len(cs.confirmed_changes()),
            "status": _changeset_status(cs),
            "created_at": cs.created_at,
        }
        for cs in changesets
    ]


@router.get("/projects/{project_id}/changesets/{changeset_id}", response_model=ChangeSetDetail, summary="查看变更集详情")
async def get_changeset(project_id: str, changeset_id: str) -> ChangeSetDetail:
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    cs = cc.get_changeset(changeset_id)
    if cs is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    return {
        **cs.model_dump(),
        "status": _changeset_status(cs),
    }


@router.post("/projects/{project_id}/changesets/{changeset_id}/approve", response_model=ChangeSetApproveResponse, summary="批量批准并提交正史")
async def approve_changeset(project_id: str, changeset_id: str) -> ChangeSetApproveResponse:
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    if cc.get_changeset(changeset_id) is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    approved_count = cc.approve_all(changeset_id)
    committed = cc.commit_to_canon(changeset_id)
    return ChangeSetApproveResponse(
        changeset_id=changeset_id,
        approved_count=approved_count,
        committed_count=len(committed),
    )


@router.post("/projects/{project_id}/changesets/{changeset_id}/reject", response_model=ChangeSetRejectResponse, summary="驳回整个变更集")
async def reject_changeset(project_id: str, changeset_id: str) -> ChangeSetRejectResponse:
    from narrative_os.core.evolution import get_canon_commit
    cc = get_canon_commit(project_id)
    cs = cc.get_changeset(changeset_id)
    if cs is None:
        raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
    rejected_count = 0
    for change in cs.changes:
        cc.reject_change(change.change_id)
        rejected_count += 1
    return ChangeSetRejectResponse(changeset_id=changeset_id, rejected_count=rejected_count)
