"""services/project_service.py — 项目管理应用服务。"""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status

from narrative_os.core.project_repository import ProjectRepository, get_project_repository


class ProjectService:
    """项目状态管理服务。"""

    def __init__(self, repository: ProjectRepository | None = None) -> None:
        self._repository = repository or get_project_repository()

    def list_projects(self) -> list[dict[str, Any]]:
        return self._repository.list_projects()

    def initialize_project(
        self,
        project_id: str,
        *,
        title: str = "",
        genre: str = "",
        description: str = "",
    ):
        handle = self._repository.initialize(project_id, title or project_id)
        if genre or description:
            kb = handle.load_kb()
            if genre:
                kb["genre"] = genre
            if description:
                kb["description"] = description
            handle.save_kb(kb)
        return handle

    def load_project_or_404(self, project_id: str):
        handle = self._repository.try_load(project_id)
        if handle is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"项目 '{project_id}' 不存在。", "code": "NOT_FOUND"},
            )
        return handle

    def try_load_project(self, project_id: str):
        return self._repository.try_load(project_id)

    def rollback_project(self, project_id: str, steps: int) -> tuple[Any, int, dict[str, Any]]:
        handle = self.load_project_or_404(project_id)
        state = handle.state
        current = state.current_chapter if state is not None else 0
        target = max(0, current - steps)
        versions = handle.list_versions()
        if not versions:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"项目 '{project_id}' 没有可用的版本快照。",
            )
        available = [version for version in versions if version <= target]
        if not available:
            available = versions
        target = available[-1]
        try:
            snapshot = handle.rollback(chapter=target)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"回滚失败：{exc}",
            )
        return handle, target, snapshot


_project_service: ProjectService | None = None


def get_project_service() -> ProjectService:
    global _project_service
    if _project_service is None:
        _project_service = ProjectService()
    return _project_service

