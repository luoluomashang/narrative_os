import { defineStore } from 'pinia'
import { ref } from 'vue'
import { sessions } from '@/api/sessions'
import type { TurnRecord, SessionSummary, CreateSessionRequest } from '@/types/session'

export const useSessionStore = defineStore('session', () => {
  const sessionId = ref<string | null>(null)
  const phase = ref<string>('INIT')
  const turn = ref(0)
  const density = ref<'dense' | 'normal' | 'sparse'>('normal')
  const scenePressure = ref(0)
  const emotionalTemperature = ref<{ base: string; current: number; drift: number }>({ base: 'neutral', current: 5.0, drift: 0.0 })
  const history = ref<TurnRecord[]>([])
  const summary = ref<SessionSummary | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function createSession(config: CreateSessionRequest = {}) {
    loading.value = true
    error.value = null
    history.value = []
    summary.value = null
    turn.value = 0
    try {
      const res = await sessions.create(config)
      sessionId.value = res.data.session_id
      phase.value = res.data.phase
      density.value = (res.data.density as 'dense' | 'normal' | 'sparse') ?? 'normal'
      scenePressure.value = res.data.scene_pressure ?? 0
      // 利用 opening_turn 直接初始化第一条历史（避免额外 step 请求）
      if (res.data.opening_turn) {
        history.value = [res.data.opening_turn as TurnRecord]
        turn.value = 1
      }
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function sendStep(action: string) {
    if (!sessionId.value) return
    loading.value = true
    try {
      const res = await sessions.step(sessionId.value, { user_input: action })
      const record: TurnRecord = { ...res.data, rolled_back: false }
      history.value.push(record)
      phase.value = res.data.phase
      density.value = (res.data.density as 'dense' | 'normal' | 'sparse') ?? density.value
      scenePressure.value = res.data.scene_pressure ?? scenePressure.value
      turn.value = history.value.filter(r => !r.rolled_back).length
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function triggerBangui(cmd: string) {
    if (!sessionId.value) return
    loading.value = true
    phase.value = 'INTERRUPT'
    try {
      await sessions.interrupt(sessionId.value, { bangui_command: cmd })
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function rollback(steps: number) {
    if (!sessionId.value) return
    loading.value = true
    try {
      await sessions.rollback(sessionId.value, { steps })
      // Mark last `steps` non-rolled-back records as rolled_back
      let count = 0
      for (let i = history.value.length - 1; i >= 0 && count < steps; i--) {
        if (!history.value[i].rolled_back) {
          history.value[i].rolled_back = true
          count++
        }
      }
      turn.value = history.value.filter(r => !r.rolled_back).length
      phase.value = 'ROLLBACK'
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'Unknown error'
    } finally {
      loading.value = false
    }
  }

  async function endSession() {
    if (!sessionId.value) return
    loading.value = true
    error.value = null
    try {
      const res = await sessions.end(sessionId.value)
      summary.value = res.data
      phase.value = 'ENDED'
      sessionId.value = null
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '结束会话失败'
      // Fallback summary
      summary.value = {
        duration_minutes: 0,
        turn_count: turn.value,
        word_count: 0,
        bangui_count: 0,
        key_decisions: [],
        next_hook: '',
        character_delta: [],
      }
      phase.value = 'ENDED'
      sessionId.value = null
    } finally {
      loading.value = false
    }
  }

  function reset() {
    sessionId.value = null
    phase.value = 'INIT'
    turn.value = 0
    density.value = 'normal'
    scenePressure.value = 0
    emotionalTemperature.value = { base: 'neutral', current: 5.0, drift: 0.0 }
    history.value = []
    summary.value = null
    error.value = null
  }

  return {
    sessionId, phase, turn, density, scenePressure, emotionalTemperature, history, summary,
    loading, error,
    createSession, sendStep, triggerBangui, rollback, endSession, reset,
  }
})

