"""services/project_service.py — 项目管理应用服务。"""
from __future__ import annotations

import sys

from fastapi import HTTPException, status

from narrative_os.core.state import StateManager as _CoreStateManager


def _get_state_manager_class():
    """返回 StateManager 类，优先从 api 模块获取以支持测试 mock 注入。"""
    api_mod = sys.modules.get("narrative_os.interface.api")
    if api_mod is not None and hasattr(api_mod, "StateManager"):
        return api_mod.StateManager
    return _CoreStateManager


class ProjectService:
    """项目状态管理服务。"""

    def load_project_or_404(self, project_id: str):
        SM = _get_state_manager_class()
        mgr = SM(project_id=project_id, base_dir=".narrative_state")
        try:
            mgr.load_state()
        except FileNotFoundError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"项目 '{project_id}' 不存在。", "code": "NOT_FOUND"},
            )
        return mgr

    def try_load_project(self, project_id: str):
        SM = _get_state_manager_class()
        mgr = SM(project_id=project_id, base_dir=".narrative_state")
        try:
            mgr.load_state()
            return mgr
        except (FileNotFoundError, Exception):
            return None


_project_service: ProjectService | None = None


def get_project_service() -> ProjectService:
    global _project_service
    if _project_service is None:
        _project_service = ProjectService()
    return _project_service

