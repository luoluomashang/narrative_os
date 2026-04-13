"""
core/world_repository.py — Phase 6 Stage 1: 统一世界数据入口

职责：
  - 对外暴露统一接口：get_world_state(), get_sandbox_data(), get_concept_data()
  - 内部按优先级取数：已发布 RuntimeWorldState → 最新 sandbox → seed/KB world
  - 屏蔽底层 DB / JSON / KB 存储差异

优先级说明：
  1. DB world_sandboxes 表（runtime_world_json 字段，即已发布的 RuntimeWorldState）
  2. DB world_sandboxes 表（sandbox_json 字段，最新沙盘数据转换为 WorldState）
  3. 文件系统 .narrative_state/{project_id}/knowledge_base.json 的 world 字段
  4. 返回空 WorldState
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from narrative_os.core.world import WorldState
from narrative_os.core.world_sandbox import WorldSandboxData, ConceptData
from narrative_os.core.state_snapshot_store import get_sqlite_db_path, save_runtime_snapshot_payload
from narrative_os.infra.config import settings


class WorldRepository:
    """
    统一世界数据访问层。

    所有调用方通过此类读写世界数据，不再直接操作 DB model 或 JSON 文件。
    """

    def __init__(self) -> None:
        self._state_root = Path(settings.state_dir)

    # ------------------------------------------------------------------ #
    # 同步接口（供 context_builder 等非异步调用方使用）                      #
    # ------------------------------------------------------------------ #

    def get_world_state(self, project_id: str) -> WorldState:
        """
        按优先级返回最新 WorldState：
          1. 已发布的 RuntimeWorldState（DB）
          2. 沙盘数据转换（DB）
          3. KB world（文件系统）
          4. 空 WorldState
        """
        runtime = self._load_db_runtime_world_sync(project_id) if self._state_root == Path(settings.state_dir) else None
        if runtime is not None:
            return runtime

        sandbox = self._load_db_sandbox_sync(project_id) if self._state_root == Path(settings.state_dir) else None
        if sandbox is not None and (sandbox.factions or sandbox.regions or sandbox.world_rules):
            from narrative_os.core.world_compiler import WorldCompiler

            compiler = WorldCompiler()
            world, _ = compiler.compile(concept=self._load_db_concept_sync(project_id), sandbox=sandbox)
            return world

        kb_world = self._load_kb_world(project_id)
        if kb_world is not None:
            return kb_world
        return WorldState()

    def get_published_world_state(self, project_id: str) -> WorldState | None:
        """仅返回已发布的 RuntimeWorldState。"""
        runtime = self._load_db_runtime_world_sync(project_id) if self._state_root == Path(settings.state_dir) else None
        if runtime is not None:
            return runtime
        kb = self._load_kb(project_id)
        if kb is None:
            return None
        world_dict = kb.get("runtime_world")
        if not world_dict:
            return None
        try:
            return WorldState.model_validate(world_dict)
        except Exception:
            return None

    def has_published_world(self, project_id: str) -> bool:
        """是否已发布 RuntimeWorldState。"""
        return self.get_published_world_state(project_id) is not None

    def get_sandbox_data(self, project_id: str) -> WorldSandboxData:
        """返回最新沙盘数据（从 KB 存储中读取）。"""
        sandbox = self._load_db_sandbox_sync(project_id) if self._state_root == Path(settings.state_dir) else None
        if sandbox is not None:
            return sandbox
        sandbox = self._load_kb_sandbox(project_id)
        if sandbox is not None:
            return sandbox
        return WorldSandboxData()

    def get_concept_data(self, project_id: str) -> ConceptData | None:
        """返回故事概念数据（从 KB 存储中读取）。"""
        concept = self._load_db_concept_sync(project_id) if self._state_root == Path(settings.state_dir) else None
        if concept is not None:
            return concept
        return self._load_kb_concept(project_id)

    def save_world_state(self, project_id: str, world: WorldState) -> None:
        """持久化 WorldState 到文件系统 KB。"""
        kb_path = self._kb_path(project_id)
        if kb_path.exists():
            try:
                kb: dict[str, Any] = json.loads(kb_path.read_text(encoding="utf-8"))
            except Exception:
                kb = {}
        else:
            kb_path.parent.mkdir(parents=True, exist_ok=True)
            kb = {}
        kb["world"] = world.model_dump()
        kb_path.write_text(
            json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def save_runtime_world_state(self, project_id: str, world: WorldState) -> None:
        """保存已发布的 RuntimeWorldState（完整 WorldState 序列化到 KB 的 runtime_world 字段）。"""
        if self._state_root == Path(settings.state_dir):
            self._save_db_runtime_world_sync(project_id, world)
            save_runtime_snapshot_payload(project_id, world=world.model_dump())
        kb_path = self._kb_path(project_id)
        if kb_path.exists():
            try:
                kb: dict[str, Any] = json.loads(kb_path.read_text(encoding="utf-8"))
            except Exception:
                kb = {}
        else:
            kb_path.parent.mkdir(parents=True, exist_ok=True)
            kb = {}
        kb["runtime_world"] = world.model_dump()
        kb["world"] = world.model_dump()  # 同步更新运行态 world
        kb_path.write_text(
            json.dumps(kb, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 异步接口（供 API / 异步流程使用）                                      #
    # ------------------------------------------------------------------ #

    async def aget_world_state(self, project_id: str) -> WorldState:
        """
        异步版本，优先级：
          1. DB world_sandboxes.runtime_world_json
          2. DB world_sandboxes.sandbox_json 编译结果
          3. 文件系统 KB world
          4. 空 WorldState
        """
        # 尝试从 DB 读取已发布的 runtime world
        runtime = await self._aload_db_runtime_world(project_id)
        if runtime is not None:
            return runtime

        # 尝试从 DB 读取 sandbox 数据并转换
        sandbox = await self._aload_db_sandbox(project_id)
        if sandbox is not None and (sandbox.factions or sandbox.regions or sandbox.world_rules):
            from narrative_os.core.world_compiler import WorldCompiler
            concept = await self._aload_db_concept(project_id)
            compiler = WorldCompiler()
            world, _ = compiler.compile(concept=concept, sandbox=sandbox)
            return world

        # 回退到文件系统 KB
        kb_world = self._load_kb_world(project_id)
        if kb_world is not None:
            return kb_world

        return WorldState()

    async def aget_sandbox_data(self, project_id: str) -> WorldSandboxData:
        """异步版本，从 DB 读取沙盘数据。"""
        sandbox = await self._aload_db_sandbox(project_id)
        if sandbox is not None:
            return sandbox
        kb_sandbox = self._load_kb_sandbox(project_id)
        if kb_sandbox is not None:
            return kb_sandbox
        return WorldSandboxData()

    async def aget_concept_data(self, project_id: str) -> ConceptData | None:
        """异步版本，从 DB 读取概念数据。"""
        concept = await self._aload_db_concept(project_id)
        if concept is not None:
            return concept
        return self._load_kb_concept(project_id)

    async def asave_runtime_world_state(self, project_id: str, world: WorldState) -> None:
        """异步版本，保存已发布的 RuntimeWorldState：持久化到 DB 和文件系统。"""
        await self._asave_db_runtime_world(project_id, world)
        save_runtime_snapshot_payload(project_id, world=world.model_dump())
        self.save_runtime_world_state(project_id, world)

    def _load_db_runtime_world_sync(self, project_id: str) -> WorldState | None:
        row = self._load_db_world_row_sync("runtime_world_json", project_id)
        if not row or row in ("{}", "null", ""):
            return None
        try:
            return WorldState.model_validate_json(row)
        except Exception:
            return None

    def _load_db_sandbox_sync(self, project_id: str) -> WorldSandboxData | None:
        row = self._load_db_world_row_sync("sandbox_json", project_id)
        if not row or row == "{}":
            return None
        try:
            return WorldSandboxData.model_validate_json(row)
        except Exception:
            return None

    def _load_db_concept_sync(self, project_id: str) -> ConceptData | None:
        db_path = get_sqlite_db_path()
        if db_path is None or not db_path.exists():
            return None
        try:
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT concept_json FROM story_concepts WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            if row is None or not row[0] or row[0] in ("{}", "null"):
                return None
            return ConceptData.model_validate_json(row[0])
        except Exception:
            return None

    def _save_db_runtime_world_sync(self, project_id: str, world: WorldState) -> None:
        db_path = get_sqlite_db_path()
        if db_path is None:
            return
        db_path.parent.mkdir(parents=True, exist_ok=True)
        payload = world.model_dump_json()
        try:
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    "SELECT id FROM world_sandboxes WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
                if row is None:
                    import uuid as _uuid

                    conn.execute(
                        """
                        INSERT INTO world_sandboxes (id, project_id, user_id, sandbox_json, runtime_world_json, updated_at)
                        VALUES (?, ?, 'local', '{}', ?, CURRENT_TIMESTAMP)
                        """,
                        (_uuid.uuid4().hex, project_id, payload),
                    )
                else:
                    conn.execute(
                        "UPDATE world_sandboxes SET runtime_world_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (payload, row[0]),
                    )
                conn.commit()
        except Exception:
            return

    def _load_db_world_row_sync(self, column: str, project_id: str) -> str | None:
        db_path = get_sqlite_db_path()
        if db_path is None or not db_path.exists():
            return None
        try:
            with sqlite3.connect(db_path) as conn:
                row = conn.execute(
                    f"SELECT {column} FROM world_sandboxes WHERE project_id = ?",
                    (project_id,),
                ).fetchone()
            if row is None:
                return None
            return row[0]
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # DB 读写 (异步)                                                       #
    # ------------------------------------------------------------------ #

    async def _aload_db_runtime_world(self, project_id: str) -> WorldState | None:
        """从 DB world_sandboxes 的 runtime_world_json 字段读取已发布状态。"""
        try:
            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import WorldSandbox as WorldSandboxModel
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorldSandboxModel).where(
                        WorldSandboxModel.project_id == project_id
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                rw_json: str | None = getattr(row, "runtime_world_json", None)
                if not rw_json or rw_json in ("{}", "null", ""):
                    return None
                return WorldState.model_validate_json(rw_json)
        except Exception:
            return None

    async def _aload_db_sandbox(self, project_id: str) -> WorldSandboxData | None:
        """从 DB 读取沙盘数据。"""
        try:
            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import WorldSandbox as WorldSandboxModel
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorldSandboxModel).where(
                        WorldSandboxModel.project_id == project_id
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                sandbox_json = getattr(row, "sandbox_json", "{}")
                if not sandbox_json or sandbox_json == "{}":
                    return None
                return WorldSandboxData.model_validate_json(sandbox_json)
        except Exception:
            return None

    async def _aload_db_concept(self, project_id: str) -> ConceptData | None:
        """从 DB 读取故事概念数据。"""
        try:
            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import StoryConcept as StoryConceptModel
            from sqlalchemy import select
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(StoryConceptModel).where(
                        StoryConceptModel.project_id == project_id
                    )
                )
                row = result.scalar_one_or_none()
                if row is None:
                    return None
                concept_json = getattr(row, "concept_json", "{}")
                if not concept_json or concept_json in ("{}", "null"):
                    return None
                return ConceptData.model_validate_json(concept_json)
        except Exception:
            return None

    async def _asave_db_runtime_world(self, project_id: str, world: WorldState) -> None:
        """将已发布状态写入 DB world_sandboxes.runtime_world_json 字段。"""
        try:
            from narrative_os.infra.database import AsyncSessionLocal
            from narrative_os.infra.models import WorldSandbox as WorldSandboxModel
            from sqlalchemy import select
            import uuid as _uuid
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(WorldSandboxModel).where(
                        WorldSandboxModel.project_id == project_id
                    )
                )
                row = result.scalar_one_or_none()
                rw_json = world.model_dump_json()
                if row is None:
                    row = WorldSandboxModel(
                        id=_uuid.uuid4().hex,
                        project_id=project_id,
                        user_id="local",
                        sandbox_json="{}",
                        runtime_world_json=rw_json,
                    )
                    db.add(row)
                else:
                    row.runtime_world_json = rw_json
                await db.commit()
        except Exception:
            pass  # DB 写失败不阻塞主流程

    # ------------------------------------------------------------------ #
    # 文件系统 KB 读取                                                     #
    # ------------------------------------------------------------------ #

    def _kb_path(self, project_id: str) -> Path:
        return self._state_root / project_id / "knowledge_base.json"

    def _load_kb(self, project_id: str) -> dict[str, Any] | None:
        """读取 KB JSON 文件。"""
        kb_path = self._kb_path(project_id)
        if not kb_path.exists():
            return None
        try:
            return json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def _load_kb_world(self, project_id: str) -> WorldState | None:
        """从 KB 文件读取 WorldState（优先 runtime_world，否则 world 字段）。"""
        kb = self._load_kb(project_id)
        if kb is None:
            return None
        # 优先使用已发布的 runtime_world
        world_dict = kb.get("runtime_world") or kb.get("world")
        if not world_dict:
            return None
        try:
            return WorldState.model_validate(world_dict)
        except Exception:
            return None

    def _load_kb_sandbox(self, project_id: str) -> WorldSandboxData | None:
        """从 KB 文件读取 WorldSandboxData。"""
        kb = self._load_kb(project_id)
        if kb is None:
            return None
        sandbox_dict = kb.get("world_sandbox")
        if not sandbox_dict:
            return None
        try:
            return WorldSandboxData.model_validate(sandbox_dict)
        except Exception:
            return None

    def _load_kb_concept(self, project_id: str) -> ConceptData | None:
        """从 KB 文件读取 ConceptData。"""
        kb = self._load_kb(project_id)
        if kb is None:
            return None
        concept_dict = kb.get("concept")
        if not concept_dict:
            return None
        try:
            return ConceptData.model_validate(concept_dict)
        except Exception:
            return None


# 模块级单例（供同步调用方直接使用）
_default_repository: WorldRepository | None = None


def get_world_repository() -> WorldRepository:
    """获取默认 WorldRepository 单例。"""
    global _default_repository
    if _default_repository is None:
        _default_repository = WorldRepository()
    return _default_repository
