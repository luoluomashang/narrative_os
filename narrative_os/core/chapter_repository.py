"""core/chapter_repository.py — 章节文本与章节快照统一入口。"""

from __future__ import annotations

from typing import Any

from narrative_os.core.project_repository import ProjectRepository, get_project_repository
from narrative_os.core.state import ChapterMeta
from narrative_os.core.character_repository import get_character_repository
from narrative_os.core.plot_repository import get_plot_repository
from narrative_os.core.world_repository import get_world_repository


class ChapterRepository:
    def __init__(self, project_repository: ProjectRepository | None = None) -> None:
        self._projects = project_repository or get_project_repository()

    def resolve_previous_hook(self, project_id: str, chapter: int) -> str:
        if chapter <= 1:
            return ""
        handle = self._projects.try_load(project_id)
        if handle is None:
            return ""
        hook_text = handle.get_last_hook(chapter - 1)
        if hook_text:
            return hook_text
        state = handle.state
        if state is None:
            return ""
        previous_meta = next(
            (meta for meta in reversed(state.chapters) if meta.chapter == chapter - 1),
            None,
        )
        return previous_meta.summary if previous_meta is not None else ""

    def persist_generated_chapter(
        self,
        *,
        project_id: str,
        chapter: int,
        text: str,
        summary: str,
        word_count: int,
        quality_score: float,
        hook_score: float,
        hook_text: str = "",
    ) -> None:
        handle = self._projects.load_or_initialize(project_id, project_name=project_id)
        handle.save_chapter_text(chapter, text)
        plot_graph = get_plot_repository().get_plot_graph(project_id)
        characters = get_character_repository().list_character_payloads(project_id)
        world = get_world_repository().get_world_state(project_id)
        chapter_meta = ChapterMeta(
            chapter=chapter,
            summary=summary[:200],
            quality_score=quality_score,
            hook_score=hook_score,
            word_count=word_count,
        )
        handle.commit_chapter(
            chapter,
            plot_graph_dict=plot_graph.to_dict() if plot_graph is not None else None,
            characters_dict=characters,
            world_dict=world.model_dump(),
            chapter_meta=chapter_meta,
        )
        if hook_text:
            handle.save_last_hook(chapter, hook_text)

    def persist_trpg_landing(self, project_id: str, result: dict[str, Any]) -> int | None:
        chapter_text = str(result.get("chapter_text", "") or "")
        if not chapter_text:
            return None
        handle = self._projects.load_or_initialize(project_id, project_name=project_id)
        state = handle.state
        next_chapter = (state.current_chapter if state is not None else 0) + 1
        self.persist_generated_chapter(
            project_id=project_id,
            chapter=next_chapter,
            text=chapter_text,
            summary=str(result.get("history_summary", "") or ""),
            word_count=int(result.get("word_count", len(chapter_text)) or 0),
            quality_score=0.0,
            hook_score=0.0,
            hook_text=str(result.get("hook", "") or ""),
        )
        return next_chapter

    async def list_chapters(self, project_id: str) -> list[dict[str, Any]]:
        rows = await self._load_db_chapters(project_id)
        if rows:
            return [
                {
                    "chapter": row.chapter_num,
                    "summary": row.summary,
                    "word_count": row.word_count,
                    "quality_score": row.quality_score,
                    "hook_score": row.hook_score,
                    "has_text": bool(row.text),
                    "timestamp": row.created_at.isoformat() if row.created_at is not None else "",
                }
                for row in rows
            ]

        handle = self._projects.load(project_id)
        state = handle.state
        if state is None:
            return []
        chapter_files = set(handle.list_chapter_files())
        items: list[dict[str, Any]] = []
        for meta in sorted(state.chapters, key=lambda item: item.chapter):
            payload = meta.model_dump()
            payload["has_text"] = meta.chapter in chapter_files
            items.append(payload)
        return items

    async def get_chapter_text(self, project_id: str, chapter_num: int) -> dict[str, Any] | None:
        row = await self._load_db_chapter(project_id, chapter_num)
        if row is not None and row.text:
            return {
                "chapter": row.chapter_num,
                "text": row.text,
                "word_count": row.word_count or len(row.text),
                "summary": row.summary,
                "quality_score": row.quality_score,
                "hook_score": row.hook_score,
                "timestamp": row.created_at.isoformat() if row.created_at is not None else "",
            }

        handle = self._projects.load(project_id)
        text = handle.load_chapter_text(chapter_num)
        if text is None:
            return None
        state = handle.state
        meta = next(
            (item for item in (state.chapters if state is not None else []) if item.chapter == chapter_num),
            None,
        )
        return {
            "chapter": chapter_num,
            "text": text,
            "word_count": len(text),
            "summary": meta.summary if meta is not None else "",
            "quality_score": meta.quality_score if meta is not None else 0.0,
            "hook_score": meta.hook_score if meta is not None else 0.0,
            "timestamp": meta.timestamp if meta is not None else "",
        }

    async def export_project(self, project_id: str, format: str = "txt") -> dict[str, Any]:
        rows = await self._load_db_chapters(project_id)
        handle = self._projects.load(project_id)
        state = handle.state
        title = state.project_name if state is not None else project_id

        if rows:
            parts: list[str] = []
            total_words = 0
            for row in rows:
                if not row.text:
                    continue
                parts.append(f"第{row.chapter_num}章\n\n{row.text}\n\n{'─' * 40}\n")
                total_words += row.word_count or len(row.text)
            return {
                "project_id": project_id,
                "title": title,
                "chapter_count": len(parts),
                "total_chapters": len(parts),
                "total_words": total_words,
                "format": format,
                "content": "\n".join(parts),
            }

        chapter_nums = sorted(handle.list_chapter_files())
        parts = []
        total_words = 0
        for chapter_num in chapter_nums:
            text = handle.load_chapter_text(chapter_num)
            if not text:
                continue
            parts.append(f"第{chapter_num}章\n\n{text}\n\n{'─' * 40}\n")
            total_words += len(text)
        return {
            "project_id": project_id,
            "title": title,
            "chapter_count": len(parts),
            "total_chapters": len(parts),
            "total_words": total_words,
            "format": format,
            "content": "\n".join(parts),
        }

    async def _load_db_chapters(self, project_id: str) -> list[Any]:
        try:
            from sqlalchemy import select

            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import Chapter as ChapterModel

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ChapterModel)
                    .where(ChapterModel.project_id == project_id)
                    .order_by(ChapterModel.chapter_num.asc())
                )
                return list(result.scalars().all())
        except Exception:
            return []

    async def _load_db_chapter(self, project_id: str, chapter_num: int) -> Any | None:
        try:
            from sqlalchemy import select

            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import Chapter as ChapterModel

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(ChapterModel)
                    .where(ChapterModel.project_id == project_id)
                    .where(ChapterModel.chapter_num == chapter_num)
                )
                return result.scalar_one_or_none()
        except Exception:
            return None


_chapter_repository: ChapterRepository | None = None


def get_chapter_repository() -> ChapterRepository:
    global _chapter_repository
    if _chapter_repository is None:
        _chapter_repository = ChapterRepository()
    return _chapter_repository