import type {
  components,
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
}

export type ArchivePreviewResponse = components["schemas"]["ArchivePreviewResponse"]
export type CanonChapterPreview = components["schemas"]["CanonChapterPreview"]
export type CanonPendingChangePreview = components["schemas"]["CanonPendingChangePreview"]
export type DraftChapterPreview = components["schemas"]["DraftChapterPreview"]
export type PreviewCharacterChange = components["schemas"]["PreviewCharacterChange"]
export type PreviewMemoryAnchor = components["schemas"]["PreviewMemoryAnchor"]
export type SessionOnlyPreview = components["schemas"]["SessionOnlyPreview"]

export type WsMessageType =
  | 'chunk' | 'turn_complete' | 'session_end' | 'phase_change'
  | 'density_change' | 'pacing_alert' | 'temp_drift' | 'agency_warning' | 'error'

export interface WsMessage {
  type: WsMessageType
  [key: string]: unknown
}
