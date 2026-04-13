from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from narrative_os.infra.config import settings

UNSET = object()


def get_sqlite_db_path() -> Path | None:
    database_url = os.environ.get("NARRATIVE_DB_URL", "").strip()
    if not database_url:
        return Path(settings.state_dir) / "narrative_os.db"

    for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
        if database_url.startswith(prefix):
            raw_path = database_url[len(prefix):]
            if raw_path.startswith("/") and len(raw_path) > 2 and raw_path[2] == ":":
                raw_path = raw_path[1:]
            return Path(raw_path)
    return None


def load_runtime_snapshot_payload(project_id: str) -> dict[str, Any] | None:
    db_path = get_sqlite_db_path()
    if db_path is None or not db_path.exists():
        return None

    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT plot_graph_json, characters_json, world_json
                FROM state_snapshots
                WHERE project_id = ? AND chapter_num = 0
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT plot_graph_json, characters_json, world_json
                    FROM state_snapshots
                    WHERE project_id = ?
                    ORDER BY chapter_num DESC, id DESC
                    LIMIT 1
                    """,
                    (project_id,),
                ).fetchone()
            if row is None:
                return None
            return {
                "plot_graph": _load_json_field(row["plot_graph_json"], {}),
                "characters": _load_json_field(row["characters_json"], []),
                "world": _load_json_field(row["world_json"], {}),
            }
    except Exception:
        return None


def save_runtime_snapshot_payload(
    project_id: str,
    *,
    plot_graph: dict[str, Any] | object = UNSET,
    characters: list[dict[str, Any]] | object = UNSET,
    world: dict[str, Any] | object = UNSET,
) -> None:
    db_path = get_sqlite_db_path()
    if db_path is None:
        return

    db_path.parent.mkdir(parents=True, exist_ok=True)
    current = load_runtime_snapshot_payload(project_id) or {
        "plot_graph": {},
        "characters": [],
        "world": {},
    }
    merged_plot_graph = current["plot_graph"] if plot_graph is UNSET else plot_graph
    merged_characters = current["characters"] if characters is UNSET else characters
    merged_world = current["world"] if world is UNSET else world
    now = datetime.now(timezone.utc).isoformat()

    try:
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO projects (
                    id, title, genre, description, settings_json, status, user_id, created_at, updated_at
                ) VALUES (?, ?, '', '', '{}', 'active', 'local', ?, ?)
                """,
                (project_id, project_id, now, now),
            )
            existing = conn.execute(
                """
                SELECT id
                FROM state_snapshots
                WHERE project_id = ? AND chapter_num = 0
                ORDER BY id DESC
                LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            payload = (
                json.dumps(merged_plot_graph or {}, ensure_ascii=False),
                json.dumps(merged_characters or [], ensure_ascii=False),
                json.dumps(merged_world or {}, ensure_ascii=False),
            )
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO state_snapshots (
                        project_id, chapter_num, plot_graph_json, characters_json, world_json, user_id, created_at
                    ) VALUES (?, 0, ?, ?, ?, 'local', ?)
                    """,
                    (project_id, *payload, now),
                )
            else:
                conn.execute(
                    """
                    UPDATE state_snapshots
                    SET plot_graph_json = ?, characters_json = ?, world_json = ?
                    WHERE id = ?
                    """,
                    (*payload, existing[0]),
                )
            conn.commit()
    except Exception:
        return


def _load_json_field(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except Exception:
        return default