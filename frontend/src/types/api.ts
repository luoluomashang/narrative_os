// api.ts — TypeScript interfaces mirroring backend Pydantic models

export interface RunChapterRequest {
  chapter: number
  volume?: number
  target_summary: string
  word_count_target?: number
  strategy?: string
  previous_hook?: string
  existing_arc_summary?: string
  character_names?: string[]
  world_rules?: string[]
  constraints?: string[]
  project_id?: string
}

export interface RunChapterResponse {
  chapter: number
  volume: number
  text: string
  word_count: number
  change_ratio: number
  quality_score: number
  hook_score: number
  passed: boolean
  retry_count: number
}

export interface PlanChapterRequest {
  chapter: number
  volume?: number
  target_summary: string
  word_count_target?: number
  previous_hook?: string
  character_names?: string[]
  world_rules?: string[]
  constraints?: string[]
}

export interface PlanChapterResponse {
  chapter_outline: string
  planned_nodes: Record<string, unknown>[]
  dialogue_goals: string[]
  hook_suggestion: string
  hook_type: string
  tension_curve: number[]
}

export interface MetricsRequest {
  draft: Record<string, unknown>
  word_count_target?: number
}

export interface MetricsResponse {
  chapter: number
  overall_score: number
  avg_tension: number
  hook_score: number
  payoff_density: number
  pacing_score: number
  tension_trend: string
  consistency_score: number
  word_efficiency: number
  // 8D narrativespace quality dimensions
  qd_01_catharsis?: number
  qd_02_golden_finger?: number
  qd_03_rhythm?: number
  qd_04_dialogue?: number
  qd_05_char_consistency?: number
  qd_06_meaning?: number
  qd_07_hook?: number
  qd_08_readability?: number
}

export interface CostResponse {
  used_tokens: number
  budget_tokens: number
  usage_ratio: number
  by_skill: Record<string, number>
  by_agent: Record<string, number>
}

// Plot Graph
export interface PlotNode {
  id: string
  type: string
  status: string
  tension: number
  [key: string]: unknown
}

export interface PlotEdge {
  source: string
  target: string
  [key: string]: unknown
}

export interface PlotGraphData {
  nodes: PlotNode[]
  edges: PlotEdge[]
}

// Character
export interface CharacterSummary {
  name: string
  emotion: string
  health: number
  arc_stage: string
  faction: string
  is_alive: boolean
}

export interface CharacterDetail extends CharacterSummary {
  traits: string[]
  goal: string
  backstory: string
  relationships: Record<string, string>
  behavior_constraints: string[]
}

// Memory
export interface MemoryRecord {
  record_id: string
  content: string
  similarity?: number
  metadata: Record<string, unknown>
}

export interface MemorySnapshot {
  short_term: number
  mid_term: number
  long_term: number
  collections: Record<string, number>
  recent_anchors: MemoryRecord[]
}

export interface MemorySearchResult {
  results: MemoryRecord[]
  query: string
}

// LLM Provider Settings
export type LLMProviderName = 'openai' | 'anthropic' | 'ollama' | 'deepseek' | 'custom'

export interface LLMProviderStatus {
  available: boolean
  models: { small: string; medium: string; large: string }
}

export interface LLMCurrentConfig {
  openai_api_key: string
  anthropic_api_key: string
  ollama_base_url: string
  deepseek_api_key: string
  custom_llm_base_url: string
  custom_llm_api_key: string
  custom_llm_model_small: string
  custom_llm_model_medium: string
  custom_llm_model_large: string
}

export interface LLMSettingsResponse {
  providers: Record<LLMProviderName, LLMProviderStatus>
  current_config: LLMCurrentConfig
}

export interface LLMProviderConfig {
  openai_api_key?: string
  anthropic_api_key?: string
  ollama_base_url?: string
  deepseek_api_key?: string
  custom_llm_base_url?: string
  custom_llm_api_key?: string
  custom_llm_model_small?: string
  custom_llm_model_medium?: string
  custom_llm_model_large?: string
}

export interface LLMTestResult {
  success: boolean
  latency_ms: number
  model_used?: string
  error?: string
}

// Project Management
export interface ProjectListItem {
  project_id: string
  title: string
  chapter_count: number
  last_modified: string
}

export interface ProjectInitRequest {
  project_id: string
  title?: string
  genre?: string
  description?: string
}

export interface ProjectInitResponse {
  project_id: string
  created_at: string
  state_dir: string
}

export interface ProjectStatusResponse {
  project_id: string
  current_chapter: number
  current_volume: number
  total_word_count: number
  versions: string[]
}

export interface MetricsHistoryItem {
  chapter: number
  summary: string
  quality_score: number
  hook_score: number
  word_count: number
  timestamp: string
}

// Consistency Check
export interface ConsistencyIssue {
  dimension: string
  severity: string
  description: string
  suggestion: string
  source_rule: string
  confidence: number
}

export interface CheckChapterResponse {
  issues: ConsistencyIssue[]
  passed: boolean
}

// Humanize
export interface DiffEntry {
  type: string
  old: string
  new: string
}

export interface HumanizeResponse {
  original: string
  humanized: string
  changes_count: number
  diff: DiffEntry[]
}

// Cost Dashboard
export interface CostSummaryResponse {
  today_tokens: number
  total_tokens: number
  today_cost_usd: number
  by_agent: Record<string, number>
  by_skill: Record<string, number>
}

// Chapter management (B4)
export interface ChapterListItem {
  chapter: number
  summary: string
  word_count: number
  quality_score: number
  hook_score: number
  has_text: boolean
  timestamp: string
}

export interface ChapterTextResponse {
  chapter: number
  text: string
  word_count: number
  summary: string
  quality_score: number
  hook_score: number
  timestamp: string
}

export interface ExportNovelResponse {
  project_id: string
  title: string
  chapter_count: number
  total_words: number
  format: string
  content: string
}

// WorldBuilder
export interface WorldbuilderStartResponse {
  wb_session_id: string
  step: string
  prompt: string
  requires_confirmation: boolean
  skippable: boolean
  draft?: Record<string, unknown>
}

export interface WorldbuilderStepResponse {
  wb_session_id: string
  step: string
  done: boolean
  prompt: string | null
  requires_confirmation: boolean
  skippable: boolean
  draft?: Record<string, unknown>
  seed_data?: {
    characters: Array<{ name: string; role?: string }>
    world: Record<string, unknown>
    plot_nodes: Array<{ id: string; summary?: string }>
  } | null
}


export interface CostHistoryItem {
  date: string
  tokens: number
  cost_usd: number
  by_skill: Record<string, number>
  by_agent: Record<string, number>
}

// Plugins
export interface PluginInfo {
  id: string
  name: string
  enabled: boolean
  description: string
}

// Style
export interface StylePreset {
  id: string
  name: string
  genre: string
  tone: string
  sentence_length: string
}

// Consistency
export interface ConsistencyIssue {
  dimension: string
  severity: string
  confidence: number
  description: string
  suggestion: string
}

export interface ConsistencyReport {
  score: number
  issues: ConsistencyIssue[]
  summary: string
}
