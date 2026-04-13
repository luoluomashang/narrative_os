"""services/governance_service.py — 治理/变更集应用服务。"""
from __future__ import annotations

from fastapi import HTTPException

from narrative_os.core.canon_repository import CanonRepository, get_canon_repository

class GovernanceService:
    def __init__(self, repository: CanonRepository | None = None) -> None:
        self._repository = repository or get_canon_repository()

    def _changeset_status(self, changeset) -> str:
        if any(change.tag.value == "canon_pending" for change in changeset.changes):
            return "canon_pending"
        if any(change.tag.value == "draft" for change in changeset.changes):
            return "draft"
        if any(change.tag.value == "canon_confirmed" for change in changeset.changes):
            return "canon_confirmed"
        return "runtime_only"

    def list_changesets(self, project_id: str) -> list[dict]:
        changesets = self._repository.list_changesets(project_id)
        return [
            {
                "changeset_id": cs.changeset_id,
                "source": cs.source.value,
                "session_id": cs.session_id,
                "commit_mode": cs.commit_mode.value,
                "changes_count": len(cs.changes),
                "pending_count": len(cs.pending_changes()),
                "confirmed_count": len(cs.confirmed_changes()),
                "status": self._changeset_status(cs),
                "created_at": cs.created_at,
            }
            for cs in changesets
        ]

    def get_changeset(self, project_id: str, changeset_id: str) -> dict:
        changeset = self._repository.get_changeset(project_id, changeset_id)
        if changeset is None:
            raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
        return {
            **changeset.model_dump(),
            "status": self._changeset_status(changeset),
            **self._build_changeset_previews(changeset),
        }

    def _build_changeset_previews(self, changeset) -> dict[str, dict]:
        pending_changes = changeset.pending_changes()
        summary = (
            f"本次 {changeset.source.value} 互动以 {changeset.commit_mode.value} 方式归档，"
            f"共记录 {len(changeset.changes)} 项变更。"
        )
        character_changes: list[dict] = []
        seen_names: set[str] = set()
        for change in changeset.changes:
            payload = change.after_value or {}
            name = payload.get("name") or payload.get("character_name")
            if not name or name in seen_names:
                continue
            seen_names.add(name)
            description = change.description or f"{name} 状态更新"
            character_changes.append(
                {
                    "name": str(name),
                    "change": description,
                    "actions_count": int(payload.get("actions_count") or 0),
                    "final_pressure": payload.get("final_pressure"),
                }
            )

        preview_pending = [
            {
                "change_type": change.change_type,
                "description": change.description,
                "tag": change.tag.value,
                "chapter": change.chapter,
                "before_snapshot": change.before_snapshot,
                "after_value": change.after_value,
            }
            for change in pending_changes
        ]
        draft_content = changeset.draft_content or ""
        return {
            "preview_session_only": {
                "summary": summary,
                "memory_anchors": [
                    {
                        "label": summary[:120],
                        "source": "changeset",
                        "importance": 0.8,
                    }
                ],
                "character_changes": character_changes,
                "projected_changeset_status": self._changeset_status(changeset),
            },
            "preview_draft_chapter": {
                "chapter_text": draft_content,
                "excerpt": draft_content[:180],
                "word_count": len(draft_content),
                "quality_estimate": self._estimate_draft_quality(draft_content),
            },
            "preview_canon_chapter": {
                "draft_content": draft_content,
                "pending_changes": preview_pending,
                "approval_required_fields": [
                    "章节正文",
                    "待审世界变更",
                    "正史提交确认",
                ],
                "requires_confirmation": changeset.commit_mode.value == "canon_chapter",
                "projected_changeset_status": self._changeset_status(changeset),
            },
        }

    def _estimate_draft_quality(self, draft_content: str) -> str:
        word_count = len(draft_content)
        if word_count >= 1200:
            return "完整度高，可直接进入审批"
        if word_count >= 500:
            return "主体清晰，建议补充细节"
        if word_count > 0:
            return "内容较短，建议继续扩写"
        return "暂无正文内容"

    def approve_changeset(self, project_id: str, changeset_id: str) -> dict[str, int | str]:
        if self._repository.get_changeset(project_id, changeset_id) is None:
            raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
        approved_count, committed = self._repository.approve_and_commit(project_id, changeset_id)
        return {
            "changeset_id": changeset_id,
            "approved_count": approved_count,
            "committed_count": len(committed),
        }

    def reject_changeset(self, project_id: str, changeset_id: str) -> dict[str, int | str]:
        if self._repository.get_changeset(project_id, changeset_id) is None:
            raise HTTPException(status_code=404, detail=f"变更集 '{changeset_id}' 不存在")
        rejected_count = self._repository.reject_all(project_id, changeset_id)
        return {"changeset_id": changeset_id, "rejected_count": rejected_count}


_governance_service: GovernanceService | None = None


def get_governance_service() -> GovernanceService:
    global _governance_service
    if _governance_service is None:
        _governance_service = GovernanceService()
    return _governance_service
