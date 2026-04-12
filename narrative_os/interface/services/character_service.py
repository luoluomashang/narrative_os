"""services/character_service.py — 角色管理应用服务。"""
from __future__ import annotations


class CharacterService:
    """角色管理服务（薄包装层）。"""
    pass


def get_character_service() -> CharacterService:
    return CharacterService()
