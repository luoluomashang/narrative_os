import client from './client'

export type BenchmarkSceneType = 'battle' | 'emotion' | 'reveal' | 'daily' | 'ensemble' | 'general'
export type BenchmarkJobType = 'project_benchmark' | 'author_distillation'
export type BenchmarkSkillApplyMode = 'guide' | 'hybrid' | 'strict'

export interface BenchmarkSourceInput {
  title: string
  file_name?: string
  text: string
  author_name?: string | null
  corpus_group?: string
  chapter_sep?: string | null
}

export interface BenchmarkTrait {
  dimension: string
  name: string
  summary: string
  value?: number
}

export interface BenchmarkProfile {
  profile_id: string
  project_id: string
  profile_type: 'project_benchmark' | 'author_distillation'
  profile_name: string
  source_ids: string[]
  stable_traits: BenchmarkTrait[]
  conditional_traits: BenchmarkTrait[]
  anti_traits: BenchmarkTrait[]
  scene_anchors: Record<string, Array<Record<string, unknown>>>
  humanness_baseline: Record<string, unknown>
  status: 'draft' | 'active'
  snippet_count: number
  created_at: string
  activated_at?: string | null
}

export interface AuthorSkillProfile {
  skill_id: string
  origin_project_id: string
  run_id?: string | null
  skill_name: string
  author_name: string
  source_ids: string[]
  stable_rules: BenchmarkTrait[]
  conditional_rules: BenchmarkTrait[]
  anti_rules: BenchmarkTrait[]
  dialogue_rules: BenchmarkTrait[]
  scene_patterns: Record<string, Array<Record<string, unknown>>>
  chapter_hook_patterns: Array<Record<string, unknown>>
  humanness_baseline: Record<string, unknown>
  confidence_map: Record<string, unknown>
  status: 'draft' | 'active'
  created_at: string
  applied: boolean
  application_mode?: BenchmarkSkillApplyMode | null
}

export interface BenchmarkSkillListResponse {
  items: AuthorSkillProfile[]
  active_skill_id?: string | null
  active_mode?: BenchmarkSkillApplyMode | null
}

export interface BenchmarkSkillApplyResponse {
  skill: AuthorSkillProfile
  mode: BenchmarkSkillApplyMode
  message: string
}

export interface BenchmarkSnippet {
  snippet_id: string
  profile_id: string
  project_id: string
  source_id: string
  scene_type: BenchmarkSceneType
  chapter?: number | null
  offset_start: number
  offset_end: number
  char_count: number
  anchor_score: number
  purity_score: number
  distinctiveness_score: number
  source_hit_verified: boolean
  text: string
}

export interface BenchmarkSource {
  source_id: string
  project_id: string
  corpus_group: string
  title: string
  author_name?: string | null
  file_name: string
  sha256: string
  char_count: number
  chapter_sep?: string | null
  source_type: 'project_reference' | 'author_reference'
  created_at: string
}

export interface BenchmarkJobCreateRequest {
  job_type: BenchmarkJobType
  mode: 'single_work' | 'multi_work' | 'scene'
  source_ids?: string[]
  sources: BenchmarkSourceInput[]
  chapter_sep?: string | null
  extract_snippets?: boolean
  target_platform?: string | null
  author_name?: string | null
  corpus_group?: string | null
}

export interface BenchmarkJobCreateResponse {
  run_id: string
  status: string
  profile: BenchmarkProfile
  author_skill?: AuthorSkillProfile | null
  source_ids: string[]
  snippet_count: number
  message: string
}

export interface BenchmarkJobDetailResponse {
  run: {
    run_id: string
    run_type: string
    status: string
    steps: Array<{
      step_id: string
      step_index: number
      agent_name: string
      status: string
      artifact?: {
        artifact_type: string
        output_content: string
      } | null
    }>
  }
  profile?: BenchmarkProfile | null
  author_skill?: AuthorSkillProfile | null
  sources: BenchmarkSource[]
  snippets: BenchmarkSnippet[]
  message: string
}

export interface BenchmarkSnippetListResponse {
  profile?: BenchmarkProfile | null
  items: BenchmarkSnippet[]
}

export const benchmark = {
  createJob: (id: string, data: BenchmarkJobCreateRequest) =>
    client.post<BenchmarkJobCreateResponse>(`/projects/${id}/benchmark/jobs`, data),
  getJob: (id: string, runId: string) =>
    client.get<BenchmarkJobDetailResponse>(`/projects/${id}/benchmark/jobs/${runId}`),
  getProfile: (id: string) =>
    client.get<BenchmarkProfile | null>(`/projects/${id}/benchmark/profile`),
  listSnippets: (id: string, params?: { profile_id?: string; scene_type?: string; limit?: number }) =>
    client.get<BenchmarkSnippetListResponse>(`/projects/${id}/benchmark/snippets`, { params }),
  activateProfile: (id: string, profileId: string) =>
    client.post<BenchmarkProfile>(`/projects/${id}/benchmark/profile/activate`, { profile_id: profileId }),
  listSkills: (id: string, params?: { author_name?: string; limit?: number }) =>
    client.get<BenchmarkSkillListResponse>(`/projects/${id}/benchmark/skills`, { params }),
  getSkill: (id: string, skillId: string) =>
    client.get<AuthorSkillProfile>(`/projects/${id}/benchmark/skills/${skillId}`),
  applySkill: (id: string, skillId: string, mode: BenchmarkSkillApplyMode) =>
    client.post<BenchmarkSkillApplyResponse>(`/projects/${id}/benchmark/skills/${skillId}/apply`, { mode }),
}