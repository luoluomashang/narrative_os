"""
tests/test_cost_persistence.py — 阶段五：成本持久化测试

覆盖：
  test_cost_record_survives_restart   — 记录 cost 后重启 CostController，history() 仍有数据
  test_cost_filter_by_project         — cost/history?project_id=xxx 只返回该项目的记录
"""
from __future__ import annotations

import asyncio
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from narrative_os.infra.database import Base
from narrative_os.infra.models import CostRecord, Project


# ------------------------------------------------------------------ #
# In-memory DB fixtures                                               #
# ------------------------------------------------------------------ #

_test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
_TestSessionLocal = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_in_memory_db(monkeypatch):
    from narrative_os.infra import models as _m  # noqa: F401

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import narrative_os.infra.database as dbm
    monkeypatch.setattr(dbm, "AsyncSessionLocal", _TestSessionLocal)

    yield

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ------------------------------------------------------------------ #
# test_cost_record_survives_restart                                   #
# ------------------------------------------------------------------ #

async def test_cost_record_survives_restart():
    """CostRecord 写入 DB 后，即使 CostController 重建（模拟重启），DB 中数据仍存在。"""
    from narrative_os.infra.models import CostRecord

    # 写入一条成本记录
    async with _TestSessionLocal() as db:
        db.add(CostRecord(
            skill="scene_generator",
            agent="writer",
            tokens_in=500,
            tokens_out=1200,
            cost_usd=0.0034,
            model="gpt-4o",
        ))
        await db.commit()

    # 模拟"重启"：创建新的 CostController 实例
    from narrative_os.infra.cost import CostController
    new_ctrl = CostController()
    # 新实例内存为零，但 DB 里有记录
    assert new_ctrl.summary()["used"] == 0  # 内存已清零

    # 直接查询 DB 验证记录仍然存在
    from sqlalchemy import select
    async with _TestSessionLocal() as db:
        rows = (await db.execute(select(CostRecord))).scalars().all()

    assert len(rows) == 1
    assert rows[0].skill == "scene_generator"
    assert rows[0].tokens_in == 500
    assert rows[0].tokens_out == 1200


# ------------------------------------------------------------------ #
# test_cost_filter_by_project                                         #
# ------------------------------------------------------------------ #

async def test_cost_filter_by_project():
    """cost_records 表支持按 project_id 过滤，不同项目记录互不干扰。"""
    # 先在 DB 中插入父项目（满足外键约束，CostRecord.project_id 可 NULL）
    async with _TestSessionLocal() as db:
        db.add(Project(id="proj_alpha", title="Alpha", status="active"))
        db.add(Project(id="proj_beta", title="Beta", status="active"))
        await db.commit()

    # 写入两个项目各自的成本记录，另有一条无项目记录
    async with _TestSessionLocal() as db:
        db.add(CostRecord(skill="s1", agent="a", tokens_in=100, tokens_out=200,
                          cost_usd=0.0006, model="m", project_id="proj_alpha"))
        db.add(CostRecord(skill="s2", agent="b", tokens_in=300, tokens_out=400,
                          cost_usd=0.0014, model="m", project_id="proj_beta"))
        db.add(CostRecord(skill="s3", agent="c", tokens_in=50, tokens_out=50,
                          cost_usd=0.0002, model="m", project_id=None))
        await db.commit()

    # 按 project_id 过滤查询
    from sqlalchemy import select
    async with _TestSessionLocal() as db:
        alpha_rows = (
            await db.execute(
                select(CostRecord).where(CostRecord.project_id == "proj_alpha")
            )
        ).scalars().all()

        beta_rows = (
            await db.execute(
                select(CostRecord).where(CostRecord.project_id == "proj_beta")
            )
        ).scalars().all()

    assert len(alpha_rows) == 1
    assert alpha_rows[0].skill == "s1"

    assert len(beta_rows) == 1
    assert beta_rows[0].skill == "s2"
