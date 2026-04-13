"""core/canon_repository.py — Canon 变更集统一入口。"""

from __future__ import annotations

from typing import Any


class CanonRepository:
    def _get_commit(self, project_id: str):
        from narrative_os.core.evolution import get_canon_commit

        return get_canon_commit(project_id)

    def list_changesets(self, project_id: str) -> list[Any]:
        return self._get_commit(project_id).list_changesets(project_id)

    def get_changeset(self, project_id: str, changeset_id: str) -> Any | None:
        return self._get_commit(project_id).get_changeset(changeset_id)

    def pending_changes_count(self, project_id: str) -> int:
        from narrative_os.core.evolution import ChangeTag

        return sum(
            1
            for changeset in self.list_changesets(project_id)
            for change in changeset.changes
            if change.tag == ChangeTag.CANON_PENDING
        )

    def approve_and_commit(self, project_id: str, changeset_id: str) -> tuple[int, list[Any]]:
        commit = self._get_commit(project_id)
        approved_count = commit.approve_all(changeset_id)
        committed = commit.commit_to_canon(changeset_id)
        return approved_count, committed

    def reject_all(self, project_id: str, changeset_id: str) -> int:
        commit = self._get_commit(project_id)
        changeset = commit.get_changeset(changeset_id)
        if changeset is None:
            return 0
        rejected_count = 0
        for change in changeset.changes:
            commit.reject_change(change.change_id)
            rejected_count += 1
        return rejected_count


_canon_repository: CanonRepository | None = None


def get_canon_repository() -> CanonRepository:
    global _canon_repository
    if _canon_repository is None:
        _canon_repository = CanonRepository()
    return _canon_repository