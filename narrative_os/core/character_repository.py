"""
core/character_repository.py — Phase 2: 统一角色数据入口

职责:
  - 统一读取/写入角色数据（从 KB JSON 存储）
  - `CharacterState.memory[]` 与 `MemorySystem` 记忆合并
    （以 MemorySystem 为权威，CharacterState.memory 降级为缓存）
  - 对外接口：get_character / save_character / list_characters
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from narrative_os.core.character import CharacterState
from narrative_os.infra.config import settings

if TYPE_CHECKING:
    pass


class CharacterRepository:
    """统一角色数据存取层。"""

    def __init__(self) -> None:
        self._state_root = Path(settings.state_dir)

    # ---------------------------------------------------------------- #
    # Internal helpers                                                  #
    # ---------------------------------------------------------------- #

    def _kb_path(self, project_id: str) -> Path:
        return self._state_root / project_id / "knowledge_base.json"

    def _load_kb(self, project_id: str) -> dict:
        path = self._kb_path(project_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_kb(self, project_id: str, kb: dict) -> None:
        path = self._kb_path(project_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- #
    # Public interface                                                  #
    # ---------------------------------------------------------------- #

    def list_characters(self, project_id: str) -> list[CharacterState]:
        """返回项目中所有角色的 CharacterState 列表。"""
        kb = self._load_kb(project_id)
        raw_list = kb.get("characters", [])
        if not isinstance(raw_list, list):
            return []
        result: list[CharacterState] = []
        for raw in raw_list:
            if not isinstance(raw, dict):
                continue
            try:
                result.append(CharacterState.model_validate(raw))
            except Exception:
                pass
        return result

    def get_character(self, project_id: str, name: str) -> CharacterState | None:
        """按名称查询角色，不存在时返回 None。支持从 MemorySystem 同步近期记忆缓存。"""
        kb = self._load_kb(project_id)
        raw_list = kb.get("characters", [])
        if not isinstance(raw_list, list):
            return None
        raw = next(
            (c for c in raw_list if isinstance(c, dict) and c.get("name") == name),
            None,
        )
        if raw is None:
            return None
        try:
            char = CharacterState.model_validate(raw)
        except Exception:
            return None

        # 从 MemorySystem 同步近期记忆（以 MemorySystem 为权威）
        char = self._sync_memory_from_system(project_id, char)
        return char

    def save_character(self, project_id: str, char: CharacterState) -> None:
        """保存（新增或更新）角色到 KB。"""
        kb = self._load_kb(project_id)
        raw_list = kb.get("characters", [])
        if not isinstance(raw_list, list):
            raw_list = []

        char_dict = char.model_dump()
        for i, c in enumerate(raw_list):
            if isinstance(c, dict) and c.get("name") == char.name:
                raw_list[i] = char_dict
                kb["characters"] = raw_list
                self._save_kb(project_id, kb)
                return

        # 不存在则追加
        raw_list.append(char_dict)
        kb["characters"] = raw_list
        self._save_kb(project_id, kb)

    # ---------------------------------------------------------------- #
    # Memory sync                                                       #
    # ---------------------------------------------------------------- #

    def _sync_memory_from_system(
        self, project_id: str, char: CharacterState
    ) -> CharacterState:
        """
        从 MemorySystem 获取与该角色相关的近期记忆，更新 char.memory 缓存。
        MemorySystem 为权威源；CharacterState.memory 仅作为查询缓存。
        如果 MemorySystem 不可用则静默降级到现有缓存。
        """
        try:
            from narrative_os.core.memory import MemorySystem

            mem = MemorySystem(project_id=project_id)
            results = mem.retrieve(
                query=f"角色 {char.name}",
                layer="short_term",
                top_k=5,
            )
            if results:
                from narrative_os.core.character import MemoryEntry

                existing_events = {m.event for m in char.memory}
                for r in results:
                    if r.content not in existing_events:
                        try:
                            chapter_hint = int(r.metadata.get("chapter", 0))
                        except (TypeError, ValueError):
                            chapter_hint = 0
                        char.memory.append(
                            MemoryEntry(
                                chapter=chapter_hint,
                                event=r.content[:300],
                                emotion="",
                                importance=float(r.similarity or 0.5),
                            )
                        )
        except Exception:
            pass
        return char


# ------------------------------------------------------------------ #
# Module singleton                                                     #
# ------------------------------------------------------------------ #

_repo: CharacterRepository | None = None


def get_character_repository() -> CharacterRepository:
    global _repo
    if _repo is None:
        _repo = CharacterRepository()
    return _repo
