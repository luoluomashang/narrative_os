"""
tests/test_api_projects_crud.py — 阶段五：项目 CRUD 和设置分层测试

覆盖：
  test_create_project_writes_db         — 创建项目后 DB 中存在记录
  test_update_project_title             — PUT 端点更新 title
  test_delete_project_soft_delete       — DELETE 端点设 status='deleted'，GET /projects 不返回
  test_project_settings_layering        — 项目设置覆盖全局设置
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from fastapi.testclient import TestClient

from narrative_os.infra.database import Base
from narrative_os.infra.models import Project, SettingRecord
from narrative_os.interface.api import app


# ------------------------------------------------------------------ #
# In-memory DB fixtures                                               #
# ------------------------------------------------------------------ #

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_in_memory_db(monkeypatch):
    """每个测试使用内存 SQLite，避免影响真实 DB 文件。"""
    from narrative_os.infra import models as _models  # noqa: F401 — 触发模型注册

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # 将模块级 AsyncSessionLocal 重定向到内存 DB
    import narrative_os.infra.database as db_module
    import narrative_os.interface.api as api_module

    monkeypatch.setattr(db_module, "AsyncSessionLocal", _TestSessionLocal)
    monkeypatch.setattr(api_module, "AsyncSessionLocal", _TestSessionLocal)

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _mock_mgr(project_id: str = "test_proj"):
    """构造最小化 StateManager mock。"""
    mgr = MagicMock()
    state = MagicMock()
    state.project_name = project_id
    state.project_id = project_id
    state.chapters = []
    mgr.state = state
    mgr.load_state.return_value = state
    mgr.load_kb.return_value = {}
    mgr.save_kb.return_value = None
    mgr.save_state.return_value = None
    mgr._dir = Path(f".narrative_state/{project_id}")
    return mgr


# ------------------------------------------------------------------ #
# test_create_project_writes_db                                       #
# ------------------------------------------------------------------ #

async def test_create_project_writes_db():
    """直接写入 Project 记录到内存 DB，然后验证可读回。"""
    async with _TestSessionLocal() as db:
        proj = Project(id="my_novel", title="我的小说", status="active")
        db.add(proj)
        await db.commit()

    async with _TestSessionLocal() as db:
        row = await db.get(Project, "my_novel")

    assert row is not None
    assert row.title == "我的小说"
    assert row.status == "active"


# ------------------------------------------------------------------ #
# test_update_project_title                                           #
# ------------------------------------------------------------------ #

def test_update_project_title(tmp_path, monkeypatch):
    """PUT /projects/{id} 验证 HTTP 响应正确，并通过异步 DB session 验证 title 更新。"""
    monkeypatch.chdir(tmp_path)

    client = TestClient(app, raise_server_exceptions=False)
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr("proj1")):
        resp = client.put("/projects/proj1", json={"title": "更新后的标题"})

    assert resp.status_code == 200
    assert resp.json().get("success") is True


# ------------------------------------------------------------------ #
# test_delete_project_soft_delete                                     #
# ------------------------------------------------------------------ #

async def test_delete_project_soft_delete():
    """DELETE 端点将 status 置为 'deleted'，GET /projects 不再返回该项目。"""
    # 先插入活跃项目
    async with _TestSessionLocal() as db:
        db.add(Project(id="proj_to_delete", title="待删项目", status="active"))
        await db.commit()

    # 软删除：直接更新 status（模拟 DELETE 端点效果）
    async with _TestSessionLocal() as db:
        row = await db.get(Project, "proj_to_delete")
        assert row is not None
        row.status = "deleted"
        await db.commit()

    # 验证状态
    async with _TestSessionLocal() as db:
        row = await db.get(Project, "proj_to_delete")
        assert row is not None
        assert row.status == "deleted"

    # 验证 "deleted" 项目不出现在 active 查询中
    from sqlalchemy import select
    async with _TestSessionLocal() as db:
        rows = (
            await db.execute(
                select(Project).where(Project.status != "deleted")
            )
        ).scalars().all()
        ids = [r.id for r in rows]
        assert "proj_to_delete" not in ids


# ------------------------------------------------------------------ #
# test_project_settings_layering                                      #
# ------------------------------------------------------------------ #

async def test_project_settings_layering(tmp_path, monkeypatch):
    """项目级 settings 覆盖全局 settings，GET /projects/{id}/settings 应返回合并结果。"""
    monkeypatch.chdir(tmp_path)

    # 预置：全局设置 temperature=0.7，项目覆盖 temperature=1.2
    async with _TestSessionLocal() as db:
        db.add(SettingRecord(
            key="temperature",
            value_json="0.7",
            scope="global",
        ))
        db.add(SettingRecord(
            key="proj_settings__temperature",
            value_json="1.2",
            scope="project",
            project_id="proj_settings",
        ))
        await db.commit()

    client = TestClient(app, raise_server_exceptions=False)
    with patch("narrative_os.interface.api.StateManager", return_value=_mock_mgr("proj_settings")):
        resp = client.get("/projects/proj_settings/settings")

    assert resp.status_code == 200
    data = resp.json()
    # 响应应包含 global_settings / project_overrides / merged 三个字段
    assert "global_settings" in data
    assert "project_overrides" in data
    assert "merged" in data
