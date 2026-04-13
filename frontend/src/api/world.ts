import type { AxiosResponse } from 'axios'

import client from './client'
import type {
  ConceptData as ApiConceptData,
  Faction as ApiFaction,
  PowerSystem as ApiPowerSystem,
  PowerTemplateSummary as ApiPowerTemplateSummary,
  Region as ApiRegion,
  RegionCivilization as ApiRegionCivilization,
  RegionGeography as ApiRegionGeography,
  RegionPowerAccess as ApiRegionPowerAccess,
  RegionRace as ApiRegionRace,
  TimelineSandboxEvent as ApiTimelineSandboxEvent,
  WorldRelation as ApiWorldRelation,
  WorldSandboxData as ApiWorldSandboxData,
} from '../types/api.gen'

export type ConceptData = Omit<ApiConceptData, 'genre_tags'> & {
  genre_tags: NonNullable<ApiConceptData['genre_tags']>
}
export type RegionGeography = Omit<ApiRegionGeography, 'special_features' | 'landmarks'> & {
  special_features: NonNullable<ApiRegionGeography['special_features']>
  landmarks: NonNullable<ApiRegionGeography['landmarks']>
}
export type RegionRace = Omit<ApiRegionRace, 'secondary_races'> & {
  secondary_races: NonNullable<ApiRegionRace['secondary_races']>
}
export type RegionCivilization = Omit<ApiRegionCivilization, 'culture_tags'> & {
  culture_tags: NonNullable<ApiRegionCivilization['culture_tags']>
}
export type RegionPowerAccess = Omit<ApiRegionPowerAccess, 'custom_system_id'> & {
  custom_system_id: Exclude<ApiRegionPowerAccess['custom_system_id'], undefined>
}
export type Region = Omit<ApiRegion, 'id' | 'geography' | 'race' | 'civilization' | 'power_access' | 'faction_ids' | 'tags'> & {
  id: string
  geography: RegionGeography
  race: RegionRace
  civilization: RegionCivilization
  power_access: RegionPowerAccess
  faction_ids: NonNullable<ApiRegion['faction_ids']>
  tags: NonNullable<ApiRegion['tags']>
}
export type Faction = Omit<ApiFaction, 'id' | 'territory_region_ids' | 'relation_map' | 'power_system_id'> & {
  id: string
  territory_region_ids: NonNullable<ApiFaction['territory_region_ids']>
  relation_map: NonNullable<ApiFaction['relation_map']>
  power_system_id: Exclude<ApiFaction['power_system_id'], undefined>
}
export type PowerSystem = Omit<ApiPowerSystem, 'id' | 'levels' | 'rules' | 'resources'> & {
  id: string
  levels: NonNullable<ApiPowerSystem['levels']>
  rules: NonNullable<ApiPowerSystem['rules']>
  resources: NonNullable<ApiPowerSystem['resources']>
}
export type PowerTemplateSummary = Omit<ApiPowerTemplateSummary, 'preview_levels'> & {
  preview_levels: NonNullable<ApiPowerTemplateSummary['preview_levels']>
}
export type WorldRelation = Omit<ApiWorldRelation, 'id'> & {
  id: string
}
export type TimelineSandboxEvent = Omit<ApiTimelineSandboxEvent, 'id' | 'linked_entity_id'> & {
  id: string
  linked_entity_id: Exclude<ApiTimelineSandboxEvent['linked_entity_id'], undefined>
}
export type WorldSandboxData = Omit<ApiWorldSandboxData, 'regions' | 'factions' | 'power_systems' | 'world_rules' | 'relations' | 'timeline_events'> & {
  regions: Region[]
  factions: Faction[]
  power_systems: PowerSystem[]
  world_rules: NonNullable<ApiWorldSandboxData['world_rules']>
  relations: WorldRelation[]
  timeline_events: TimelineSandboxEvent[]
}

const requireId = (value: string | undefined, entity: string): string => {
  if (value) {
    return value
  }
  throw new Error(`${entity} is missing required id`)
}

const mapResponse = <TIn, TOut>(
  request: Promise<AxiosResponse<TIn>>,
  normalize: (data: TIn) => TOut,
): Promise<AxiosResponse<TOut>> =>
  request.then((response) => ({
    ...response,
    data: normalize(response.data),
  }) as AxiosResponse<TOut>)

const normalizeConceptData = (data: ApiConceptData): ConceptData => ({
  ...data,
  genre_tags: data.genre_tags ?? [],
})

const normalizeRegionGeography = (data?: ApiRegionGeography): RegionGeography => ({
  terrain: data?.terrain ?? '',
  climate: data?.climate ?? '',
  special_features: data?.special_features ?? [],
  landmarks: data?.landmarks ?? [],
})

const normalizeRegionRace = (data?: ApiRegionRace): RegionRace => ({
  primary_race: data?.primary_race ?? '',
  secondary_races: data?.secondary_races ?? [],
  is_mixed: data?.is_mixed ?? false,
  race_notes: data?.race_notes ?? '',
})

const normalizeRegionCivilization = (data?: ApiRegionCivilization): RegionCivilization => ({
  name: data?.name ?? '',
  belief_system: data?.belief_system ?? '',
  culture_tags: data?.culture_tags ?? [],
  govt_type: data?.govt_type ?? '',
})

const normalizeRegionPowerAccess = (data?: ApiRegionPowerAccess): RegionPowerAccess => ({
  inherits_global: data?.inherits_global ?? true,
  custom_system_id: data?.custom_system_id ?? null,
  power_notes: data?.power_notes ?? '',
})

const normalizeRegion = (data: ApiRegion): Region => ({
  ...data,
  id: requireId(data.id, 'Region'),
  geography: normalizeRegionGeography(data.geography),
  race: normalizeRegionRace(data.race),
  civilization: normalizeRegionCivilization(data.civilization),
  power_access: normalizeRegionPowerAccess(data.power_access),
  faction_ids: data.faction_ids ?? [],
  tags: data.tags ?? [],
})

const normalizeFaction = (data: ApiFaction): Faction => ({
  ...data,
  id: requireId(data.id, 'Faction'),
  territory_region_ids: data.territory_region_ids ?? [],
  relation_map: data.relation_map ?? {},
  power_system_id: data.power_system_id ?? null,
})

const normalizePowerSystem = (data: ApiPowerSystem): PowerSystem => ({
  ...data,
  id: requireId(data.id, 'PowerSystem'),
  levels: data.levels ?? [],
  rules: data.rules ?? [],
  resources: data.resources ?? [],
})

const normalizePowerTemplateSummary = (data: ApiPowerTemplateSummary): PowerTemplateSummary => ({
  ...data,
  preview_levels: data.preview_levels ?? [],
})

const normalizeWorldRelation = (data: ApiWorldRelation): WorldRelation => ({
  ...data,
  id: requireId(data.id, 'WorldRelation'),
})

const normalizeTimelineSandboxEvent = (data: ApiTimelineSandboxEvent): TimelineSandboxEvent => ({
  ...data,
  id: requireId(data.id, 'TimelineSandboxEvent'),
  linked_entity_id: data.linked_entity_id ?? null,
})

const normalizeWorldSandboxData = (data: ApiWorldSandboxData): WorldSandboxData => ({
  ...data,
  regions: (data.regions ?? []).map(normalizeRegion),
  factions: (data.factions ?? []).map(normalizeFaction),
  power_systems: (data.power_systems ?? []).map(normalizePowerSystem),
  world_rules: data.world_rules ?? [],
  relations: (data.relations ?? []).map(normalizeWorldRelation),
  timeline_events: (data.timeline_events ?? []).map(normalizeTimelineSandboxEvent),
})

export interface WorldPublishResponse {
  status: 'published' | 'validation_failed'
  world_version?: string
  warnings: string[]
  suggestions: string[]
  errors?: string[]
  runtime_diff?: WorldRuntimeDiff | null
  publish_report?: {
    factions_compiled: number
    regions_compiled: number
    power_systems_compiled: number
    rules_compiled: number
    timeline_events_compiled: number
    relations_compiled: number
  } | null
}

export interface WorldRuntimeDiffEntry {
  target_id: string
  target_name: string
  change_type: string
  before: string
  after: string
  effect: string
  note: string
}

export interface WorldRuntimeDiffSection {
  key: string
  label: string
  items: WorldRuntimeDiffEntry[]
}

export interface WorldRuntimeDiff {
  sections: WorldRuntimeDiffSection[]
  auto_fix_notes: string[]
}

export interface WorldPublishPreviewResponse {
  status: 'ready' | 'validation_failed'
  warnings: string[]
  suggestions: string[]
  errors?: string[]
  runtime_diff?: WorldRuntimeDiff | null
  publish_report?: WorldPublishResponse['publish_report']
}

// --- 故事概念 ---
export const concept = {
  get: (projectId: string) =>
    mapResponse(client.get<ApiConceptData>(`/projects/${projectId}/concept`), normalizeConceptData),
  update: (projectId: string, data: Partial<ConceptData>) =>
    mapResponse(client.put<ApiConceptData>(`/projects/${projectId}/concept`, data), normalizeConceptData),
}

// --- 世界观沙盘 ---
export const world = {
  get: (projectId: string) =>
    mapResponse(client.get<ApiWorldSandboxData>(`/projects/${projectId}/world`), normalizeWorldSandboxData),
  updateMeta: (projectId: string, data: { world_name?: string; world_type?: string; world_description?: string }) =>
    mapResponse(client.put<ApiWorldSandboxData>(`/projects/${projectId}/world/meta`, data), normalizeWorldSandboxData),

  // Regions
  createRegion: (projectId: string, data: { name: string; region_type?: string; x?: number; y?: number }) =>
    mapResponse(client.post<ApiRegion>(`/projects/${projectId}/world/regions`, data), normalizeRegion),
  getRegion: (projectId: string, regionId: string) =>
    mapResponse(client.get<ApiRegion>(`/projects/${projectId}/world/regions/${regionId}`), normalizeRegion),
  updateRegion: (projectId: string, regionId: string, data: Partial<Region>) =>
    mapResponse(client.put<ApiRegion>(`/projects/${projectId}/world/regions/${regionId}`, data), normalizeRegion),
  deleteRegion: (projectId: string, regionId: string) =>
    client.delete(`/projects/${projectId}/world/regions/${regionId}`),

  // Factions
  createFaction: (projectId: string, data: { name: string; scope?: string; description?: string }) =>
    mapResponse(client.post<ApiFaction>(`/projects/${projectId}/world/factions`, data), normalizeFaction),
  getFaction: (projectId: string, factionId: string) =>
    mapResponse(client.get<ApiFaction>(`/projects/${projectId}/world/factions/${factionId}`), normalizeFaction),
  updateFaction: (projectId: string, factionId: string, data: Partial<Faction>) =>
    mapResponse(client.put<ApiFaction>(`/projects/${projectId}/world/factions/${factionId}`, data), normalizeFaction),
  deleteFaction: (projectId: string, factionId: string) =>
    client.delete(`/projects/${projectId}/world/factions/${factionId}`),

  // Power Systems
  createPowerSystem: (projectId: string, data: { name: string; template?: string }) =>
    mapResponse(client.post<ApiPowerSystem>(`/projects/${projectId}/world/power-systems`, data), normalizePowerSystem),
  getPowerSystem: (projectId: string, psId: string) =>
    mapResponse(client.get<ApiPowerSystem>(`/projects/${projectId}/world/power-systems/${psId}`), normalizePowerSystem),
  updatePowerSystem: (projectId: string, psId: string, data: Partial<PowerSystem>) =>
    mapResponse(client.put<ApiPowerSystem>(`/projects/${projectId}/world/power-systems/${psId}`, data), normalizePowerSystem),
  deletePowerSystem: (projectId: string, psId: string) =>
    client.delete(`/projects/${projectId}/world/power-systems/${psId}`),

  // Relations
  listRelations: (projectId: string) =>
    mapResponse(client.get<ApiWorldRelation[]>(`/projects/${projectId}/world/relations`), (data) => data.map(normalizeWorldRelation)),
  getRelation: (projectId: string, relationId: string) =>
    mapResponse(client.get<ApiWorldRelation>(`/projects/${projectId}/world/relations/${relationId}`), normalizeWorldRelation),
  createRelation: (projectId: string, data: { source_id: string; target_id: string; relation_type?: string; label?: string; description?: string }) =>
    mapResponse(client.post<ApiWorldRelation>(`/projects/${projectId}/world/relations`, data), normalizeWorldRelation),
  updateRelation: (projectId: string, relationId: string, data: Partial<WorldRelation>) =>
    mapResponse(client.put<ApiWorldRelation>(`/projects/${projectId}/world/relations/${relationId}`, data), normalizeWorldRelation),
  deleteRelation: (projectId: string, relationId: string) =>
    client.delete(`/projects/${projectId}/world/relations/${relationId}`),

  // Tools
  powerTemplates: (projectId: string) =>
    mapResponse(client.get<ApiPowerTemplateSummary[]>(`/projects/${projectId}/world/power-templates`), (data) => data.map(normalizePowerTemplateSummary)),
  finalize: (projectId: string) =>
    client.post<{ success: boolean; summary: Record<string, number> }>(`/projects/${projectId}/world/finalize`),
  previewPublish: (projectId: string) =>
    client.post<WorldPublishPreviewResponse>(`/projects/${projectId}/world/publish-preview`),
  publish: (projectId: string) =>
    client.post<WorldPublishResponse>(`/projects/${projectId}/world/publish`),

  // AI 增强
  suggestRelations: (projectId: string, factionIds: string[]) =>
    client.post<{ suggestions: Array<{ source_id: string; target_id: string; relation_type: string; reason: string }> }>(
      `/projects/${projectId}/world/ai/suggest-relations`, { faction_ids: factionIds }
    ),
  expandEntityField: (projectId: string, entityType: 'region' | 'faction', entityId: string, field: string) =>
    client.post<{ field: string; generated_content: string }>(
      `/projects/${projectId}/world/ai/expand`, { entity_type: entityType, entity_id: entityId, field }
    ),
  importText: (projectId: string, text: string) =>
    client.post<{ regions: Array<{ name: string; region_type?: string; notes?: string }>; factions: Array<{ name: string; scope?: string; description?: string }>; relations: Array<{ source_name: string; target_name: string; relation_type: string; label?: string }> }>(
      `/projects/${projectId}/world/ai/import-text`, { text }
    ),
  aiConsistencyCheck: (projectId: string) =>
    client.post<{ issues: Array<{ severity: string; node_ref: string; message: string }> }>(
      `/projects/${projectId}/world/ai/consistency-check`
    ),

  // Timeline
  listTimeline: (projectId: string) =>
    mapResponse(client.get<ApiTimelineSandboxEvent[]>(`/projects/${projectId}/world/timeline`), (data) => data.map(normalizeTimelineSandboxEvent)),
  createTimelineEvent: (projectId: string, data: { year?: string; title: string; description?: string; linked_entity_id?: string | null; event_type?: string }) =>
    mapResponse(client.post<ApiTimelineSandboxEvent>(`/projects/${projectId}/world/timeline`, data), normalizeTimelineSandboxEvent),
  getTimelineEvent: (projectId: string, eventId: string) =>
    mapResponse(client.get<ApiTimelineSandboxEvent>(`/projects/${projectId}/world/timeline/${eventId}`), normalizeTimelineSandboxEvent),
  updateTimelineEvent: (projectId: string, eventId: string, data: Partial<TimelineSandboxEvent>) =>
    mapResponse(client.put<ApiTimelineSandboxEvent>(`/projects/${projectId}/world/timeline/${eventId}`, data), normalizeTimelineSandboxEvent),
  deleteTimelineEvent: (projectId: string, eventId: string) =>
    client.delete(`/projects/${projectId}/world/timeline/${eventId}`),

  // Overview & Layout
  overview: (projectId: string) =>
    client.get<{ statistics: Record<string, number>; orphan_nodes: Array<{ id: string; name: string; type: string }>; completeness_hints: string[] }>(
      `/projects/${projectId}/world/overview`
    ),
  mapLayout: (projectId: string) =>
    client.get<{ nodes: Array<{ id: string; name: string; region_type: string; x: number; y: number; faction_ids: string[] }>; edges: Array<{ source_id: string; target_id: string; relation_type: string }> }>(
      `/projects/${projectId}/world/map-layout`
    ),
}
