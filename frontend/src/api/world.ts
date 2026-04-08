import client from './client'

export interface ConceptData {
  one_sentence: string
  one_paragraph: string
  genre_tags: string[]
  world_type: string
}

export interface RegionGeography {
  terrain: string
  climate: string
  special_features: string[]
  landmarks: string[]
}

export interface RegionRace {
  primary_race: string
  secondary_races: string[]
  is_mixed: boolean
  race_notes: string
}

export interface RegionCivilization {
  name: string
  belief_system: string
  culture_tags: string[]
  govt_type: string
}

export interface RegionPowerAccess {
  inherits_global: boolean
  custom_system_id: string | null
  power_notes: string
}

export interface Region {
  id: string
  name: string
  region_type: string
  x: number
  y: number
  geography: RegionGeography
  race: RegionRace
  civilization: RegionCivilization
  power_access: RegionPowerAccess
  faction_ids: string[]
  alignment: string
  tags: string[]
  notes: string
}

export interface Faction {
  id: string
  name: string
  scope: string
  description: string
  territory_region_ids: string[]
  alignment: string
  relation_map: Record<string, number>
  power_system_id: string | null
  notes: string
}

export interface PowerLevel {
  name: string
  description: string
  requirements: string
}

export interface PowerSystem {
  id: string
  name: string
  template: string
  levels: PowerLevel[]
  rules: string[]
  resources: string[]
  notes: string
}

export interface WorldRelation {
  id: string
  source_id: string
  target_id: string
  relation_type: string
  label: string
  description: string
}

export interface WorldSandboxData {
  world_name: string
  world_type: string
  world_description: string
  regions: Region[]
  factions: Faction[]
  power_systems: PowerSystem[]
  relations: WorldRelation[]
  world_rules: string[]
}

export interface PowerTemplateSummary {
  template: string
  name: string
  preview_levels: string[]
  level_count: number
}

// --- 故事概念 ---
export const concept = {
  get: (projectId: string) =>
    client.get<ConceptData>(`/projects/${projectId}/concept`),
  update: (projectId: string, data: Partial<ConceptData>) =>
    client.put<ConceptData>(`/projects/${projectId}/concept`, data),
}

// --- 世界观沙盘 ---
export const world = {
  get: (projectId: string) =>
    client.get<WorldSandboxData>(`/projects/${projectId}/world`),
  updateMeta: (projectId: string, data: { world_name?: string; world_type?: string; world_description?: string }) =>
    client.put<WorldSandboxData>(`/projects/${projectId}/world/meta`, data),

  // Regions
  createRegion: (projectId: string, data: { name: string; region_type?: string; x?: number; y?: number }) =>
    client.post<Region>(`/projects/${projectId}/world/regions`, data),
  getRegion: (projectId: string, regionId: string) =>
    client.get<Region>(`/projects/${projectId}/world/regions/${regionId}`),
  updateRegion: (projectId: string, regionId: string, data: Partial<Region>) =>
    client.put<Region>(`/projects/${projectId}/world/regions/${regionId}`, data),
  deleteRegion: (projectId: string, regionId: string) =>
    client.delete(`/projects/${projectId}/world/regions/${regionId}`),

  // Factions
  createFaction: (projectId: string, data: { name: string; scope?: string; description?: string }) =>
    client.post<Faction>(`/projects/${projectId}/world/factions`, data),
  getFaction: (projectId: string, factionId: string) =>
    client.get<Faction>(`/projects/${projectId}/world/factions/${factionId}`),
  updateFaction: (projectId: string, factionId: string, data: Partial<Faction>) =>
    client.put<Faction>(`/projects/${projectId}/world/factions/${factionId}`, data),
  deleteFaction: (projectId: string, factionId: string) =>
    client.delete(`/projects/${projectId}/world/factions/${factionId}`),

  // Power Systems
  createPowerSystem: (projectId: string, data: { name: string; template?: string }) =>
    client.post<PowerSystem>(`/projects/${projectId}/world/power-systems`, data),
  getPowerSystem: (projectId: string, psId: string) =>
    client.get<PowerSystem>(`/projects/${projectId}/world/power-systems/${psId}`),
  updatePowerSystem: (projectId: string, psId: string, data: Partial<PowerSystem>) =>
    client.put<PowerSystem>(`/projects/${projectId}/world/power-systems/${psId}`, data),
  deletePowerSystem: (projectId: string, psId: string) =>
    client.delete(`/projects/${projectId}/world/power-systems/${psId}`),

  // Relations
  listRelations: (projectId: string) =>
    client.get<WorldRelation[]>(`/projects/${projectId}/world/relations`),
  getRelation: (projectId: string, relationId: string) =>
    client.get<WorldRelation>(`/projects/${projectId}/world/relations/${relationId}`),
  createRelation: (projectId: string, data: { source_id: string; target_id: string; relation_type?: string; label?: string; description?: string }) =>
    client.post<WorldRelation>(`/projects/${projectId}/world/relations`, data),
  updateRelation: (projectId: string, relationId: string, data: Partial<WorldRelation>) =>
    client.put<WorldRelation>(`/projects/${projectId}/world/relations/${relationId}`, data),
  deleteRelation: (projectId: string, relationId: string) =>
    client.delete(`/projects/${projectId}/world/relations/${relationId}`),

  // Tools
  powerTemplates: (projectId: string) =>
    client.get<PowerTemplateSummary[]>(`/projects/${projectId}/world/power-templates`),
  finalize: (projectId: string) =>
    client.post<{ success: boolean; summary: Record<string, number> }>(`/projects/${projectId}/world/finalize`),

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
}
