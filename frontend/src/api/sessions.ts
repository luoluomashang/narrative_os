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
}
