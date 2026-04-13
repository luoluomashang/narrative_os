"""routers/memory.py — 记忆搜索路由模块。"""
from __future__ import annotations

import sys
from typing import Any

from fastapi import APIRouter, Depends, Query

from narrative_os.interface.services.memory_service import MemoryService, get_memory_service
from narrative_os.schemas.memory import (
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemorySnapshot,
)

router = APIRouter(tags=["memory"])


def _svc() -> MemoryService:
    return get_memory_service()


@router.get("/projects/{project_id}/memory", response_model=MemorySnapshot, summary="三层记忆快照")
async def get_project_memory(
    project_id: str,
    svc: MemoryService = Depends(_svc),
) -> MemorySnapshot:
    return MemorySnapshot.model_validate(svc.get_snapshot(project_id))


@router.get("/projects/{project_id}/memory/search", response_model=MemorySearchResult, summary="RAG 记忆检索")
async def search_project_memory_get(
    project_id: str,
    q: str = Query(..., max_length=200),
    svc: MemoryService = Depends(_svc),
) -> MemorySearchResult:
    results = [MemoryRecord.model_validate(item) for item in svc.search_memory(project_id, q, limit=5)]
    return MemorySearchResult(query=q, results=results)


@router.post("/projects/{project_id}/memory/search", response_model=list[MemoryRecord], summary="按语义搜索记忆")
async def search_memory_post(
    project_id: str,
    req: MemorySearchRequest,
    svc: MemoryService = Depends(_svc),
) -> list[MemoryRecord]:
    return [MemoryRecord.model_validate(item) for item in svc.search_memory(project_id, req.query, limit=req.limit)]

