from __future__ import annotations

import sqlite3
from pathlib import Path


async def test_init_db_upgrades_legacy_world_tables(tmp_path, monkeypatch):
    legacy_db_path = tmp_path / "legacy_runtime.db"

    conn = sqlite3.connect(legacy_db_path)
    conn.execute(
        "CREATE TABLE world_sandboxes ("
        "id TEXT PRIMARY KEY, "
        "project_id TEXT NOT NULL, "
        "sandbox_json TEXT DEFAULT '{}', "
        "updated_at TEXT"
        ")"
    )
    conn.execute(
        "CREATE TABLE story_concepts ("
        "id TEXT PRIMARY KEY, "
        "project_id TEXT NOT NULL, "
        "concept_json TEXT DEFAULT '{}', "
        "updated_at TEXT"
        ")"
    )
    conn.commit()
    conn.close()

    monkeypatch.setenv("NARRATIVE_DB_URL", f"sqlite+aiosqlite:///{legacy_db_path}")

    import narrative_os.infra.database as dbm

    await dbm.init_db()

    conn = sqlite3.connect(legacy_db_path)
    world_columns = {row[1] for row in conn.execute("PRAGMA table_info(world_sandboxes)")}
    concept_columns = {row[1] for row in conn.execute("PRAGMA table_info(story_concepts)")}
    run_columns = {row[1] for row in conn.execute("PRAGMA table_info(runs)")}
    step_columns = {row[1] for row in conn.execute("PRAGMA table_info(run_steps)")}
    artifact_columns = {row[1] for row in conn.execute("PRAGMA table_info(artifacts)")}
    checkpoint_columns = {row[1] for row in conn.execute("PRAGMA table_info(approval_checkpoints)")}
    tables = {
        row[0]
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    conn.close()

    assert {"runtime_world_json", "user_id"}.issubset(world_columns)
    assert "user_id" in concept_columns
    assert {"correlation_id", "failure_type", "failure_message", "root_cause_step_id"}.issubset(run_columns)
    assert {"correlation_id", "failure_type", "failure_message"}.issubset(step_columns)
    assert "correlation_id" in artifact_columns
    assert "correlation_id" in checkpoint_columns
    assert {"book_plans", "volume_plans", "chapter_plans", "scene_beats"}.issubset(tables)


async def test_init_db_uses_state_dir_when_env_not_set(tmp_path, monkeypatch):
    monkeypatch.delenv("NARRATIVE_DB_URL", raising=False)

    from narrative_os.infra.config import settings
    import narrative_os.infra.database as dbm

    state_dir = tmp_path / "state"
    monkeypatch.setattr(settings, "state_dir", str(state_dir))

    await dbm.init_db()

    assert (state_dir / "narrative_os.db").exists()
    assert Path(dbm.DATABASE_URL.removeprefix("sqlite+aiosqlite:///")) == state_dir / "narrative_os.db"