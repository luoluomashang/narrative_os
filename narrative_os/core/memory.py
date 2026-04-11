"""
core/memory.py — Phase 1: MemorySystem（记忆系统）

三层分离 + ChromaDB 向量数据库：
  ShortTermMemory  — 当前章（最近 ~800 词上下文）
  MidTermMemory    — 当前卷/弧段（章节摘要）
  LongTermMemory   — 全书设定（语义设定事实）

三种类型：
  semantic  — 语义记忆（世界设定、规则、不变事实）
  event     — 事件记忆（发生了什么）
  style     — 风格记忆（DNA、作者口吻）

ChromaDB Collection 命名规范：
  narrative_short_{project_id}
  narrative_mid_{project_id}
  narrative_long_{project_id}

UI 映射：三层空间隐喻界面 + 知识图谱透视（余弦相似度溯源）
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from narrative_os.infra.config import settings

MemoryType = Literal["semantic", "event", "style"]
MemoryLayer = Literal["short", "mid", "long"]


class MemoryPool(str, Enum):
    """记忆分池 — Phase 4.4 新增。

    AUTHOR : 创作写入池（默认池，保存写作流水线产生的记忆）
    TRPG   : 互动模式池（TRPG 会话写入，不污染主线）
    CANON  : 正史池（CanonCommit 审批通过后转入）
    """
    AUTHOR = "author"
    TRPG = "trpg"
    CANON = "canon"


# ------------------------------------------------------------------ #
# Memory Entry                                                          #
# ------------------------------------------------------------------ #

class MemoryRecord(BaseModel):
    """
    记忆条目 — 写入 ChromaDB 时的结构化 document + metadata。
    """
    id: str
    content: str                      # 写入 ChromaDB document 字段
    memory_type: MemoryType
    layer: MemoryLayer
    chapter: int = 0
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    characters: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_chroma_doc(self) -> tuple[str, str, dict[str, Any]]:
        """返回 (id, document, metadata) 供 ChromaDB collection.add() 使用。"""
        return (
            self.id,
            self.content,
            {
                "memory_type": self.memory_type,
                "layer": self.layer,
                "chapter": self.chapter,
                "importance": self.importance,
                "characters": json.dumps(self.characters, ensure_ascii=False),
                "tags": json.dumps(self.tags, ensure_ascii=False),
                "timestamp": self.timestamp,
            },
        )


@dataclass
class RetrievalResult:
    """检索结果条目（含余弦相似度，供 UI 知识图谱透视使用）。"""
    record_id: str
    content: str
    similarity: float
    metadata: dict[str, Any]


# ------------------------------------------------------------------ #
# MemorySystem                                                          #
# ------------------------------------------------------------------ #

class MemorySystem:
    """
    三层记忆系统 — ChromaDB 后端。

    初始化：
        mem = MemorySystem(project_id="my_novel")
        # 会自动创建/加载 3 个 ChromaDB collection

    写入：
        mem.write_memory(content="主角击败了刘长老", memory_type="event",
                         chapter=5, importance=0.8, characters=["林枫","刘长老"])

    检索：
        results = mem.retrieve_memory("林枫 击败 长老", top_k=3)

    自动压缩：
        mem.summarize_and_compress(chapter=5)  # short→mid 摘要
        mem.archive(volume=1)                   # mid→long 归档
    """

    def __init__(self, project_id: str, db_path: str | None = None, persist_dir: str | None = None) -> None:
        self.project_id = project_id
        # persist_dir is an alias for db_path (used in tests with tmp_path)
        self._db_path = persist_dir or db_path or settings.chroma_db_path
        self._use_ephemeral = persist_dir is not None  # ephemeral for test isolation
        self._client = None
        # Phase 4.4: pool-aware collections — key: (pool_value, layer)
        self._pool_collections: dict[tuple[str, str], Any] = {}
        # Backward-compat alias: _collections[layer] → AUTHOR pool
        self._collections: dict[MemoryLayer, Any] = {}
        self._initialized = False
        # 记忆锚点（≤150字关键转折快照，来自 chapter_anchor_template）
        self._anchors: list[dict[str, Any]] = []

    def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        try:
            import chromadb  # type: ignore
            if self._use_ephemeral:
                self._client = chromadb.EphemeralClient()
            else:
                self._client = chromadb.PersistentClient(path=self._db_path)
            for layer in ("short", "mid", "long"):
                # Phase 4.4: create AUTHOR pool collections (default pool)
                coll_name = f"narrative_{MemoryPool.AUTHOR.value}_{layer}_{self.project_id}"
                coll = self._client.get_or_create_collection(  # type: ignore
                    name=coll_name,
                    metadata={"hnsw:space": "cosine"},
                )
                self._pool_collections[(MemoryPool.AUTHOR.value, layer)] = coll
                self._collections[layer] = coll  # backward-compat alias
            self._initialized = True
        except ImportError:
            raise ImportError(
                "ChromaDB 未安装。请运行：pip install chromadb"
            )
        except Exception as e:
            raise RuntimeError(f"ChromaDB 初始化失败: {e}") from e

    # ---------------------------------------------------------------- #
    # Write                                                              #
    # ---------------------------------------------------------------- #

    def _get_pool_collection(self, pool: MemoryPool, layer: MemoryLayer) -> Any:
        """按池+层获取/懒创建 ChromaDB collection。"""
        self._ensure_initialized()
        key = (pool.value, layer)
        if key not in self._pool_collections:
            coll_name = f"narrative_{pool.value}_{layer}_{self.project_id}"
            self._pool_collections[key] = self._client.get_or_create_collection(  # type: ignore
                name=coll_name,
                metadata={"hnsw:space": "cosine"},
            )
        return self._pool_collections[key]

    def write_memory(
        self,
        content: str,
        memory_type: MemoryType,
        *,
        layer: MemoryLayer = "short",
        chapter: int = 0,
        importance: float = 0.5,
        characters: list[str] | None = None,
        tags: list[str] | None = None,
        record_id: str | None = None,
        pool: MemoryPool = MemoryPool.AUTHOR,
    ) -> MemoryRecord:
        """
        写入一条记忆到指定层（默认 short）。

        importance 应在写入前由 LLM 评分（Phase 2 接入），当前接受外部传入。
        """
        self._ensure_initialized()
        import uuid
        rid = record_id or str(uuid.uuid4())
        record = MemoryRecord(
            id=rid,
            content=content,
            memory_type=memory_type,
            layer=layer,
            chapter=chapter,
            importance=importance,
            characters=characters or [],
            tags=tags or [],
        )
        doc_id, document, metadata = record.to_chroma_doc()
        coll = self._get_pool_collection(pool, layer)
        # 如已存在则 upsert，否则 add
        try:
            coll.upsert(ids=[doc_id], documents=[document], metadatas=[metadata])
        except Exception as e:
            raise RuntimeError(f"写入 ChromaDB 失败 (pool={pool.value}, layer={layer}): {e}") from e
        return record

    # ---------------------------------------------------------------- #
    # Retrieve                                                           #
    # ---------------------------------------------------------------- #

    def retrieve_memory(
        self,
        query: str,
        *,
        top_k: int = 5,
        layer: MemoryLayer | None = None,
        memory_type: MemoryType | None = None,
        min_importance: float = 0.0,
        chapter_range: tuple[int, int] | None = None,
        pools: list[MemoryPool] | None = None,
    ) -> list[RetrievalResult]:
        """
        语义检索记忆。

        layer=None 时跨三层检索并按 similarity * importance 排序。
        pools=None 时默认检索 AUTHOR + CANON 池（不检索 TRPG 池，防止污染主线）。
        返回 RetrievalResult 列表（含 similarity，供 UI 知识图谱透视展示）。
        """
        self._ensure_initialized()

        pools_to_search: list[MemoryPool] = pools if pools is not None else [
            MemoryPool.AUTHOR, MemoryPool.CANON
        ]
        layers_to_search: list[MemoryLayer] = (
            [layer] if layer else ["short", "mid", "long"]
        )

        where_filter: dict[str, Any] = {}
        if memory_type:
            where_filter["memory_type"] = {"$eq": memory_type}
        if min_importance > 0.0:
            where_filter["importance"] = {"$gte": min_importance}

        all_results: list[RetrievalResult] = []
        for pool in pools_to_search:
            for lyr in layers_to_search:
                coll = self._get_pool_collection(pool, lyr)
                try:
                    results = coll.query(
                        query_texts=[query],
                        n_results=min(top_k, coll.count() or 1),
                        where=where_filter or None,
                        include=["documents", "metadatas", "distances"],
                    )
                except Exception:
                    continue

                docs = results.get("documents", [[]])[0]
                metas = results.get("metadatas", [[]])[0]
                dists = results.get("distances", [[]])[0]

                for doc, meta, dist in zip(docs, metas, dists):
                    similarity = max(0.0, 1.0 - dist)  # cosine distance → similarity

                    # 章节范围过滤
                    if chapter_range is not None:
                        chap = meta.get("chapter", 0)
                        if not (chapter_range[0] <= chap <= chapter_range[1]):
                            continue

                    all_results.append(
                        RetrievalResult(
                            record_id=meta.get("id", ""),
                            content=doc,
                            similarity=similarity,
                            metadata=meta,
                        )
                    )

        # 按 similarity * importance 综合排序
        all_results.sort(
            key=lambda r: r.similarity * float(r.metadata.get("importance", 0.5)),
            reverse=True,
        )
        return all_results[:top_k]

    # ---------------------------------------------------------------- #
    # Compression                                                        #
    # ---------------------------------------------------------------- #

    def summarize_and_compress(self, chapter: int) -> str:
        """
        章结束后：将 short 层当章内容摘要后写入 mid 层。
        Phase 2 接入 LLM Router 后替换为真正的摘要调用。
        """
        self._ensure_initialized()
        short_results = self.retrieve_memory(
            f"chapter {chapter}",
            top_k=20,
            layer="short",
            chapter_range=(chapter, chapter),
        )
        if not short_results:
            return ""
        # 当前实现：简单拼接（Phase 2 替换为 LLM 摘要）
        combined = " | ".join(r.content[:100] for r in short_results)
        summary_content = f"[章{chapter}摘要] {combined[:500]}"
        self.write_memory(
            summary_content,
            memory_type="event",
            layer="mid",
            chapter=chapter,
            importance=0.7,
            tags=["summary", f"ch{chapter}"],
        )
        return summary_content

    def archive(self, volume: int, chapters: list[int] | None = None) -> str:
        """
        卷结束后：将 mid 层内容归档到 long 层（永久设定）。
        """
        self._ensure_initialized()
        query = f"volume {volume} summary"
        mid_results = self.retrieve_memory(query, top_k=50, layer="mid")
        if not mid_results:
            return ""
        archived_content = (
            f"[卷{volume}归档] "
            + " | ".join(r.content[:80] for r in mid_results[:10])
        )
        self.write_memory(
            archived_content,
            memory_type="semantic",
            layer="long",
            chapter=max((chapters or [0])),
            importance=0.9,
            tags=["archive", f"vol{volume}"],
        )
        return archived_content

    # ---------------------------------------------------------------- #
    # Memory Anchors（记忆锚点，来自 chapter_anchor_template）         #
    # ---------------------------------------------------------------- #

    def write_anchor(
        self,
        chapter: int,
        key_pivot: str,
        burning_question: str,
        protagonist_emotion: str,
        next_chapter_debt: str,
        hook_type: str = "",
    ) -> dict[str, Any]:
        """
        写入章节记忆锚点（≤150字关键转折快照）。
        优先级高于普通摘要，防止长上下文遗忘。
        """
        anchor = {
            "chapter": chapter,
            "key_pivot": key_pivot[:50],
            "burning_question": burning_question[:50],
            "protagonist_emotion": protagonist_emotion[:20],
            "next_chapter_debt": next_chapter_debt[:30],
            "hook_type": hook_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self._anchors.append(anchor)
        # 同时写入 short 层（高重要性）
        content = f"[锚点-章{chapter}] {key_pivot} | 悬念:{burning_question} | 债:{next_chapter_debt}"
        self.write_memory(
            content[:150],
            memory_type="event",
            layer="short",
            chapter=chapter,
            importance=0.95,
            tags=["anchor", f"ch{chapter}"],
        )
        return anchor

    def get_recent_anchors(self, last_n: int = 3) -> list["RetrievalResult"]:
        """
        返回最近 N 章的记忆锚点 RetrievalResult 列表（供 Context Builder 注入 prompt 前缀）。
        按章节降序排列（最新章在前）。
        """
        # 从内存缓存按章节降序取出最后 N 个
        recent = sorted(self._anchors, key=lambda a: a["chapter"], reverse=True)[:last_n]
        results = []
        for anchor in recent:
            results.append(
                RetrievalResult(
                    record_id=f"anchor_chapter_{anchor['chapter']}",
                    content=f"[锚点-章{anchor['chapter']}] {anchor['key_pivot']} | 悬念:{anchor['burning_question']} | 债:{anchor['next_chapter_debt']}",
                    similarity=1.0,
                    metadata={
                        "chapter": anchor["chapter"],
                        "type": "anchor",
                        "key_pivot": anchor["key_pivot"],
                    },
                )
            )
        return results

    # ---------------------------------------------------------------- #
    # Stats                                                              #
    # ---------------------------------------------------------------- #

    def collection_counts(self) -> dict[MemoryLayer, int]:
        self._ensure_initialized()
        return {
            layer: self._collections[layer].count()
            for layer in ("short", "mid", "long")
        }

    def __repr__(self) -> str:
        return f"MemorySystem(project={self.project_id!r}, initialized={self._initialized})"
