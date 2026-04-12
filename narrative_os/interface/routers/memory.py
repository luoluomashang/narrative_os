"""routers/memory.py — 记忆搜索路由模块。"""
from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, Query

from narrative_os.schemas.memory import (
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemorySnapshot,
)

router = APIRouter(tags=["memory"])


def _get_memory_system_class():
    """返回 MemorySystem 类，优先从 api 模块获取以支持测试 mock。"""
    _api = sys.modules.get("narrative_os.interface.api")
    if _api is not None and hasattr(_api, "MemorySystem"):
        return _api.MemorySystem
    from narrative_os.core.memory import MemorySystem
    return MemorySystem


def _try_load_project(project_id: str):
    _api = sys.modules.get("narrative_os.interface.api")
    _try = getattr(_api, "_try_load_project", None) if _api else None
    if _try:
        return _try(project_id)
    from narrative_os.interface.services.project_service import get_project_service
    return get_project_service().try_load_project(project_id)


@router.get("/projects/{project_id}/memory", response_model=MemorySnapshot, summary="三层记忆快照")
async def get_project_memory(project_id: str) -> MemorySnapshot:
    """返回三层记忆系统的计数快照。项目不存在时返回空快照。"""
    _try_load_project(project_id)
    MemorySystem = _get_memory_system_class()
    mem = MemorySystem(project_id=project_id)
    try:
        counts = mem.collection_counts()
        short = counts.get("short", 0)
        mid = counts.get("mid", 0)
        long_ = counts.get("long", 0)
    except Exception:
        short, mid, long_ = 0, 0, 0

    recent_anchors: list[dict[str, Any]] = []
    try:
        for r in mem.get_recent_anchors(last_n=5):
            recent_anchors.append({
                "record_id": r.record_id,
                "content": r.content,
                "similarity": r.similarity,
                "metadata": dict(r.metadata),
            })
    except Exception:
        pass

    return MemorySnapshot(
        short_term=short,
        mid_term=mid,
        long_term=long_,
        collections={"short_term": short, "mid_term": mid, "long_term": long_},
        recent_anchors=recent_anchors,
    )


@router.get("/projects/{project_id}/memory/search", response_model=MemorySearchResult, summary="RAG 记忆检索")
async def search_project_memory_get(
    project_id: str,
    q: str = Query(..., max_length=200),
) -> MemorySearchResult:
    """RAG 检索记忆。"""
    _try_load_project(project_id)
    MemorySystem = _get_memory_system_class()
    mem = MemorySystem(project_id=project_id)
    try:
        results = mem.retrieve_memory(q, top_k=5)
        return MemorySearchResult(
            query=q,
            results=[
                MemoryRecord(
                    record_id=r.record_id,
                    content=r.content,
                    similarity=r.similarity,
                    metadata=dict(r.metadata),
                )
                for r in results
            ],
        )
    except Exception:
        return MemorySearchResult(query=q, results=[])


@router.post("/projects/{project_id}/memory/search", response_model=list[MemoryRecord], summary="按语义搜索记忆")
async def search_memory_post(
    project_id: str, req: MemorySearchRequest
) -> list[MemoryRecord]:
    from narrative_os.core.state import StateManager
    mgr = StateManager(project_id=project_id, base_dir=".narrative_state")
    try:
        mgr.load_state()
    except FileNotFoundError:
        return []
    try:
        results = mgr.search_memory(query=req.query, limit=req.limit)
        if not isinstance(results, list):
            return []
        return [MemoryRecord.model_validate(item) for item in results if isinstance(item, dict)]
    except Exception:
        return []

