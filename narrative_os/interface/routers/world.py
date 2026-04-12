"""routers/world.py — 世界观沙盘路由模块。"""
from __future__ import annotations

import json as _json
import math
import time as _time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from narrative_os.core.world import WorldState
from narrative_os.core.world_sandbox import (
    WorldSandboxData,
    ConceptData,
    Region,
    Faction,
    PowerSystem,
    WorldRelation,
    TimelineSandboxEvent,
    RelationType,
    PowerSystemTemplateType,
    POWER_SYSTEM_TEMPLATES,
    get_template_summary,
    normalize_relation_type,
)
from narrative_os.infra.database import AsyncSessionLocal
from narrative_os.schemas.world import (
    AIConsistencyResponse,
    AIExpandRequest,
    AIExpandResponse,
    AIImportTextRequest,
    AIImportTextResponse,
    AISuggestRelationsRequest,
    AISuggestRelationsResponse,
    ConceptUpdateRequest,
    FinalizeWorldResponse,
    WorldMetaUpdateRequest,
    WorldMapEdge,
    WorldMapLayoutResponse,
    WorldMapNode,
    WorldOverviewResponse,
    RegionCreateRequest,
    FactionCreateRequest,
    PowerTemplateSummary,
    PowerSystemCreateRequest,
    RelationCreateRequest,
    RelationUpdateRequest,
    TimelineEventCreateRequest,
    TimelineEventUpdateRequest,
)
from narrative_os.interface.services.world_service import (
    WorldService,
    get_world_service,
    collect_world_node_ids,
    sync_territory_links,
)

router = APIRouter(tags=["world"])

# ------------------------------------------------------------------ #
# 依赖                                                                  #
# ------------------------------------------------------------------ #


def _svc() -> WorldService:
    return get_world_service()


def _get_world_svc() -> WorldService:
    """向 api.py 暴露的 WorldService 工厂（用于 _get_sandbox/_get_concept 委托）。"""
    return get_world_service()


# ------------------------------------------------------------------ #
# 故事概念端点                                                          #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/concept", response_model=ConceptData, summary="获取故事概念数据")
async def get_concept(
    project_id: str, svc: WorldService = Depends(_svc)
) -> ConceptData:
    async with AsyncSessionLocal() as db:
        concept = await svc.get_concept(project_id, db)
    return concept.model_dump()


@router.put("/projects/{project_id}/concept", response_model=ConceptData, summary="保存故事概念数据")
async def update_concept(
    project_id: str,
    req: ConceptUpdateRequest,
    svc: WorldService = Depends(_svc),
) -> ConceptData:
    async with AsyncSessionLocal() as db:
        concept = ConceptData(
            one_sentence=req.one_sentence,
            one_paragraph=req.one_paragraph,
            genre_tags=req.genre_tags,
            world_type=req.world_type,
        )
        await svc.save_concept(project_id, concept, db)
    return concept.model_dump()


# ------------------------------------------------------------------ #
# 世界基本信息                                                          #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/world", response_model=WorldSandboxData, summary="获取完整世界观沙盘数据")
async def get_world(
    project_id: str, svc: WorldService = Depends(_svc)
) -> WorldSandboxData:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    return sandbox.model_dump()


@router.put("/projects/{project_id}/world/meta", response_model=WorldSandboxData, summary="更新世界基本信息")
async def update_world_meta(
    project_id: str,
    req: WorldMetaUpdateRequest,
    svc: WorldService = Depends(_svc),
) -> WorldSandboxData:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        if req.world_name is not None:
            sandbox.world_name = req.world_name
        if req.world_type is not None:
            sandbox.world_type = req.world_type
        if req.world_description is not None:
            sandbox.world_description = req.world_description
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.model_dump()


# ------------------------------------------------------------------ #
# Regions                                                              #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/world/regions", response_model=Region, summary="创建地区节点", status_code=201)
async def create_region(
    project_id: str,
    req: RegionCreateRequest,
    svc: WorldService = Depends(_svc),
) -> Region:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        from narrative_os.core.world_sandbox import (
            RegionGeography,
            RegionRace,
            RegionCivilization,
            RegionPowerAccess,
        )
        region = Region(
            name=req.name,
            region_type=req.region_type,
            x=req.x,
            y=req.y,
            faction_ids=req.faction_ids,
            alignment=req.alignment,
            tags=req.tags,
            notes=req.notes,
            geography=RegionGeography(**(req.geography or {})),
            race=RegionRace(**(req.race or {})),
            civilization=RegionCivilization(**(req.civilization or {})),
            power_access=RegionPowerAccess(**(req.power_access or {})),
        )
        sandbox.regions.append(region)
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)
    return region.model_dump()


@router.get("/projects/{project_id}/world/regions/{region_id}", response_model=Region, summary="获取地区详情")
async def get_region(
    project_id: str, region_id: str, svc: WorldService = Depends(_svc)
) -> Region:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    region = next((r for r in sandbox.regions if r.id == region_id), None)
    if region is None:
        raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
    return region.model_dump()


@router.put("/projects/{project_id}/world/regions/{region_id}", response_model=Region, summary="更新地区数据")
async def update_region(
    project_id: str,
    region_id: str,
    req: Region,
    svc: WorldService = Depends(_svc),
) -> Region:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        idx = next((i for i, r in enumerate(sandbox.regions) if r.id == region_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
        if req.id and req.id != region_id:
            raise HTTPException(status_code=400, detail="region id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = region_id
        sandbox.regions[idx] = Region(**payload)
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.regions[idx].model_dump()


@router.delete("/projects/{project_id}/world/regions/{region_id}", summary="删除地区", status_code=204)
async def delete_region(
    project_id: str, region_id: str, svc: WorldService = Depends(_svc)
) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        original_len = len(sandbox.regions)
        sandbox.regions = [r for r in sandbox.regions if r.id != region_id]
        if len(sandbox.regions) == original_len:
            raise HTTPException(status_code=404, detail=f"Region {region_id} not found")
        sandbox.relations = [
            rel for rel in sandbox.relations
            if rel.source_id != region_id and rel.target_id != region_id
        ]
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)


# ------------------------------------------------------------------ #
# Factions                                                             #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/world/factions", response_model=Faction, summary="创建势力", status_code=201)
async def create_faction(
    project_id: str,
    req: FactionCreateRequest,
    svc: WorldService = Depends(_svc),
) -> Faction:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        faction = Faction(
            name=req.name,
            scope=req.scope,
            description=req.description,
            territory_region_ids=req.territory_region_ids,
            alignment=req.alignment,
            color=req.color,
            power_system_id=req.power_system_id,
            notes=req.notes,
        )  # type: ignore[arg-type]
        sandbox.factions.append(faction)
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)
    return faction.model_dump()


@router.get("/projects/{project_id}/world/factions/{faction_id}", response_model=Faction, summary="获取势力详情")
async def get_faction(
    project_id: str, faction_id: str, svc: WorldService = Depends(_svc)
) -> Faction:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    faction = next((f for f in sandbox.factions if f.id == faction_id), None)
    if faction is None:
        raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
    return faction.model_dump()


@router.put("/projects/{project_id}/world/factions/{faction_id}", response_model=Faction, summary="更新势力数据")
async def update_faction(
    project_id: str,
    faction_id: str,
    req: Faction,
    svc: WorldService = Depends(_svc),
) -> Faction:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        idx = next((i for i, f in enumerate(sandbox.factions) if f.id == faction_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
        if req.id and req.id != faction_id:
            raise HTTPException(status_code=400, detail="faction id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = faction_id
        sandbox.factions[idx] = Faction(**payload)
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.factions[idx].model_dump()


@router.delete("/projects/{project_id}/world/factions/{faction_id}", summary="删除势力", status_code=204)
async def delete_faction(
    project_id: str, faction_id: str, svc: WorldService = Depends(_svc)
) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        original_len = len(sandbox.factions)
        sandbox.factions = [f for f in sandbox.factions if f.id != faction_id]
        if len(sandbox.factions) == original_len:
            raise HTTPException(status_code=404, detail=f"Faction {faction_id} not found")
        sandbox.relations = [
            rel for rel in sandbox.relations
            if rel.source_id != faction_id and rel.target_id != faction_id
        ]
        sync_territory_links(sandbox)
        await svc.save_sandbox(project_id, sandbox, db)


# ------------------------------------------------------------------ #
# Power Systems                                                        #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/world/power-systems", response_model=PowerSystem, summary="创建力量体系", status_code=201)
async def create_power_system(
    project_id: str,
    req: PowerSystemCreateRequest,
    svc: WorldService = Depends(_svc),
) -> PowerSystem:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        template_key = None
        for t in PowerSystemTemplateType:
            if t.value == req.template and t != PowerSystemTemplateType.CUSTOM:
                template_key = t
                break
        if template_key and template_key in POWER_SYSTEM_TEMPLATES:
            tpl = POWER_SYSTEM_TEMPLATES[template_key]
            ps = PowerSystem(
                name=req.name or tpl.name,
                template=template_key,
                levels=tpl.levels,
                rules=tpl.rules,
                resources=tpl.resources,
            )
        else:
            ps = PowerSystem(name=req.name, template=PowerSystemTemplateType.CUSTOM)
        sandbox.power_systems.append(ps)
        await svc.save_sandbox(project_id, sandbox, db)
    return ps.model_dump()


@router.get("/projects/{project_id}/world/power-systems/{ps_id}", response_model=PowerSystem, summary="获取力量体系详情")
async def get_power_system(
    project_id: str, ps_id: str, svc: WorldService = Depends(_svc)
) -> PowerSystem:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    power_system = next((p for p in sandbox.power_systems if p.id == ps_id), None)
    if power_system is None:
        raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
    return power_system.model_dump()


@router.put("/projects/{project_id}/world/power-systems/{ps_id}", response_model=PowerSystem, summary="更新力量体系")
async def update_power_system(
    project_id: str,
    ps_id: str,
    req: PowerSystem,
    svc: WorldService = Depends(_svc),
) -> PowerSystem:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        idx = next((i for i, p in enumerate(sandbox.power_systems) if p.id == ps_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
        if req.id and req.id != ps_id:
            raise HTTPException(status_code=400, detail="power system id in payload does not match path")
        payload = req.model_dump()
        payload["id"] = ps_id
        sandbox.power_systems[idx] = PowerSystem(**payload)
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.power_systems[idx].model_dump()


@router.delete("/projects/{project_id}/world/power-systems/{ps_id}", summary="删除力量体系", status_code=204)
async def delete_power_system(
    project_id: str, ps_id: str, svc: WorldService = Depends(_svc)
) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        original_len = len(sandbox.power_systems)
        sandbox.power_systems = [p for p in sandbox.power_systems if p.id != ps_id]
        if len(sandbox.power_systems) == original_len:
            raise HTTPException(status_code=404, detail=f"PowerSystem {ps_id} not found")
        await svc.save_sandbox(project_id, sandbox, db)


# ------------------------------------------------------------------ #
# Relations                                                            #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/world/relations", response_model=list[WorldRelation], summary="获取全部关系")
async def list_relations(
    project_id: str, svc: WorldService = Depends(_svc)
) -> list[WorldRelation]:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    return [r.model_dump() for r in sandbox.relations]


@router.get("/projects/{project_id}/world/relations/{relation_id}", response_model=WorldRelation, summary="获取关系详情")
async def get_relation(
    project_id: str, relation_id: str, svc: WorldService = Depends(_svc)
) -> WorldRelation:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    relation = next((r for r in sandbox.relations if r.id == relation_id), None)
    if relation is None:
        raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
    return relation.model_dump()


@router.post("/projects/{project_id}/world/relations", response_model=WorldRelation, summary="创建地区/势力关系", status_code=201)
async def create_relation(
    project_id: str,
    req: RelationCreateRequest,
    svc: WorldService = Depends(_svc),
) -> WorldRelation:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        valid_ids = collect_world_node_ids(sandbox)
        if req.source_id not in valid_ids:
            raise HTTPException(status_code=422, detail=f"source_id {req.source_id} does not exist")
        if req.target_id not in valid_ids:
            raise HTTPException(status_code=422, detail=f"target_id {req.target_id} does not exist")
        relation = WorldRelation(
            source_id=req.source_id,
            target_id=req.target_id,
            relation_type=req.relation_type,
            label=req.label,
            description=req.description,
        )
        sandbox.relations.append(relation)
        await svc.save_sandbox(project_id, sandbox, db)
    return relation.model_dump()


@router.put("/projects/{project_id}/world/relations/{relation_id}", response_model=WorldRelation, summary="更新关系")
async def update_relation(
    project_id: str,
    relation_id: str,
    req: RelationUpdateRequest,
    svc: WorldService = Depends(_svc),
) -> WorldRelation:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        idx = next((i for i, r in enumerate(sandbox.relations) if r.id == relation_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
        existing = sandbox.relations[idx].model_dump()
        for key, value in req.model_dump(exclude_none=True).items():
            existing[key] = value
        valid_ids = collect_world_node_ids(sandbox)
        if existing["source_id"] not in valid_ids:
            raise HTTPException(status_code=422, detail=f"source_id does not exist")
        if existing["target_id"] not in valid_ids:
            raise HTTPException(status_code=422, detail=f"target_id does not exist")
        sandbox.relations[idx] = WorldRelation(**existing)
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.relations[idx].model_dump()


@router.delete("/projects/{project_id}/world/relations/{relation_id}", summary="删除关系", status_code=204)
async def delete_relation(
    project_id: str, relation_id: str, svc: WorldService = Depends(_svc)
) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        original_len = len(sandbox.relations)
        sandbox.relations = [r for r in sandbox.relations if r.id != relation_id]
        if len(sandbox.relations) == original_len:
            raise HTTPException(status_code=404, detail=f"Relation {relation_id} not found")
        await svc.save_sandbox(project_id, sandbox, db)


# ------------------------------------------------------------------ #
# Timeline Events                                                      #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/world/timeline", response_model=list[TimelineSandboxEvent], summary="获取全部时间轴事件")
async def list_timeline_events(
    project_id: str, svc: WorldService = Depends(_svc)
) -> list[TimelineSandboxEvent]:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    return [e.model_dump() for e in sandbox.timeline_events]


@router.post("/projects/{project_id}/world/timeline", response_model=TimelineSandboxEvent, summary="创建时间轴事件", status_code=201)
async def create_timeline_event(
    project_id: str,
    req: TimelineEventCreateRequest,
    svc: WorldService = Depends(_svc),
) -> TimelineSandboxEvent:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        event = TimelineSandboxEvent(
            year=req.year,
            title=req.title,
            description=req.description,
            linked_entity_id=req.linked_entity_id,
            event_type=req.event_type,
        )
        sandbox.timeline_events.append(event)
        await svc.save_sandbox(project_id, sandbox, db)
    return event.model_dump()


@router.get("/projects/{project_id}/world/timeline/{event_id}", response_model=TimelineSandboxEvent, summary="获取时间轴事件详情")
async def get_timeline_event(
    project_id: str, event_id: str, svc: WorldService = Depends(_svc)
) -> TimelineSandboxEvent:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
    event = next((e for e in sandbox.timeline_events if e.id == event_id), None)
    if event is None:
        raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
    return event.model_dump()


@router.put("/projects/{project_id}/world/timeline/{event_id}", response_model=TimelineSandboxEvent, summary="更新时间轴事件")
async def update_timeline_event(
    project_id: str,
    event_id: str,
    req: TimelineEventUpdateRequest,
    svc: WorldService = Depends(_svc),
) -> TimelineSandboxEvent:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        idx = next((i for i, e in enumerate(sandbox.timeline_events) if e.id == event_id), None)
        if idx is None:
            raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
        existing = sandbox.timeline_events[idx].model_dump()
        for key, value in req.model_dump(exclude_none=True).items():
            existing[key] = value
        sandbox.timeline_events[idx] = TimelineSandboxEvent(**existing)
        await svc.save_sandbox(project_id, sandbox, db)
    return sandbox.timeline_events[idx].model_dump()


@router.delete("/projects/{project_id}/world/timeline/{event_id}", summary="删除时间轴事件", status_code=204)
async def delete_timeline_event(
    project_id: str, event_id: str, svc: WorldService = Depends(_svc)
) -> None:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        original_len = len(sandbox.timeline_events)
        sandbox.timeline_events = [e for e in sandbox.timeline_events if e.id != event_id]
        if len(sandbox.timeline_events) == original_len:
            raise HTTPException(status_code=404, detail=f"TimelineEvent {event_id} not found")
        await svc.save_sandbox(project_id, sandbox, db)


# ------------------------------------------------------------------ #
# 世界概览 / 工具端点                                                   #
# ------------------------------------------------------------------ #


@router.get("/projects/{project_id}/world/overview", response_model=WorldOverviewResponse, summary="世界概览")
async def get_world_overview(
    project_id: str, svc: WorldService = Depends(_svc)
) -> WorldOverviewResponse:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)

    connected_ids: set[str] = set()
    for rel in sandbox.relations:
        connected_ids.add(rel.source_id)
        connected_ids.add(rel.target_id)
    all_node_ids = {r.id for r in sandbox.regions} | {f.id for f in sandbox.factions}
    orphan_ids = all_node_ids - connected_ids
    orphan_nodes = []
    for oid in orphan_ids:
        r = next((r for r in sandbox.regions if r.id == oid), None)
        f = next((f for f in sandbox.factions if f.id == oid), None)
        if r:
            orphan_nodes.append({"id": oid, "name": r.name, "type": "region"})
        elif f:
            orphan_nodes.append({"id": oid, "name": f.name, "type": "faction"})

    completeness_hints: list[str] = []
    if not sandbox.regions:
        completeness_hints.append("尚未创建任何地区")
    if not sandbox.factions:
        completeness_hints.append("尚未创建任何势力")
    if not sandbox.relations and (sandbox.regions or sandbox.factions):
        completeness_hints.append("尚未建立任何关系")
    regions_with_faction = set()
    for f in sandbox.factions:
        regions_with_faction.update(f.territory_region_ids)
    regions_no_faction = [r.name for r in sandbox.regions if r.id not in regions_with_faction]
    if regions_no_faction:
        completeness_hints.append(f"以下地区无势力归属：{', '.join(regions_no_faction[:5])}")
    factions_no_territory = [f.name for f in sandbox.factions if not f.territory_region_ids]
    if factions_no_territory:
        completeness_hints.append(f"以下势力无领地：{', '.join(factions_no_territory[:5])}")
    factions_no_color = [f.name for f in sandbox.factions if not f.color]
    if factions_no_color:
        completeness_hints.append(f"以下势力未设置颜色：{', '.join(factions_no_color[:5])}")

    return WorldOverviewResponse(
        statistics={
            "regions": len(sandbox.regions),
            "factions": len(sandbox.factions),
            "relations": len(sandbox.relations),
            "power_systems": len(sandbox.power_systems),
            "timeline_events": len(sandbox.timeline_events),
        },
        orphan_nodes=orphan_nodes,
        completeness_hints=completeness_hints,
    )


@router.post("/projects/{project_id}/world/publish", summary="发布世界：沙盘 → 运行态 WorldState")
async def publish_world(
    project_id: str, svc: WorldService = Depends(_svc)
) -> dict[str, Any]:
    import sys
    from narrative_os.core.world_validator import WorldValidator
    from narrative_os.core.world_compiler import WorldCompiler
    from narrative_os.core.world_repository import WorldRepository

    _api = sys.modules.get("narrative_os.interface.api")
    _sandbox_fn = getattr(_api, "_get_sandbox", None) if _api else None
    _concept_fn = getattr(_api, "_get_concept", None) if _api else None

    async with AsyncSessionLocal() as db:
        if _sandbox_fn:
            sandbox = await _sandbox_fn(project_id, db)
        else:
            sandbox = await svc.get_sandbox(project_id, db)
        if _concept_fn:
            concept = await _concept_fn(project_id, db)
        else:
            concept = await svc.get_concept(project_id, db)

    validator = WorldValidator()
    validation_report = validator.validate(sandbox=sandbox, concept=concept)

    if not validation_report.is_valid:
        return {
            "status": "validation_failed",
            "errors": validation_report.errors,
            "warnings": validation_report.warnings,
            "suggestions": validation_report.suggestions,
            "publish_report": None,
        }

    compiler = WorldCompiler()
    world, publish_report = compiler.compile(concept=concept, sandbox=sandbox)

    world_version = f"v{int(_time.time())}"
    publish_report.world_version = world_version

    repo = WorldRepository()
    await repo.asave_runtime_world_state(project_id, world)

    return {
        "status": "published",
        "world_version": world_version,
        "warnings": publish_report.warnings + validation_report.warnings,
        "suggestions": validation_report.suggestions,
        "publish_report": {
            "factions_compiled": publish_report.factions_compiled,
            "regions_compiled": publish_report.regions_compiled,
            "power_systems_compiled": publish_report.power_systems_compiled,
            "rules_compiled": publish_report.rules_compiled,
            "timeline_events_compiled": publish_report.timeline_events_compiled,
            "relations_compiled": publish_report.relations_compiled,
        },
    }


@router.get("/projects/{project_id}/world/runtime-state", response_model=WorldState, summary="获取运行态 WorldState")
async def get_world_runtime_state(project_id: str) -> WorldState:
    from narrative_os.core.world_repository import WorldRepository
    repo = WorldRepository()
    world = await repo.aget_world_state(project_id)
    return world


@router.get("/projects/{project_id}/world/map-layout", response_model=WorldMapLayoutResponse, summary="地图布局坐标")
async def get_map_layout(
    project_id: str, svc: WorldService = Depends(_svc)
) -> WorldMapLayoutResponse:
    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)

    if not sandbox.regions:
        return WorldMapLayoutResponse(nodes=[], edges=[])

    spatial_types = {
        RelationType.ADJACENT, RelationType.BORDER,
        RelationType.CONNECTION, RelationType.TELEPORT,
    }
    region_ids = {r.id for r in sandbox.regions}
    edges = []
    adjacency: dict[str, set[str]] = {r.id: set() for r in sandbox.regions}
    for rel in sandbox.relations:
        rel_type = normalize_relation_type(rel.relation_type)
        if rel.source_id in region_ids and rel.target_id in region_ids:
            if rel_type in {t.value for t in spatial_types}:
                adjacency[rel.source_id].add(rel.target_id)
                adjacency[rel.target_id].add(rel.source_id)
                edges.append({
                    "source_id": rel.source_id,
                    "target_id": rel.target_id,
                    "relation_type": rel_type,
                })

    has_user_positions = any(r.x != 0.0 or r.y != 0.0 for r in sandbox.regions)
    placed: dict[str, dict[str, float]] = {}
    if has_user_positions:
        for r in sandbox.regions:
            placed[r.id] = {"x": r.x, "y": r.y}
    else:
        n = len(sandbox.regions)
        radius = max(150, n * 40)
        for i, r in enumerate(sandbox.regions):
            angle = 2 * math.pi * i / n
            placed[r.id] = {
                "x": round(radius * math.cos(angle), 2),
                "y": round(radius * math.sin(angle), 2),
            }

    region_faction_map: dict[str, list[str]] = {}
    for f in sandbox.factions:
        for rid in f.territory_region_ids:
            region_faction_map.setdefault(rid, []).append(f.id)

    nodes = [
        {
            "id": r.id,
            "name": r.name,
            "region_type": r.region_type,
            "x": placed.get(r.id, {"x": 0})["x"],
            "y": placed.get(r.id, {"y": 0})["y"],
            "faction_ids": region_faction_map.get(r.id, []),
        }
        for r in sandbox.regions
    ]
    return WorldMapLayoutResponse(
        nodes=[WorldMapNode.model_validate(node) for node in nodes],
        edges=[WorldMapEdge.model_validate(edge) for edge in edges],
    )


@router.get("/projects/{project_id}/world/power-templates", response_model=list[PowerTemplateSummary], summary="内置力量体系模板")
async def get_power_templates(project_id: str) -> list[PowerTemplateSummary]:
    return [PowerTemplateSummary.model_validate(item) for item in get_template_summary()]


@router.post("/projects/{project_id}/world/finalize", response_model=FinalizeWorldResponse, summary="完成世界设定，写入知识库")
async def finalize_world(
    project_id: str, svc: WorldService = Depends(_svc)
) -> FinalizeWorldResponse:
    from pathlib import Path as _Path

    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)
        concept = await svc.get_concept(project_id, db)

    first_ps = sandbox.power_systems[0] if sandbox.power_systems else None
    seed: dict[str, Any] = {
        "one_sentence": concept.one_sentence,
        "one_paragraph": concept.one_paragraph,
        "genre_tags": concept.genre_tags,
        "world": {
            "power_system": {
                "system_name": first_ps.name if first_ps else "",
                "tiers": [lv.name for lv in first_ps.levels] if first_ps else [],
                "rules": first_ps.rules if first_ps else [],
                "resources": first_ps.resources if first_ps else [],
            } if first_ps else None,
            "factions": [f.name for f in sandbox.factions],
            "key_locations": [r.name for r in sandbox.regions],
            "rules": sandbox.world_rules,
            "world_name": sandbox.world_name,
            "world_type": sandbox.world_type,
            "world_description": sandbox.world_description,
            "sandbox_raw": sandbox.model_dump(),
        },
        "plot_nodes": [],
        "characters": [],
    }

    kb_path = _Path(f".narrative_state/{project_id}/knowledge_base.json")
    kb_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any] = {}
    if kb_path.exists():
        try:
            existing = _json.loads(kb_path.read_text(encoding="utf-8"))
        except Exception:
            pass
    existing.update(seed)
    kb_path.write_text(_json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    return FinalizeWorldResponse(
        success=True,
        summary={
            "regions": len(sandbox.regions),
            "factions": len(sandbox.factions),
            "power_systems": len(sandbox.power_systems),
            "relations": len(sandbox.relations),
            "timeline_events": len(sandbox.timeline_events),
        },
    )


# ------------------------------------------------------------------ #
# AI 增强端点                                                           #
# ------------------------------------------------------------------ #


@router.post("/projects/{project_id}/world/ai/suggest-relations", response_model=AISuggestRelationsResponse, summary="AI 关系建议")
async def ai_suggest_relations(
    project_id: str,
    req: AISuggestRelationsRequest,
    svc: WorldService = Depends(_svc),
) -> AISuggestRelationsResponse:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter

    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)

    factions = [f for f in sandbox.factions if f.id in req.faction_ids]
    if not factions:
        return AISuggestRelationsResponse(suggestions=[])

    faction_descs = []
    for f in factions:
        territory_names = [r.name for r in sandbox.regions if r.id in f.territory_region_ids]
        faction_descs.append(
            f"ID:{f.id} 名称:{f.name} 范围:{f.scope} 阵营:{f.alignment} "
            f"领地:{','.join(territory_names) or '无'} 描述:{f.description}"
        )

    prompt = (
        "你是一位世界观设计助手。根据以下势力信息，建议它们之间可能存在的关系。\n\n"
        "势力列表：\n" + "\n".join(faction_descs) + "\n\n"
        "请以 JSON 数组格式返回建议，每项包含 source_id、target_id、"
        "relation_type（alliance/conflict/trade/rivalry/vassal）、reason。"
        "只返回 JSON 数组，不要其他文字。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.7,
        skill_name="world_ai_suggest_relations",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        suggestions = _json.loads(content)
        return AISuggestRelationsResponse(suggestions=suggestions)
    except Exception as exc:
        return AISuggestRelationsResponse(suggestions=[], error=str(exc))


@router.post("/projects/{project_id}/world/ai/expand", response_model=AIExpandResponse, summary="AI 上下文扩写")
async def ai_expand_field(
    project_id: str,
    req: AIExpandRequest,
    svc: WorldService = Depends(_svc),
) -> AIExpandResponse:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter

    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)

    entity = None
    if req.entity_type == "region":
        entity = next((r for r in sandbox.regions if r.id == req.entity_id), None)
    else:
        entity = next((f for f in sandbox.factions if f.id == req.entity_id), None)
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    neighbor_ids = set()
    for rel in sandbox.relations:
        if rel.source_id == req.entity_id:
            neighbor_ids.add(rel.target_id)
        elif rel.target_id == req.entity_id:
            neighbor_ids.add(rel.source_id)

    neighbors_desc = []
    for nid in neighbor_ids:
        r = next((x for x in sandbox.regions if x.id == nid), None)
        f = next((x for x in sandbox.factions if x.id == nid), None)
        if r:
            neighbors_desc.append(f"地区:{r.name}({r.region_type})")
        if f:
            neighbors_desc.append(f"势力:{f.name}({f.scope})")

    entity_dump = entity.model_dump() if hasattr(entity, "model_dump") else str(entity)
    prompt = (
        f"你是一位世界观设计助手。请根据以下实体信息和其关联实体，为字段「{req.field}」生成丰富的内容。\n\n"
        f"实体类型：{req.entity_type}\n"
        f"实体数据：{_json.dumps(entity_dump, ensure_ascii=False)}\n"
        f"关联实体：{', '.join(neighbors_desc) or '无'}\n"
        f"世界背景：{sandbox.world_name} ({sandbox.world_type})\n\n"
        f"请只返回「{req.field}」字段的内容文本，不要 JSON 包装，不要解释。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=256,
        temperature=0.7,
        skill_name="world_ai_expand",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        return AIExpandResponse(field=req.field, generated_content=resp.content.strip())
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 扩写失败: {exc}")


@router.post("/projects/{project_id}/world/ai/import-text", response_model=AIImportTextResponse, summary="文本转图谱（NER）")
async def ai_import_text(
    project_id: str, req: AIImportTextRequest
) -> AIImportTextResponse:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter

    prompt = (
        "你是一位世界观解析助手。请从下面的设定文本中提取地区、势力和它们之间的关系。\n\n"
        f"文本：\n{req.text}\n\n"
        "请以 JSON 格式返回，结构如下：\n"
        '{"regions": [{"name": "...", "region_type": "...", "notes": "..."}], '
        '"factions": [{"name": "...", "scope": "internal/external", "description": "..."}], '
        '"relations": [{"source_name": "...", "target_name": "...", '
        '"relation_type": "alliance/conflict/connection", "label": "..."}]}\n'
        "只返回 JSON，不要其他文字。"
    )

    llm_req = LLMRequest(
        task_type="world_building",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1024,
        temperature=0.3,
        skill_name="world_ai_import_text",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        parsed = _json.loads(content)
        return AIImportTextResponse(
            regions=parsed.get("regions", []),
            factions=parsed.get("factions", []),
            relations=parsed.get("relations", []),
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"AI 文本解析失败: {exc}")


@router.post("/projects/{project_id}/world/ai/consistency-check", response_model=AIConsistencyResponse, summary="AI 深度一致性校验")
async def ai_consistency_check(
    project_id: str, svc: WorldService = Depends(_svc)
) -> AIConsistencyResponse:
    from narrative_os.execution.llm_router import LLMRequest, LLMRouter

    async with AsyncSessionLocal() as db:
        sandbox = await svc.get_sandbox(project_id, db)

    summary_parts = [f"世界：{sandbox.world_name}（{sandbox.world_type}）"]
    for r in sandbox.regions[:20]:
        summary_parts.append(
            f"地区[{r.name}] 类型:{r.region_type} 阵营:{r.alignment} 备注:{r.notes[:100] if r.notes else ''}"
        )
    for f in sandbox.factions[:20]:
        summary_parts.append(
            f"势力[{f.name}] 范围:{f.scope} 阵营:{f.alignment} 描述:{f.description[:100] if f.description else ''}"
        )
    for ps in sandbox.power_systems[:10]:
        summary_parts.append(f"力量体系[{ps.name}] 等级:{[l.name for l in ps.levels]} 规则:{ps.rules[:3]}")
    for rel in sandbox.relations[:30]:
        summary_parts.append(f"关系: {rel.source_id}→{rel.target_id} 类型:{rel.relation_type}")

    world_summary = "\n".join(summary_parts)
    prompt = (
        "你是一位世界观一致性分析师。请分析以下世界设定中可能存在的逻辑冲突、不一致或不合理之处。\n\n"
        f"{world_summary}\n\n"
        "请以 JSON 数组格式返回问题列表，每项包含：\n"
        '{"severity": "warning/error", "node_ref": "涉及的实体名", "message": "问题描述"}\n'
        "如果没有发现问题，返回空数组 []。只返回 JSON 数组。"
    )

    llm_req = LLMRequest(
        task_type="consistency_check",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.3,
        skill_name="world_ai_consistency",
    )
    tmp_router = LLMRouter()
    try:
        resp = await tmp_router.call(llm_req)
        content = resp.content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        issues = _json.loads(content)
        return AIConsistencyResponse(issues=issues, passed=len(issues) == 0)
    except Exception as exc:
        return AIConsistencyResponse(issues=[], passed=True, error=str(exc))
