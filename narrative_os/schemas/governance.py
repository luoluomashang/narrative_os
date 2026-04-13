"""schemas/governance.py — Canon 变更集相关模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from narrative_os.schemas.trpg import CanonChapterPreview, DraftChapterPreview, SessionOnlyPreview


class ChangeSetListItem(BaseModel):
    changeset_id: str
    source: str
    session_id: str | None = None
    commit_mode: str
    changes_count: int = 0
    pending_count: int = 0
    confirmed_count: int = 0
    project_id: str | None = None
    status: str | None = None
    created_at: str


class ChangeSetDetail(BaseModel):
    changeset_id: str
    project_id: str
    status: str
    created_at: str
    changes: list[dict[str, Any]] = []
    preview_session_only: SessionOnlyPreview = SessionOnlyPreview()
    preview_draft_chapter: DraftChapterPreview = DraftChapterPreview()
    preview_canon_chapter: CanonChapterPreview = CanonChapterPreview()


class ChangeSetApproveResponse(BaseModel):
    changeset_id: str
    approved_count: int
    committed_count: int


class ChangeSetRejectResponse(BaseModel):
    changeset_id: str
    rejected_count: int
