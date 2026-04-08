// session.ts — TRPG session related types

export interface CreateSessionRequest {
  project_id?: string
  character_name?: string
  density?: string
  scene_pressure?: number
  opening_prompt?: string
  world_summary?: string
  max_history_turns?: number
}

export interface CreateSessionResponse {
  session_id: string
  phase: string
  density: string
  scene_pressure: number
  opening_turn?: TurnRecordResponse  // 后端在创建会话时可能直接返回首轮 DM 叙事
}

export interface StepSessionRequest {
  user_input: string
  // decision_choice 已废弃：选择项直接写入 user_input 发送
}

export interface TurnRecordResponse {
  turn_id: number
  who: string
  content: string
  scene_pressure: number
  density: string
  phase: string
  has_decision: boolean
  decision_options: string[]
}

export interface InterruptRequest {
  bangui_command: string
}

export interface RollbackRequest {
  steps: number
}

export interface SessionSummary {
  duration_minutes: number
  turn_count: number
  bangui_count: number
  key_decisions: Array<{ turn: number; choice: string }>
  next_hook: string
  character_delta: Array<{ name: string; change: string }>
}

export interface TurnRecord {
  turn_id: number
  who: string
  content: string
  scene_pressure: number
  density: string
  phase: string
  has_decision: boolean
  decision_options: string[]
  decision_type?: string
  risk_levels?: string[]
  rolled_back?: boolean
  is_rewrite?: boolean
  rewrite_index?: number
}

export interface SessionStatusResponse {
  session_id: string
  project_id: string
  phase: string
  turn: number
  density: string
  scene_pressure: number
  history_count: number
  emotional_temperature?: { base: string; current: number; drift: number }
  turn_char_count?: number
  // legacy aliases for compatibility
  turn_count?: number
  last_dm_content?: string
  has_decision?: boolean
  decision_options?: string[]
}

export type WsMessageType =
  | 'chunk' | 'turn_complete' | 'session_end' | 'phase_change'
  | 'density_change' | 'pacing_alert' | 'temp_drift' | 'agency_warning' | 'error'

export interface WsMessage {
  type: WsMessageType
  [key: string]: unknown
}
