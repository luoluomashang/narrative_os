"""core/project_repository.py — 项目状态/文件持久化统一入口。"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from narrative_os.infra.config import settings

from narrative_os.core.state import StateManager as _ORIGINAL_STATE_MANAGER


def _get_state_manager_class():
    from narrative_os.core.state import StateManager as core_state_manager

    api_mod = sys.modules.get("narrative_os.interface.api")
    api_state_manager = getattr(api_mod, "StateManager", None) if api_mod is not None else None

    if api_state_manager is not None and api_state_manager is not _ORIGINAL_STATE_MANAGER:
        return api_state_manager
    if core_state_manager is not _ORIGINAL_STATE_MANAGER:
        return core_state_manager

    return core_state_manager


@dataclass
class ProjectHandle:
    manager: Any

    @property
    def state(self):
        return self.manager.state

    @property
    def dir_path(self) -> str:
        return str(self.manager._dir)

    def initialize(self, project_name: str = "", force: bool = False):
        return self.manager.initialize(project_name=project_name, force=force)

    def load_state(self):
        return self.manager.load_state()

    def save_state(self) -> None:
        self.manager.save_state()

    def load_kb(self) -> dict[str, Any]:
        return self.manager.load_kb()

    def save_kb(self, kb: dict[str, Any]) -> None:
        self.manager.save_kb(kb)

    def list_versions(self) -> list[int]:
        return self.manager.list_versions()

    def rollback(self, chapter: int) -> dict[str, Any]:
        return self.manager.rollback(chapter=chapter)

    def get_last_hook(self, chapter: int | None = None) -> str:
        return self.manager.get_last_hook(chapter)

    def save_last_hook(self, chapter: int, hook_text: str) -> None:
        self.manager.save_last_hook(chapter, hook_text)

    def save_chapter_text(self, chapter: int, text: str):
        return self.manager.save_chapter_text(chapter, text)

    def load_chapter_text(self, chapter: int) -> str | None:
        return self.manager.load_chapter_text(chapter)

    def list_chapter_files(self) -> list[int]:
        return self.manager.list_chapter_files()

    def commit_chapter(
        self,
        chapter: int,
        *,
        plot_graph_dict: dict[str, Any] | None = None,
        characters_dict: dict[str, Any] | None = None,
        world_dict: dict[str, Any] | None = None,
        chapter_meta: Any | None = None,
    ):
        return self.manager.commit_chapter(
            chapter,
            plot_graph_dict=plot_graph_dict,
            characters_dict=characters_dict,
            world_dict=world_dict,
            chapter_meta=chapter_meta,
        )


class ProjectRepository:
    def __init__(self) -> None:
        self._state_root = Path(settings.state_dir)

    def list_projects(self) -> list[dict[str, Any]]:
        if not self._state_root.exists():
            return []
        items: list[dict[str, Any]] = []
        for project_dir in sorted(self._state_root.iterdir()):
            if not project_dir.is_dir():
                continue
            state_file = project_dir / "state.json"
            if not state_file.exists():
                continue
            title = project_dir.name
            chapter_count = 0
            last_modified = ""
            try:
                payload = json.loads(state_file.read_text(encoding="utf-8"))
                title = payload.get("project_name", title) or title
                chapter_count = payload.get("current_chapter", 0) or 0
                last_modified = payload.get("updated_at", "") or ""
            except Exception:
                pass
            items.append(
                {
                    "project_id": project_dir.name,
                    "title": title,
                    "chapter_count": chapter_count,
                    "total_chapters": chapter_count,
                    "last_modified": last_modified,
                }
            )
        return items

    def try_load(self, project_id: str) -> ProjectHandle | None:
        manager = _get_state_manager_class()(project_id=project_id, base_dir=settings.state_dir)
        try:
            state = manager.load_state()
            if state is not None:
                manager.state = state
            return ProjectHandle(manager)
        except (FileNotFoundError, Exception):
            return None

    def load(self, project_id: str) -> ProjectHandle:
        handle = self.try_load(project_id)
        if handle is None:
            raise FileNotFoundError(project_id)
        return handle

    def initialize(self, project_id: str, project_name: str = "") -> ProjectHandle:
        manager = _get_state_manager_class()(project_id=project_id, base_dir=settings.state_dir)
        manager.initialize(project_name=project_name or project_id)
        return ProjectHandle(manager)

    def load_or_initialize(self, project_id: str, project_name: str = "") -> ProjectHandle:
        return self.try_load(project_id) or self.initialize(project_id, project_name=project_name)


_project_repository: ProjectRepository | None = None


def get_project_repository() -> ProjectRepository:
    global _project_repository
    if _project_repository is None:
        _project_repository = ProjectRepository()
    return _project_repository