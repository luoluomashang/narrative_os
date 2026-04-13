"""schemas/world.py — 世界观沙盘请求/响应模型。"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from narrative_os.core.world import WorldState
from narrative_os.core.world_sandbox import (
    ConceptData,
    Faction,
    PowerLevel,
    PowerSystem,
    Region,
    RegionCivilization,
    RegionGeography,
    RegionPowerAccess,
    RegionRace,
    TimelineSandboxEvent,
    WorldType,
    WorldRelation,
    WorldSandboxData,
)


class ConceptUpdateRequest(BaseModel):
    one_sentence: str = ""
    one_paragraph: str = ""
    genre_tags: list[str] = Field(default_factory=list)
    world_type: WorldType = WorldType.CONTINENTAL


class WorldMetaUpdateRequest(BaseModel):
    world_name: Optional[str] = None
    world_type: Optional[WorldType] = None
    world_description: Optional[str] = None


class RegionCreateRequest(BaseModel):
    name: str
    region_type: str = ""
    x: float = 100.0
    y: float = 100.0
    geography: Optional[dict] = None
    race: Optional[dict] = None
    civilization: Optional[dict] = None
    power_access: Optional[dict] = None
    faction_ids: list[str] = Field(default_factory=list)
    alignment: str = "true_neutral"
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class FactionCreateRequest(BaseModel):
    name: str
    scope: str = "internal"
    description: str = ""
    territory_region_ids: list[str] = Field(default_factory=list)
    alignment: str = "true_neutral"
    color: Optional[str] = None
    power_system_id: Optional[str] = None
    notes: str = ""


class PowerSystemCreateRequest(BaseModel):
    name: str
    template: str = "custom"


class RelationCreateRequest(BaseModel):
    source_id: str
    target_id: str
    relation_type: str = "connection"
    label: str = ""
    description: str = ""


class RelationUpdateRequest(BaseModel):
    relation_type: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None


class TimelineEventCreateRequest(BaseModel):
    year: str = ""
    title: str
    description: str = ""
    linked_entity_id: Optional[str] = None
    event_type: str = "general"


class TimelineEventUpdateRequest(BaseModel):
    year: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    linked_entity_id: Optional[str] = None
    event_type: Optional[str] = None


class PowerTemplateSummary(BaseModel):
    template: str
    name: str
    preview_levels: list[str] = Field(default_factory=list)
    level_count: int = 0


class FinalizeWorldSummary(BaseModel):
    regions: int = 0
    factions: int = 0
    power_systems: int = 0
    relations: int = 0
    timeline_events: int = 0


class FinalizeWorldResponse(BaseModel):
    success: bool = True
    summary: FinalizeWorldSummary


class AISuggestRelationsRequest(BaseModel):
    faction_ids: list[str] = Field(default_factory=list)


class SuggestedRelation(BaseModel):
    source_id: str
    target_id: str
    relation_type: str
    reason: str = ""


class AISuggestRelationsResponse(BaseModel):
    suggestions: list[SuggestedRelation] = Field(default_factory=list)
    error: str | None = None


class AIExpandRequest(BaseModel):
    entity_type: Literal["region", "faction"]
    entity_id: str
    field: str


class AIExpandResponse(BaseModel):
    field: str
    generated_content: str


class AIImportTextRequest(BaseModel):
    text: str = Field(..., max_length=4000)


class ImportedRegion(BaseModel):
    name: str
    region_type: str | None = None
    notes: str | None = None


class ImportedFaction(BaseModel):
    name: str
    scope: str | None = None
    description: str | None = None


class ImportedRelation(BaseModel):
    source_name: str
    target_name: str
    relation_type: str
    label: str | None = None


class AIImportTextResponse(BaseModel):
    regions: list[ImportedRegion] = Field(default_factory=list)
    factions: list[ImportedFaction] = Field(default_factory=list)
    relations: list[ImportedRelation] = Field(default_factory=list)


class WorldConsistencyIssue(BaseModel):
    severity: str
    node_ref: str
    message: str


class AIConsistencyResponse(BaseModel):
    issues: list[WorldConsistencyIssue] = Field(default_factory=list)
    passed: bool = True
    error: str | None = None


class OrphanNodeSummary(BaseModel):
    id: str
    name: str
    type: str


class WorldOverviewResponse(BaseModel):
    statistics: dict[str, int] = Field(default_factory=dict)
    orphan_nodes: list[OrphanNodeSummary] = Field(default_factory=list)
    completeness_hints: list[str] = Field(default_factory=list)


class WorldMapNode(BaseModel):
    id: str
    name: str
    region_type: str
    x: float
    y: float
    faction_ids: list[str] = Field(default_factory=list)


class WorldMapEdge(BaseModel):
    source_id: str
    target_id: str
    relation_type: str


class WorldMapLayoutResponse(BaseModel):
    nodes: list[WorldMapNode] = Field(default_factory=list)
    edges: list[WorldMapEdge] = Field(default_factory=list)


class WorldPublishReport(BaseModel):
    factions_compiled: int = 0
    regions_compiled: int = 0
    power_systems_compiled: int = 0
    rules_compiled: int = 0
    timeline_events_compiled: int = 0
    relations_compiled: int = 0


class WorldRuntimeDiffEntry(BaseModel):
    target_id: str = ""
    target_name: str = ""
    change_type: str = ""
    before: str = ""
    after: str = ""
    effect: str = ""
    note: str = ""


class WorldRuntimeDiffSection(BaseModel):
    key: str
    label: str
    items: list[WorldRuntimeDiffEntry] = Field(default_factory=list)


class WorldRuntimeDiff(BaseModel):
    sections: list[WorldRuntimeDiffSection] = Field(default_factory=list)
    auto_fix_notes: list[str] = Field(default_factory=list)


class WorldPublishPreviewResponse(BaseModel):
    status: Literal["ready", "validation_failed"]
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    publish_report: WorldPublishReport | None = None
    runtime_diff: WorldRuntimeDiff | None = None


class WorldPublishResponse(BaseModel):
    status: Literal["published", "validation_failed"]
    world_version: str | None = None
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    publish_report: WorldPublishReport | None = None
    runtime_diff: WorldRuntimeDiff | None = None
