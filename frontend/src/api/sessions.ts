import client from './client'
import type { CreateSessionRequest, CreateSessionResponse, StepSessionRequest, TurnRecordResponse, SessionStatusResponse, InterruptRequest, RollbackRequest, SessionSummary } from '@/types/session'

export const sessions = {
  create: (req: CreateSessionRequest) =>
    client.post<CreateSessionResponse>('/sessions/create', req),
  step: (id: string, req: StepSessionRequest) =>
    client.post<TurnRecordResponse>(`/sessions/${id}/step`, req),
  interrupt: (id: string, req: InterruptRequest) =>
    client.post(`/sessions/${id}/interrupt`, req),
  rollback: (id: string, req: RollbackRequest) =>
    client.post(`/sessions/${id}/rollback`, req),
  end: (id: string) =>
    client.post<SessionSummary>(`/sessions/${id}/end`),
  status: (id: string) =>
    client.get<SessionStatusResponse>(`/sessions/${id}/status`),
  // Phase 3: SL
  createSave: (projectId: string, sessionId: string, trigger = 'manual') =>
    client.post<{ save_id: string; trigger: string; timestamp: string; turn: number }>(
      `/projects/${projectId}/sessions/${sessionId}/save`,
      { trigger },
    ),
  listSaves: (projectId: string, sessionId: string) =>
    client.get<Array<{ save_id: string; trigger: string; timestamp: string; turn: number; scene_pressure: number }>>(
      `/projects/${projectId}/sessions/${sessionId}/saves`,
    ),
  loadSave: (projectId: string, sessionId: string, saveId: string) =>
    client.post<{ save_id: string; restored_turn: number; memory_summary_preserved: boolean }>(
      `/projects/${projectId}/sessions/${sessionId}/load/${saveId}`,
    ),
  deleteSave: (projectId: string, sessionId: string, saveId: string) =>
    client.delete(`/projects/${projectId}/sessions/${sessionId}/saves/${saveId}`),
  // Phase 3: Control mode
  setControlMode: (
    projectId: string,
    sessionId: string,
    mode: string,
    opts: { ai_controlled_characters?: string[]; allow_protagonist_proxy?: boolean; director_intervention_enabled?: boolean } = {},
  ) =>
    client.post<{ session_id: string; mode: string; prompt_hint: string }>(
      `/projects/${projectId}/sessions/${sessionId}/control-mode`,
      { mode, ...opts },
    ),
  getAgenda: (projectId: string, sessionId: string) =>
    client.get<{ session_id: string; turn: number; agenda: Array<Record<string, unknown>> }>(
      `/projects/${projectId}/sessions/${sessionId}/agenda`,
    ),
}
