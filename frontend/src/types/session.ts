export type {
  CreateSessionRequest,
  CreateSessionResponse,
  StepSessionRequest,
  TurnRecordResponse,
  InterruptRequest,
  RollbackRequest,
  SessionSummary,
  TurnRecord,
  SessionStatusResponse,
} from './api.gen'

export type WsMessageType =
  | 'chunk' | 'turn_complete' | 'session_end' | 'phase_change'
  | 'density_change' | 'pacing_alert' | 'temp_drift' | 'agency_warning' | 'error'

export interface WsMessage {
  type: WsMessageType
  [key: string]: unknown
}
