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
import threading
from pathlib import Path
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

# ------------------------------------------------------------------ #
# DB 路径（相对于进程工作目录 narrative_os/）                          #
# ------------------------------------------------------------------ #
_DB_DIR = Path(".narrative_state")
_DB_DIR.mkdir(parents=True, exist_ok=True)
_DB_PATH = _DB_DIR / "narrative_os.db"

DATABASE_URL = f"sqlite+aiosqlite:///{_DB_PATH}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ------------------------------------------------------------------ #
# ORM 基类                                                            #
# ------------------------------------------------------------------ #
class Base(DeclarativeBase):
    pass


# ------------------------------------------------------------------ #
# 初始化 / 依赖注入                                                    #
# ------------------------------------------------------------------ #
async def init_db() -> None:
    """创建所有 ORM 表（幂等：已存在则不做任何操作）。"""
    # 延迟导入以避免循环
    from narrative_os.infra import models as _  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI Dependency: 注入 AsyncSession。"""
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
