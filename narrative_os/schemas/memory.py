"""schemas/memory.py — 记忆检索请求/响应模型。"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    record_id: str
    content: str
    similarity: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySnapshot(BaseModel):
    short_term: int = 0
    mid_term: int = 0
    long_term: int = 0
    collections: dict[str, int] = Field(default_factory=dict)
    recent_anchors: list[MemoryRecord] = Field(default_factory=list)


class MemorySearchRequest(BaseModel):
    query: str
    limit: int = Field(default=5, ge=1, le=20)
    top_k: int | None = Field(default=None, ge=1, le=20)


class MemorySearchResult(BaseModel):
    query: str
    results: list[MemoryRecord] = Field(default_factory=list)
