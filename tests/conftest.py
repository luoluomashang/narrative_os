"""
tests/conftest.py — 全局测试夹具

提供各测试模块共享的夹具，保证测试隔离性。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


# ------------------------------------------------------------------ #
# 世界沙盘 DB 隔离夹具                                                  #
# ------------------------------------------------------------------ #

_DB_PATH = Path(".narrative_state") / "narrative_os.db"

# 需要清理的测试模块 → 清理的 project_id 前缀列表
_CLEANUP_MODULE_PREFIXES: dict[str, list[str]] = {
    "test_world_sandbox_phase3": ["test-phase3-sandbox"],
}


# ------------------------------------------------------------------ #
# 全局 DB 初始化夹具（一次性，整个测试会话）                              #
# ------------------------------------------------------------------ #

@pytest.fixture(scope="session", autouse=True)
def init_test_db():
    """
    在整个测试会话开始前触发 app lifespan（startup），确保 world_sandboxes
    等 ORM 表已在文件 DB 中创建。
    使用 TestClient 上下文管理器来触发 lifespan，避免 asyncio.run() 清空事件循环。
    """
    from narrative_os.interface.api import app
    from starlette.testclient import TestClient
    with TestClient(app, raise_server_exceptions=False):
        pass  # startup → init_db() → shutdown
    yield


@pytest.fixture(autouse=True)
def isolate_world_sandbox_db(request):
    """
    在每个函数级测试执行**前**，删除对应 project_id 前缀的 world_sandboxes 行，
    防止多次运行测试时旧数据污染断言结果。
    仅对配置了前缀的测试模块生效。
    """
    module_name = Path(request.fspath).stem  # e.g. "test_world_sandbox_phase3"
    prefixes = _CLEANUP_MODULE_PREFIXES.get(module_name)
    if not prefixes or not _DB_PATH.exists():
        yield
        return

    # 用同步 sqlite3 直接删（TestClient 本身也是同步的）
    try:
        conn = sqlite3.connect(str(_DB_PATH))
        for prefix in prefixes:
            conn.execute(
                "DELETE FROM world_sandboxes WHERE project_id LIKE ?",
                (f"{prefix}%",),
            )
        conn.commit()
        conn.close()
    except Exception:
        pass  # DB 不存在或未初始化时跳过
    yield
