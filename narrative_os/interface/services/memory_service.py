"""services/memory_service.py — 记忆检索应用服务。"""
from __future__ import annotations

import sys
from typing import Any


class MemoryService:
    @staticmethod
    def _serialize_record(item: Any) -> dict[str, Any]:
        record_id = getattr(item, "record_id", "")
        content = getattr(item, "content", "")
        similarity = getattr(item, "similarity", 0.0)
        metadata = getattr(item, "metadata", {})
        return {
            "record_id": record_id if isinstance(record_id, str) else "",
            "content": content if isinstance(content, str) else str(content or ""),
            "similarity": float(similarity) if isinstance(similarity, (int, float)) else 0.0,
            "metadata": dict(metadata) if isinstance(metadata, dict) else {},
        }

    def _get_memory_system_class(self):
        api_mod = sys.modules.get("narrative_os.interface.api")
        if api_mod is not None and hasattr(api_mod, "MemorySystem"):
            return api_mod.MemorySystem
        from narrative_os.core.memory import MemorySystem

        return MemorySystem

    def get_snapshot(self, project_id: str) -> dict[str, Any]:
        memory_system = self._get_memory_system_class()(project_id=project_id)
        try:
            counts = memory_system.collection_counts()
            short = counts.get("short", 0)
            mid = counts.get("mid", 0)
            long_term = counts.get("long", 0)
        except Exception:
            short, mid, long_term = 0, 0, 0

        recent_anchors: list[dict[str, Any]] = []
        try:
            for item in memory_system.get_recent_anchors(last_n=5):
                recent_anchors.append(self._serialize_record(item))
        except Exception:
            pass

        return {
            "short_term": short,
            "mid_term": mid,
            "long_term": long_term,
            "collections": {
                "short_term": short,
                "mid_term": mid,
                "long_term": long_term,
            },
            "recent_anchors": recent_anchors,
        }

    def search_memory(self, project_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        memory_system = self._get_memory_system_class()(project_id=project_id)
        try:
            results = memory_system.retrieve_memory(query, top_k=limit)
        except Exception:
            results = []
        return [self._serialize_record(item) for item in results]


_memory_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    global _memory_service
    if _memory_service is None:
        _memory_service = MemoryService()
    return _memory_service
