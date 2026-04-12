"""services/world_service.py — 世界观沙盘应用服务。"""
from __future__ import annotations

import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.core.world_sandbox import (
    WorldSandboxData,
    ConceptData,
    WorldRelation,
    Region,
    Faction,
    PowerSystem,
    TimelineSandboxEvent,
    PowerSystemTemplateType,
    POWER_SYSTEM_TEMPLATES,
)
from narrative_os.infra.models import (
    WorldSandbox as WorldSandboxModel,
    StoryConcept as StoryConceptModel,
)
from narrative_os.infra.database import AsyncSessionLocal


# ------------------------------------------------------------------ #
# 辅助函数（从 api.py 迁移）                                            #
# ------------------------------------------------------------------ #

def collect_world_node_ids(sandbox: WorldSandboxData) -> set[str]:
    region_ids = {r.id for r in sandbox.regions}
    faction_ids = {f.id for f in sandbox.factions}
    return region_ids | faction_ids


def sync_territory_links(sandbox: WorldSandboxData) -> None:
    """双向同步 region.faction_ids ↔ faction.territory_region_ids。"""
    faction_region_map: dict[str, set[str]] = {f.id: set(f.territory_region_ids) for f in sandbox.factions}
    region_set = {r.id for r in sandbox.regions}
    for r in sandbox.regions:
        for fid in list(r.faction_ids):
            if fid in faction_region_map:
                faction_region_map[fid].add(r.id)
            else:
                r.faction_ids.remove(fid)
    for f in sandbox.factions:
        f.territory_region_ids = [rid for rid in faction_region_map.get(f.id, set()) if rid in region_set]
    for f in sandbox.factions:
        for rid in f.territory_region_ids:
            r = next((x for x in sandbox.regions if x.id == rid), None)
            if r and f.id not in r.faction_ids:
                r.faction_ids.append(f.id)


# ------------------------------------------------------------------ #
# WorldService                                                         #
# ------------------------------------------------------------------ #

class WorldService:
    """世界观沙盘 CRUD 服务。"""

    async def get_sandbox(self, project_id: str, db: AsyncSession) -> WorldSandboxData:
        result = await db.execute(
            select(WorldSandboxModel).where(WorldSandboxModel.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return WorldSandboxData()
        return WorldSandboxData.model_validate_json(row.sandbox_json)

    async def save_sandbox(self, project_id: str, data: WorldSandboxData, db: AsyncSession) -> None:
        result = await db.execute(
            select(WorldSandboxModel).where(WorldSandboxModel.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        json_str = data.model_dump_json()
        if row is None:
            row = WorldSandboxModel(
                id=_uuid.uuid4().hex,
                project_id=project_id,
                sandbox_json=json_str,
            )
            db.add(row)
        else:
            row.sandbox_json = json_str
        await db.commit()

    async def get_concept(self, project_id: str, db: AsyncSession) -> ConceptData:
        result = await db.execute(
            select(StoryConceptModel).where(StoryConceptModel.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return ConceptData()
        return ConceptData.model_validate_json(row.concept_json)

    async def save_concept(self, project_id: str, data: ConceptData, db: AsyncSession) -> None:
        result = await db.execute(
            select(StoryConceptModel).where(StoryConceptModel.project_id == project_id)
        )
        row = result.scalar_one_or_none()
        json_str = data.model_dump_json()
        if row is None:
            row = StoryConceptModel(
                id=_uuid.uuid4().hex,
                project_id=project_id,
                concept_json=json_str,
            )
            db.add(row)
        else:
            row.concept_json = json_str
        await db.commit()


_world_service: WorldService | None = None


def get_world_service() -> WorldService:
    global _world_service
    if _world_service is None:
        _world_service = WorldService()
    return _world_service
