import client from './client'
import type {
  PlotGraphData,
  CharacterSummary,
  CharacterDetail,
  CharacterDrive,
  CharacterRuntime,
  RelationshipProfile,
  MemorySnapshot,
  MemorySearchResult,
  ProjectListItem,
  ProjectInitRequest,
  ProjectInitResponse,
  MetricsHistoryItem,
  ChapterListItem,
  ChapterTextResponse,
  ExportNovelResponse,
} from '@/types/api'

export const projects = {
  list: () =>
    client.get<ProjectListItem[]>('/projects'),
  init: (req: ProjectInitRequest) =>
    client.post<ProjectInitResponse>('/projects/init', req),
  update: (id: string, data: { title?: string; genre?: string; description?: string; status?: string }) =>
    client.put(`/projects/${id}`, data),
  delete: (id: string) =>
    client.delete(`/projects/${id}`),
  archive: (id: string) =>
    client.post(`/projects/${id}/archive`),
  status: (id: string) =>
    client.get(`/projects/${id}/status`),
  changesets: (id: string) =>
    client.get(`/projects/${id}/changesets`),
  plot: (id: string) =>
    client.get<PlotGraphData>(`/projects/${id}/plot`),
  characters: (id: string) =>
    client.get<CharacterSummary[]>(`/projects/${id}/characters`),
  character: (id: string, name: string) =>
    client.get<CharacterDetail>(`/projects/${id}/characters/${encodeURIComponent(name)}`),
  createCharacter: (id: string, data: Partial<CharacterDetail>) =>
    client.post<CharacterDetail>(`/projects/${id}/characters`, data),
  updateCharacter: (id: string, name: string, data: Partial<CharacterDetail>) =>
    client.put<CharacterDetail>(`/projects/${id}/characters/${encodeURIComponent(name)}`, data),
  deleteCharacter: (id: string, name: string) =>
    client.delete<{ deleted: string }>(`/projects/${id}/characters/${encodeURIComponent(name)}`),
  testVoice: (id: string, name: string, scenario: string) =>
    client.post<{ dialogue: string }>(
      `/projects/${id}/characters/${encodeURIComponent(name)}/test-voice`,
      { scenario }
    ),
  // Phase 2: 四层角色端点
  getCharacterDrive: (id: string, name: string) =>
    client.get<CharacterDrive>(`/projects/${id}/characters/${encodeURIComponent(name)}/drive`),
  updateCharacterDrive: (id: string, name: string, data: Partial<CharacterDrive>) =>
    client.put<CharacterDrive>(`/projects/${id}/characters/${encodeURIComponent(name)}/drive`, data),
  updateCharacterRuntime: (id: string, name: string, data: Partial<CharacterRuntime>) =>
    client.put<CharacterRuntime>(`/projects/${id}/characters/${encodeURIComponent(name)}/runtime`, data),
  getCharacterSocialMatrix: (id: string, name: string) =>
    client.get<Record<string, RelationshipProfile>>(`/projects/${id}/characters/${encodeURIComponent(name)}/social-matrix`),
  updateCharacterSocialMatrix: (id: string, name: string, data: Record<string, Partial<RelationshipProfile>>) =>
    client.put<Record<string, RelationshipProfile>>(`/projects/${id}/characters/${encodeURIComponent(name)}/social-matrix`, data),
  memory: (id: string) =>
    client.get<MemorySnapshot>(`/projects/${id}/memory`),
  memorySearch: (id: string, q: string) =>
    client.get<MemorySearchResult>(`/projects/${id}/memory/search`, { params: { q } }),
  rollback: (id: string, steps: number) =>
    client.post(`/projects/${id}/rollback`, { steps }),
  metricsHistory: (id: string) =>
    client.get<MetricsHistoryItem[]>(`/projects/${id}/metrics/history`),
  chapterList: (id: string) =>
    client.get<ChapterListItem[]>(`/projects/${id}/chapters`),
  chapterText: (id: string, chapter: number) =>
    client.get<ChapterTextResponse>(`/projects/${id}/chapters/${chapter}`),
  exportNovel: (id: string, format: 'txt' | 'md' = 'txt') =>
    client.get<ExportNovelResponse>(`/projects/${id}/export`, { params: { format } }),
  getSettings: (id: string) =>
    client.get(`/projects/${id}/settings`),
  updateSettings: (id: string, settings: Record<string, unknown>) =>
    client.put(`/projects/${id}/settings`, { settings }),
  worldbuilderStart: (id: string) =>
    client.post(`/projects/${id}/worldbuilder/start`),
  worldbuilderStep: (id: string, data: { wb_session_id: string; user_input: string }) =>
    client.post(`/projects/${id}/worldbuilder/step`, data),
  /**
   * SSE 流式讨论当前世界构建步骤。返回 ReadableStream，需调用方解析 SSE 事件。
   */
  worldbuilderDiscuss: (id: string, data: { wb_session_id: string; message: string }) =>
    fetch(`/api/projects/${id}/worldbuilder/discuss`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
}

