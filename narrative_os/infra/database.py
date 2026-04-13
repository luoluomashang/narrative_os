"""
infra/database.py — SQLite + SQLAlchemy 异步数据库引擎

提供：
  - 全局 async engine（SQLite + aiosqlite）
  - AsyncSession sessionmaker
  - Base 声明基类（供 models.py 继承）
  - init_db() — 创建所有表
  - get_db()  — FastAPI dependency 注入
  - fire_and_forget() — 从同步/异步上下文提交非阻塞 DB 写
"""

from __future__ import annotations

import asyncio
import os
import threading
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy import event as _sa_event
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
    AsyncEngine,
)
from sqlalchemy.orm import DeclarativeBase

from narrative_os.infra.config import settings

# ------------------------------------------------------------------ #
# DB 路径（默认相对于 settings.state_dir，可由 NARRATIVE_DB_URL 覆盖） #
# ------------------------------------------------------------------ #
def _resolve_database_url() -> str:
    env_database_url = os.environ.get("NARRATIVE_DB_URL", "").strip()
    if env_database_url:
        return env_database_url

    db_dir = Path(settings.state_dir)
    db_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_dir / 'narrative_os.db'}"


def _make_engine(database_url: str) -> AsyncEngine:
    connect_args: dict[str, object] = {"timeout": 30}
    if database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False

    new_engine = create_async_engine(
        database_url,
        echo=False,
        connect_args=connect_args,
    )
    _sa_event.listen(new_engine.sync_engine, "connect", _set_sqlite_wal)
    return new_engine


def _set_sqlite_wal(dbapi_conn, connection_record):  # type: ignore[misc]
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()


DATABASE_URL = _resolve_database_url()
engine = _make_engine(DATABASE_URL)
_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)
_schema_sync_lock = asyncio.Lock()
_schema_synced_url: str | None = None


class _SessionFactoryProxy:
    """稳定代理对象，允许底层 sessionmaker 在运行时重建。"""

    def __call__(self, *args, **kwargs):
        return _session_factory(*args, **kwargs)

    def __getattr__(self, name: str):
        return getattr(_session_factory, name)


AsyncSessionLocal = _SessionFactoryProxy()


# ------------------------------------------------------------------ #
# ORM 基类                                                            #
# ------------------------------------------------------------------ #
class Base(DeclarativeBase):
    pass


def _ensure_legacy_schema_columns(sync_conn) -> None:
    """为旧版 SQLite 库补齐阶段 3/4 需要的列。"""
    inspector = sa_inspect(sync_conn)

    def _has_column(table_name: str, column_name: str) -> bool:
        try:
            columns = inspector.get_columns(table_name)
        except Exception:
            return False
        return any(column["name"] == column_name for column in columns)

    if _has_column("world_sandboxes", "runtime_world_json") is False:
        sync_conn.execute(
            text(
                "ALTER TABLE world_sandboxes "
                "ADD COLUMN runtime_world_json TEXT NOT NULL DEFAULT '{}'"
            )
        )

    if _has_column("world_sandboxes", "user_id") is False:
        sync_conn.execute(
            text(
                "ALTER TABLE world_sandboxes "
                "ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'"
            )
        )

    if _has_column("story_concepts", "user_id") is False:
        sync_conn.execute(
            text(
                "ALTER TABLE story_concepts "
                "ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'"
            )
        )

    def _has_table(table_name: str) -> bool:
        try:
            return inspector.has_table(table_name)
        except Exception:
            return False

    def _add_column_if_missing(table_name: str, column_name: str, ddl: str) -> None:
        if _has_table(table_name) and _has_column(table_name, column_name) is False:
            sync_conn.execute(text(ddl))

    _add_column_if_missing(
        "runs",
        "user_id",
        "ALTER TABLE runs ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "runs",
        "correlation_id",
        "ALTER TABLE runs ADD COLUMN correlation_id VARCHAR(40) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "runs",
        "failure_type",
        "ALTER TABLE runs ADD COLUMN failure_type VARCHAR(40)",
    )
    _add_column_if_missing(
        "runs",
        "failure_message",
        "ALTER TABLE runs ADD COLUMN failure_message TEXT",
    )
    _add_column_if_missing(
        "runs",
        "root_cause_step_id",
        "ALTER TABLE runs ADD COLUMN root_cause_step_id VARCHAR(100)",
    )
    _add_column_if_missing(
        "run_steps",
        "correlation_id",
        "ALTER TABLE run_steps ADD COLUMN correlation_id VARCHAR(40) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "run_steps",
        "failure_type",
        "ALTER TABLE run_steps ADD COLUMN failure_type VARCHAR(40)",
    )
    _add_column_if_missing(
        "run_steps",
        "failure_message",
        "ALTER TABLE run_steps ADD COLUMN failure_message TEXT",
    )
    _add_column_if_missing(
        "artifacts",
        "correlation_id",
        "ALTER TABLE artifacts ADD COLUMN correlation_id VARCHAR(40) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "approval_checkpoints",
        "correlation_id",
        "ALTER TABLE approval_checkpoints ADD COLUMN correlation_id VARCHAR(40) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "corpus_group",
        "ALTER TABLE benchmark_sources ADD COLUMN corpus_group VARCHAR(100) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "author_name",
        "ALTER TABLE benchmark_sources ADD COLUMN author_name VARCHAR(200)",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "file_name",
        "ALTER TABLE benchmark_sources ADD COLUMN file_name VARCHAR(300) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "sha256",
        "ALTER TABLE benchmark_sources ADD COLUMN sha256 VARCHAR(64) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "char_count",
        "ALTER TABLE benchmark_sources ADD COLUMN char_count INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "chapter_sep",
        "ALTER TABLE benchmark_sources ADD COLUMN chapter_sep VARCHAR(300)",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "source_type",
        "ALTER TABLE benchmark_sources ADD COLUMN source_type VARCHAR(30) NOT NULL DEFAULT 'project_reference'",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "text_content",
        "ALTER TABLE benchmark_sources ADD COLUMN text_content TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "user_id",
        "ALTER TABLE benchmark_sources ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "benchmark_sources",
        "created_at",
        "ALTER TABLE benchmark_sources ADD COLUMN created_at DATETIME",
    )

    _add_column_if_missing(
        "benchmark_snippets",
        "profile_id",
        "ALTER TABLE benchmark_snippets ADD COLUMN profile_id VARCHAR(100) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "chapter",
        "ALTER TABLE benchmark_snippets ADD COLUMN chapter INTEGER",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "offset_start",
        "ALTER TABLE benchmark_snippets ADD COLUMN offset_start INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "offset_end",
        "ALTER TABLE benchmark_snippets ADD COLUMN offset_end INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "char_count",
        "ALTER TABLE benchmark_snippets ADD COLUMN char_count INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "anchor_score",
        "ALTER TABLE benchmark_snippets ADD COLUMN anchor_score FLOAT NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "purity_score",
        "ALTER TABLE benchmark_snippets ADD COLUMN purity_score FLOAT NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "distinctiveness_score",
        "ALTER TABLE benchmark_snippets ADD COLUMN distinctiveness_score FLOAT NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "text",
        "ALTER TABLE benchmark_snippets ADD COLUMN text TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "user_id",
        "ALTER TABLE benchmark_snippets ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "benchmark_snippets",
        "created_at",
        "ALTER TABLE benchmark_snippets ADD COLUMN created_at DATETIME",
    )

    _add_column_if_missing(
        "benchmark_profiles",
        "run_id",
        "ALTER TABLE benchmark_profiles ADD COLUMN run_id VARCHAR(100)",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "source_ids_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN source_ids_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "stable_traits_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN stable_traits_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "conditional_traits_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN conditional_traits_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "anti_traits_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN anti_traits_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "scene_anchors_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN scene_anchors_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "humanness_baseline_json",
        "ALTER TABLE benchmark_profiles ADD COLUMN humanness_baseline_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "status",
        "ALTER TABLE benchmark_profiles ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'draft'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "activated_at",
        "ALTER TABLE benchmark_profiles ADD COLUMN activated_at DATETIME",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "user_id",
        "ALTER TABLE benchmark_profiles ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "benchmark_profiles",
        "created_at",
        "ALTER TABLE benchmark_profiles ADD COLUMN created_at DATETIME",
    )

    _add_column_if_missing(
        "benchmark_scores",
        "run_id",
        "ALTER TABLE benchmark_scores ADD COLUMN run_id VARCHAR(100)",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "chapter",
        "ALTER TABLE benchmark_scores ADD COLUMN chapter INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "profile_id",
        "ALTER TABLE benchmark_scores ADD COLUMN profile_id VARCHAR(100) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "humanness_score",
        "ALTER TABLE benchmark_scores ADD COLUMN humanness_score FLOAT NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "adherence_score",
        "ALTER TABLE benchmark_scores ADD COLUMN adherence_score FLOAT NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "dimension_scores_json",
        "ALTER TABLE benchmark_scores ADD COLUMN dimension_scores_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "violations_json",
        "ALTER TABLE benchmark_scores ADD COLUMN violations_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "recommendations_json",
        "ALTER TABLE benchmark_scores ADD COLUMN recommendations_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "user_id",
        "ALTER TABLE benchmark_scores ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "benchmark_scores",
        "created_at",
        "ALTER TABLE benchmark_scores ADD COLUMN created_at DATETIME",
    )

    _add_column_if_missing(
        "author_skills",
        "run_id",
        "ALTER TABLE author_skills ADD COLUMN run_id VARCHAR(100)",
    )
    _add_column_if_missing(
        "author_skills",
        "author_name",
        "ALTER TABLE author_skills ADD COLUMN author_name VARCHAR(200) NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        "author_skills",
        "source_ids_json",
        "ALTER TABLE author_skills ADD COLUMN source_ids_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "stable_rules_json",
        "ALTER TABLE author_skills ADD COLUMN stable_rules_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "conditional_rules_json",
        "ALTER TABLE author_skills ADD COLUMN conditional_rules_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "anti_rules_json",
        "ALTER TABLE author_skills ADD COLUMN anti_rules_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "dialogue_rules_json",
        "ALTER TABLE author_skills ADD COLUMN dialogue_rules_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "scene_patterns_json",
        "ALTER TABLE author_skills ADD COLUMN scene_patterns_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "author_skills",
        "chapter_hook_patterns_json",
        "ALTER TABLE author_skills ADD COLUMN chapter_hook_patterns_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        "author_skills",
        "humanness_baseline_json",
        "ALTER TABLE author_skills ADD COLUMN humanness_baseline_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "author_skills",
        "confidence_map_json",
        "ALTER TABLE author_skills ADD COLUMN confidence_map_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        "author_skills",
        "status",
        "ALTER TABLE author_skills ADD COLUMN status VARCHAR(30) NOT NULL DEFAULT 'draft'",
    )
    _add_column_if_missing(
        "author_skills",
        "user_id",
        "ALTER TABLE author_skills ADD COLUMN user_id VARCHAR(100) NOT NULL DEFAULT 'local'",
    )
    _add_column_if_missing(
        "author_skills",
        "created_at",
        "ALTER TABLE author_skills ADD COLUMN created_at DATETIME",
    )


async def _ensure_schema_ready(force: bool = False) -> None:
    global _schema_synced_url

    if not force and _schema_synced_url == DATABASE_URL:
        return

    async with _schema_sync_lock:
        if not force and _schema_synced_url == DATABASE_URL:
            return

        from narrative_os.infra import models as _  # noqa: F401

        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(_ensure_legacy_schema_columns)

        _schema_synced_url = DATABASE_URL


async def _ensure_database_runtime() -> None:
    """当 DB URL 变化时重建 engine/sessionmaker。"""
    global DATABASE_URL, engine, _session_factory, _schema_synced_url

    target_database_url = _resolve_database_url()
    if target_database_url == DATABASE_URL:
        return

    old_engine = engine
    DATABASE_URL = target_database_url
    engine = _make_engine(DATABASE_URL)
    _session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    _schema_synced_url = None
    await old_engine.dispose()


# ------------------------------------------------------------------ #
# 初始化 / 依赖注入                                                    #
# ------------------------------------------------------------------ #
async def init_db() -> None:
    """创建所有 ORM 表（幂等：已存在则不做任何操作）。"""
    await _ensure_database_runtime()
    await _ensure_schema_ready(force=True)


async def ensure_database_runtime() -> None:
    """公开运行时 DB 对齐入口，供非依赖注入路径在打开会话前调用。"""
    await _ensure_database_runtime()
    await _ensure_schema_ready()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency: 注入 AsyncSession。"""
    await ensure_database_runtime()
    async with AsyncSessionLocal() as session:
        yield session


# ------------------------------------------------------------------ #
# Fire-and-Forget 工具函数                                            #
# ------------------------------------------------------------------ #
def fire_and_forget(coro: object) -> None:
    """
    非阻塞提交协程到 DB 写。

    - 在 asyncio 运行循环内（FastAPI）：创建 Task
    - 在同步上下文（tests、CLI）：启动后台线程执行
    """
    import inspect  # noqa: PLC0415

    if not inspect.iscoroutine(coro):
        return

    async def _safe_run(c: object) -> None:
        try:
            await c  # type: ignore[misc]
        except Exception as exc:
            from narrative_os.infra.logging import logger
            logger.error("db_fire_and_forget_failed", error=str(exc))

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_safe_run(coro))
    except RuntimeError:
        # 没有 running loop — 在后台线程中运行
        def _run() -> None:
            asyncio.run(_safe_run(coro))

        threading.Thread(target=_run, daemon=True).start()
