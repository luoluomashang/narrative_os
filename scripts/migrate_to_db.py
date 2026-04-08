"""migrate_to_db.py — 将现有文件系统状态迁移到 SQLite DB。

用法:
    cd narrative_os
    python scripts/migrate_to_db.py

或指定 base_dir:
    python scripts/migrate_to_db.py --base-dir .narrative_state
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# 确保 narrative_os 包可以被找到
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from narrative_os.infra.database import init_db, AsyncSessionLocal
from narrative_os.infra.models import (
    Chapter,
    Project,
    StateSnapshot,
)


async def migrate(base_dir: Path) -> None:
    if not base_dir.exists():
        print(f"[WARN] base_dir 不存在: {base_dir}，跳过迁移。")
        return

    await init_db()
    stats = {"projects": 0, "chapters": 0, "snapshots": 0, "errors": 0}

    async with AsyncSessionLocal() as db:
        for project_dir in sorted(base_dir.iterdir()):
            if not project_dir.is_dir():
                continue

            project_id = project_dir.name
            state_file = project_dir / "state.json"

            # ── 迁移 Project ──────────────────────────────────────────────
            project_name = project_id
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    project_name = state.get("title") or state.get("project_name") or project_id
                    existing = await db.get(Project, project_id)
                    if existing is None:
                        db.add(Project(
                            id=project_id,
                            title=project_name,
                            genre=state.get("genre", ""),
                            one_sentence=state.get("one_sentence", ""),
                            one_paragraph=state.get("one_paragraph", ""),
                            settings_json=json.dumps(state.get("settings", {}), ensure_ascii=False),
                        ))
                        stats["projects"] += 1
                except Exception as exc:
                    print(f"[ERROR] project {project_id}: {exc}")
                    stats["errors"] += 1

            # ── 迁移 Chapter Markdown 文件 ─────────────────────────────────
            chapters_dir = project_dir / "chapters"
            if chapters_dir.exists():
                for md_file in sorted(chapters_dir.glob("*.md")):
                    try:
                        chapter_num_str = md_file.stem  # e.g. "001"
                        chapter_num = int(chapter_num_str)
                        text = md_file.read_text(encoding="utf-8")
                        word_count = len(text)

                        existing = (await db.execute(
                            __import__("sqlalchemy", fromlist=["select"]).select(Chapter).where(
                                Chapter.project_id == project_id,
                                Chapter.chapter_num == chapter_num,
                            )
                        )).scalars().first()

                        if existing is None:
                            db.add(Chapter(
                                project_id=project_id,
                                chapter_num=chapter_num,
                                text=text,
                                word_count=word_count,
                            ))
                            stats["chapters"] += 1
                    except Exception as exc:
                        print(f"[ERROR] chapter {md_file}: {exc}")
                        stats["errors"] += 1

            # ── 迁移 StateSnapshot JSON 文件 ──────────────────────────────
            versions_dir = project_dir / "versions"
            if versions_dir.exists():
                for snap_file in sorted(versions_dir.glob("*.json")):
                    try:
                        snap_data = json.loads(snap_file.read_text(encoding="utf-8"))
                        snapshot_id = snap_file.stem
                        existing = await db.get(StateSnapshot, snapshot_id)
                        if existing is None:
                            chapter_num = snap_data.get("chapter", 0)
                            db.add(StateSnapshot(
                                id=snapshot_id,
                                project_id=project_id,
                                chapter_num=chapter_num,
                                state_json=json.dumps(snap_data, ensure_ascii=False),
                                label=snap_data.get("label", ""),
                            ))
                            stats["snapshots"] += 1
                    except Exception as exc:
                        print(f"[ERROR] snapshot {snap_file}: {exc}")
                        stats["errors"] += 1

        await db.commit()

    print("\n=== 迁移完成 ===")
    print(f"  项目(projects)   : {stats['projects']}")
    print(f"  章节(chapters)   : {stats['chapters']}")
    print(f"  快照(snapshots)  : {stats['snapshots']}")
    if stats["errors"]:
        print(f"  错误(errors)     : {stats['errors']}  ← 请检查上方 [ERROR] 日志")
    else:
        print("  无错误 ✓")


def main() -> None:
    parser = argparse.ArgumentParser(description="迁移文件系统数据到 SQLite DB")
    parser.add_argument(
        "--base-dir",
        default=".narrative_state",
        help="项目状态根目录（默认 .narrative_state）",
    )
    args = parser.parse_args()
    asyncio.run(migrate(Path(args.base_dir)))


if __name__ == "__main__":
    main()
