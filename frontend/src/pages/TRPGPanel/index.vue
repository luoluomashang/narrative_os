<template>
  <div class="trpg-page">
    <!-- Session start screen -->
    <div v-if="!store.sessionId && store.phase === 'INIT'" class="session-init">
      <h2 class="init-title">🎲 TRPG 互动模式</h2>
      <p class="init-sub">PING_PONG 双屏会话</p>
      <button class="n-btn primary" :disabled="store.loading" @click="startSession">
        {{ store.loading ? '初始化中…' : '开始会话' }}
      </button>
    </div>

    <!-- Session ended — show summary -->
    <div v-else-if="store.phase === 'ENDED'" class="session-summary">
      <div class="summary-card">
        <h3 class="summary-title">会话总结</h3>
        <div class="summary-row">
          <span>时长</span><span>{{ store.summary?.duration_minutes ?? 0 }} 分钟</span>
        </div>
        <div class="summary-row">
          <span>回合数</span><span>{{ store.summary?.turn_count ?? 0 }}</span>
        </div>
        <div class="summary-row">
          <span>帮回触发</span><span>{{ store.summary?.bangui_count ?? 0 }} 次</span>
        </div>
        <div v-if="store.summary?.next_hook" class="summary-hook">
          <span class="hook-label">下章钩子</span>
          <p class="hook-text">{{ store.summary.next_hook }}</p>
        </div>
        <div v-if="store.summary?.character_delta?.length" class="summary-delta">
          <span class="delta-label">角色状态变化</span>
          <p v-for="d in store.summary.character_delta" :key="d.name" class="delta-item">
            {{ d.name }}：{{ d.change }}
          </p>
        </div>
        <div class="summary-actions">
          <button class="n-btn ghost" @click="store.reset">返回标准模式</button>
          <button class="n-btn primary" @click="startSession">开始新章</button>
        </div>
      </div>
    </div>

    <!-- Active session -->
    <template v-else>
      <!-- Top session info bar -->
      <div class="session-bar">
        <span class="session-phase-badge" :class="`phase-${store.phase}`">{{ phaseLabel }}</span>
        <span class="session-turn">回合 {{ store.turn }}</span>

        <!-- Scene Pressure gauge -->
        <div class="pressure-gauge-inline" :title="`场景压力: ${store.scenePressure?.toFixed(1)}/10`">
          <span class="pg-label">压力</span>
          <div class="pg-track">
            <div class="pg-fill" :style="{ width: pressurePct + '%' }" :class="pressureClass" />
          </div>
          <span class="pg-value">{{ store.scenePressure?.toFixed(1) ?? '5.0' }}</span>
        </div>

        <!-- Emotional Temperature bar -->
        <div class="temp-bar-inline" :title="`情感温度: ${store.emotionalTemperature.current.toFixed(1)}`">
          <span class="tb-edge">冷</span>
          <div class="tb-track">
            <div class="tb-cursor" :style="{ left: tempCursorPct + '%' }" :class="tempClass" />
          </div>
          <span class="tb-edge">热</span>
          <span v-if="Math.abs(store.emotionalTemperature.drift) >= 0.5"
            class="tb-drift" :class="store.emotionalTemperature.drift > 0 ? 'drift-hot' : 'drift-cold'">
            {{ store.emotionalTemperature.drift > 0 ? '↑' : '↓' }}{{ Math.abs(store.emotionalTemperature.drift).toFixed(1) }}
          </span>
        </div>

        <div style="flex:1" />
        <!-- Phase 3: SL buttons -->
        <button class="n-btn ghost sm" title="手动存档" @click="doCreateSave">💾 存档</button>
        <button class="n-btn ghost sm" title="读档" @click="openSLModal">📂 读档</button>
        <!-- Phase 3: Control mode selector -->
        <select v-model="controlMode" class="control-mode-select" title="控制权模式" @change="applyControlMode">
          <option value="user_driven">👤 用户驱动</option>
          <option value="semi_agent">🤝 半代理</option>
          <option value="full_agent">🤖 全代理</option>
          <option value="director">🎬 导演模式</option>
        </select>
        <button class="n-btn ghost sm" @click="showRollbackModal = true">↩ 回滚</button>
        <button class="n-btn danger sm" @click="confirmEnd">结束会话</button>
      </div>

      <!-- Pacing Alert Banner -->
      <Transition name="slide-down">
        <div v-if="store.phase === 'PACING_ALERT'" class="pacing-alert-banner">
          <span class="pa-icon">⚡</span>
          <span class="pa-text">节奏预警 — 叙事字数已达 {{ store.turn }} 回合，建议推进至着陆阶段</span>
          <div class="pa-actions">
            <button class="n-btn ghost sm" @click="continueAfterAlert">继续</button>
            <button class="n-btn primary sm" @click="confirmEnd">结算</button>
          </div>
        </div>
      </Transition>

      <!-- Agency Warning Banner -->
      <Transition name="slide-down">
        <div v-if="agencyWarningText" class="agency-warning-banner">
          <span>⚠ AI 可能越权替玩家决策：{{ agencyWarningText }}</span>
          <button class="banner-close" @click="agencyWarningText = ''">✕</button>
        </div>
      </Transition>

      <!-- Main dual panel -->
      <div class="session-main">
        <!-- DM Area (60%) -->
        <div class="dm-area" :class="`frame-${store.phase}`">
          <div class="dm-header">
            <span class="dm-label">DM 叙事</span>
            <span class="dm-status-dot" :class="`dot-${store.phase}`"></span>
          </div>

          <!-- Anti-proxy warning (local heuristic) -->
          <div v-if="antiProxyWarning" class="anti-proxy-bar">
            ⚠ AI 可能在替玩家做决定 — 请核查
          </div>

          <!-- Narrative text -->
          <div class="dm-narrative" ref="narrativeEl">
            <NTypewriter :text="narrativeText" :speed="35" />
          </div>

          <!-- Latest decision options in DM area -->
          <div v-if="latestOptions.length" class="dm-options">
            <div v-for="(opt, i) in latestOptions" :key="i" class="dm-option">
              <span class="dm-opt-type-icon">{{ decisionTypeIcon }}</span>
              [{{ String.fromCharCode(65 + i) }}] {{ opt }}
              <span class="dm-opt-risk" :class="`risk-badge-${latestRiskLevels[i] ?? 'safe'}`">
                {{ { safe: '✓', risky: '⚠', dangerous: '☠' }[latestRiskLevels[i] ?? 'safe'] }}
              </span>
            </div>
          </div>

          <!-- Context window bar -->
          <div class="context-bar">
            <span class="ctx-label">Context</span>
            <div class="ctx-track">
              <div class="ctx-fill" :style="{ width: contextPct + '%' }" :class="contextClass"></div>
            </div>
            <span class="ctx-count">{{ store.turn }} / {{ maxTurns }} 回合</span>
          </div>
        </div>

        <!-- Player Area (40%) -->
        <div class="player-area">
          <!-- Option buttons -->
          <div v-if="latestOptions.length" class="player-options">
            <button
              v-for="(opt, i) in latestOptions.slice(0, 6)"
              :key="i"
              class="option-btn"
              :class="`risk-opt-${latestRiskLevels[i] ?? 'safe'}`"
              :disabled="store.loading"
              @click="handleOptionClick(opt, i)"
            >
              <span class="opt-decision-icon">{{ decisionTypeIcon }}</span>
              <span class="opt-key">[{{ String.fromCharCode(65 + i) }}]</span>
              {{ opt }}
              <span class="opt-risk-badge" :class="`badge-${latestRiskLevels[i] ?? 'safe'}`">
                {{ { safe: '✓', risky: '⚠', dangerous: '☠' }[latestRiskLevels[i] ?? 'safe'] ?? '✓' }}
              </span>
            </button>
          </div>

          <!-- Free action input -->
          <div class="player-input-row">
            <input
              v-model="inputText"
              class="player-input"
              placeholder="输入自由行动…"
              :disabled="store.loading || contextFull"
              @keydown.enter.prevent="sendAction"
            />
            <button class="n-btn primary" :disabled="store.loading || !inputText.trim() || contextFull" @click="sendAction">
              发送
            </button>
          </div>

          <!-- Density pill selector -->
          <div class="density-pills">
            <button v-for="d in (['dense', 'normal', 'sparse'] as const)" :key="d"
              class="density-pill"
              :class="{ active: store.density === d }"
              @click="setDensity(d)">
              {{ { dense: '⚡密集', normal: '◎普通', sparse: '〜稀疏' }[d] }}
            </button>
          </div>

          <!-- Turn history -->
          <div class="turn-history" ref="historyEl">
            <div
              v-for="rec in store.history"
              :key="rec.turn_id"
              class="turn-record"
              :class="{
                'rolled-back': rec.rolled_back,
                'rewrite': rec.is_rewrite,
                'dm-turn': rec.who === 'dm',
              }"
            >
              <span class="turn-who">{{ rec.who === 'dm' ? 'DM' : '玩家' }} #{{ rec.turn_id }}</span>
              <span v-if="rec.rolled_back" class="rolled-label">已撤销 ×</span>
              <span v-if="rec.is_rewrite" class="rewrite-label">当前重写</span>
              <p class="turn-content">{{ rec.content }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Bangui shortcut bar -->
      <div class="bangui-bar">
        <button
          v-for="(btn, i) in banguiButtons"
          :key="i"
          class="bangui-btn"
          :class="{
            'active-bangui': activeBangui === btn.trigger,
            'disabled-bangui': store.phase === 'INTERRUPT' && activeBangui !== btn.trigger,
          }"
          :style="{ pointerEvents: store.phase === 'INTERRUPT' && activeBangui !== btn.trigger ? 'none' : 'auto' }"
          @click="triggerBangui(btn.trigger)"
        >
          {{ btn.label }}
        </button>
      </div>
      <!-- Dangerous option confirm modal -->
      <Teleport to="body">
        <div v-if="dangerConfirm" class="modal-overlay" @click.self="dangerConfirm = null">
          <div class="modal-box danger-confirm-modal">
            <h3>☠ 高风险行动确认</h3>
            <p class="danger-text">{{ dangerConfirm.opt }}</p>
            <p class="danger-warn">此选项被标记为高危险度，确认后不可撤销回到此节点。</p>
            <div class="modal-actions">
              <button class="n-btn ghost" @click="dangerConfirm = null">取消</button>
              <button class="n-btn danger" @click="confirmDangerous">确认执行</button>
            </div>
          </div>
        </div>
      </Teleport>

    </template>

    <!-- Rollback modal -->
    <Teleport to="body">
      <div v-if="showRollbackModal" class="modal-overlay" @click.self="showRollbackModal = false">
        <div class="modal-box rollback-modal">
          <h3>↩ 时间回溯</h3>
          <div class="rollback-options">
            <label v-for="n in [1, 2, 3]" :key="n" class="radio-row">
              <input type="radio" v-model="rollbackSteps" :value="n" />
              回退 {{ n }} 步
            </label>
            <label class="radio-row">
              <input type="radio" v-model="rollbackSteps" :value="customSteps" />
              自定义
              <input type="number" v-model.number="customSteps" min="1" max="20" class="custom-steps" />
              步
            </label>
          </div>
          <p class="rollback-warn">⚠ 被回退的回合保留显示，标记为"已撤销"。</p>
          <div class="modal-actions">
            <button class="n-btn ghost" @click="showRollbackModal = false">取消</button>
            <button class="n-btn primary" @click="doRollback">确认回退</button>
          </div>
        </div>
      </div>

      <!-- End session confirm -->
      <div v-if="showEndModal" class="modal-overlay" @click.self="showEndModal = false">
        <div class="modal-box end-modal">
          <h3>确认结束会话？</h3>
          <p>系统将收束剧情、更新角色状态并保存本回会话。历史记录将保存至章节。</p>
          <div class="modal-actions">
            <button class="n-btn ghost" @click="showEndModal = false">继续会话</button>
            <button class="n-btn danger" @click="doEndSession">确认着陆</button>
          </div>
        </div>
      </div>

      <!-- Phase 3: SL Modal -->
      <div v-if="showSLModal" class="modal-overlay" @click.self="showSLModal = false">
        <div class="modal-box sl-modal">
          <h3>📂 存档管理</h3>
          <div v-if="savesList.length === 0" class="sl-empty">暂无存档</div>
          <div v-else class="sl-list">
            <div v-for="s in savesList" :key="s.save_id" class="sl-item">
              <div class="sl-info">
                <span class="sl-trigger">{{ s.trigger }}</span>
                <span class="sl-turn">回合 {{ s.turn }}</span>
                <span class="sl-ts">{{ s.timestamp.slice(0, 16) }}</span>
                <span class="sl-pressure">压力 {{ s.scene_pressure?.toFixed(1) }}</span>
              </div>
              <div class="sl-actions">
                <button class="n-btn primary sm" @click="doLoadSave(s.save_id)">读档</button>
                <button class="n-btn danger sm" @click="doDeleteSave(s.save_id)">删除</button>
              </div>
            </div>
          </div>
          <div class="modal-actions">
            <button class="n-btn ghost" @click="showSLModal = false">关闭</button>
            <button class="n-btn primary" @click="doCreateSave">💾 新建存档</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- Toast container (bottom-right) -->
    <Teleport to="body">
      <div class="toast-container">
        <TransitionGroup name="toast">
          <div v-for="t in toasts" :key="t.id" class="toast-item" :class="`toast-${t.type}`">
            <span class="toast-icon">{{ { info: 'ℹ', warning: '⚠', error: '✕', success: '✓' }[t.type] ?? 'ℹ' }}</span>
            {{ t.message }}
          </div>
        </TransitionGroup>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import NTypewriter from '@/components/common/NTypewriter.vue'
import { useSessionStore } from '@/stores/sessionStore'
import { useToast } from '@/composables/useToast'
import { sessions as sessionsApi } from '@/api/sessions'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const store = useSessionStore()
const toast = useToast()

const inputText = ref('')
const narrativeText = ref('')
const narrativeEl = ref<HTMLElement | null>(null)
const historyEl = ref<HTMLElement | null>(null)
const showRollbackModal = ref(false)
const showEndModal = ref(false)
const rollbackSteps = ref(1)
const customSteps = ref(1)
const activeBangui = ref<string | null>(null)
const contextWarned = ref(false)
const maxTurns = 20

// Phase 4 new state
const agencyWarningText = ref('')
const dangerConfirm = ref<{ opt: string; idx: number } | null>(null)
const latestDecisionType = ref<string>('action')
const latestRiskLevels = ref<string[]>([])

// Phase 3: SL + control mode state
const showSLModal = ref(false)
const controlMode = ref<'user_driven' | 'semi_agent' | 'full_agent' | 'director'>('user_driven')
interface SaveEntry { save_id: string; trigger: string; timestamp: string; turn: number; scene_pressure: number }
const savesList = ref<SaveEntry[]>([])

interface ToastItem { id: number; type: 'info' | 'warning' | 'error' | 'success'; message: string }
const toasts = ref<ToastItem[]>([])
let toastSeq = 0
function pushToast(type: ToastItem['type'], message: string, duration = 4000) {
  const id = ++toastSeq
  toasts.value.push({ id, type, message })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, duration)
}

// WebSocket
let ws: WebSocket | null = null
let wsRetries = 0
const maxWsRetries = 3

function connectWs() {
  if (!store.sessionId) return
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${location.host}/ws/sessions/${store.sessionId}`
  ws = new WebSocket(url)

  ws.onopen = () => { wsRetries = 0 }

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data as string) as Record<string, unknown>
      if (msg.type === 'chunk') {
        narrativeText.value += msg.content as string
        scrollNarrative()
      } else if (msg.type === 'turn_complete') {
        const rec = msg.record as Record<string, unknown>
        if (rec) {
          store.history.push({ ...rec, rolled_back: false } as Parameters<typeof store.history.push>[0])
          // Update risk levels and decision type from record
          latestRiskLevels.value = (rec.risk_levels as string[]) ?? []
          latestDecisionType.value = (rec.decision_type as string) ?? 'action'
        }
        store.phase = (msg.phase as string) ?? store.phase
        if (msg.scene_pressure !== undefined) store.scenePressure = msg.scene_pressure as number
        if (msg.density) store.density = msg.density as 'dense' | 'normal' | 'sparse'
        if (msg.emotional_temperature) {
          store.emotionalTemperature = msg.emotional_temperature as typeof store.emotionalTemperature
        }
        if (store.phase === 'INTERRUPT') {
          store.phase = 'PING_PONG'
          activeBangui.value = null
        }
      } else if (msg.type === 'phase_change') {
        store.phase = msg.phase as string
      } else if (msg.type === 'density_change') {
        store.density = msg.density as 'dense' | 'normal' | 'sparse'
      } else if (msg.type === 'pacing_alert') {
        store.phase = 'PACING_ALERT'
        pushToast('warning', `节奏预警：已累积 ${msg.chars_so_far ?? 0} 字`, 6000)
      } else if (msg.type === 'agency_warning') {
        agencyWarningText.value = (msg.fragment as string) ?? ''
        pushToast('warning', 'DM 可能越权替玩家决策，已记录')
      } else if (msg.type === 'temp_drift') {
        store.emotionalTemperature = {
          ...store.emotionalTemperature,
          current: msg.current as number,
          drift: msg.drift as number,
        }
        const dir = (msg.drift as number) > 0 ? '升温' : '降温'
        pushToast('info', `情感温度${dir} ${Math.abs(msg.drift as number).toFixed(1)}`)
      } else if (msg.type === 'session_end') {
        store.summary = (msg.summary as typeof store.summary) ?? null
        store.phase = 'ENDED'
        ws?.close()
      }
    } catch { /* ignore malformed */ }
  }

  ws.onclose = () => {
    if (store.phase === 'ENDED') return
    if (wsRetries < maxWsRetries) {
      const delay = Math.min(1000 * 2 ** wsRetries, 8000)
      wsRetries++
      setTimeout(connectWs, delay)
    }
  }
}

async function startSession() {
  await store.createSession({ project_id: projectId.value })
  if (store.sessionId) {
    narrativeText.value = ''
    latestDecisionType.value = 'action'
    latestRiskLevels.value = []
    connectWs()
  }
}

async function sendAction() {
  const text = inputText.value.trim()
  if (!text || store.loading) return
  inputText.value = ''
  await store.sendStep(text)
  scrollHistory()
}

function selectOption(opt: string) {
  inputText.value = opt
  sendAction()
}

function handleOptionClick(opt: string, idx: number) {
  const risk = latestRiskLevels.value[idx] ?? 'safe'
  if (risk === 'dangerous') {
    dangerConfirm.value = { opt, idx }
  } else {
    selectOption(opt)
  }
}

function confirmDangerous() {
  if (dangerConfirm.value) {
    const opt = dangerConfirm.value.opt
    dangerConfirm.value = null
    selectOption(opt)
  }
}

function continueAfterAlert() {
  if (store.phase === 'PACING_ALERT') store.phase = 'PING_PONG'
}

async function triggerBangui(trigger: string) {
  if (store.phase === 'INTERRUPT') return
  activeBangui.value = trigger
  await store.triggerBangui(trigger)
}

async function doRollback() {
  const steps = rollbackSteps.value
  showRollbackModal.value = false
  await store.rollback(steps)
}

function confirmEnd() { showEndModal.value = true }

async function doEndSession() {
  showEndModal.value = false
  await store.endSession()
}

// Phase 3: SL functions
async function doCreateSave() {
  if (!store.sessionId) return
  try {
    const res = await sessionsApi.createSave(projectId.value, store.sessionId, 'manual')
    pushToast('success', `存档成功 (回合 ${res.data.turn})`)
    // Refresh list if modal open
    if (showSLModal.value) await fetchSaves()
  } catch {
    pushToast('error', '存档失败')
  }
}

async function fetchSaves() {
  if (!store.sessionId) return
  try {
    const res = await sessionsApi.listSaves(projectId.value, store.sessionId)
    savesList.value = res.data ?? []
  } catch {
    savesList.value = []
  }
}

async function openSLModal() {
  await fetchSaves()
  showSLModal.value = true
}

async function doLoadSave(saveId: string) {
  if (!store.sessionId) return
  try {
    const res = await sessionsApi.loadSave(projectId.value, store.sessionId, saveId)
    showSLModal.value = false
    store.turn = res.data.restored_turn
    pushToast('success', `已读档至回合 ${res.data.restored_turn}`)
  } catch {
    pushToast('error', '读档失败')
  }
}

async function doDeleteSave(saveId: string) {
  if (!store.sessionId) return
  try {
    await sessionsApi.deleteSave(projectId.value, store.sessionId, saveId)
    await fetchSaves()
    pushToast('info', '存档已删除')
  } catch {
    pushToast('error', '删除失败')
  }
}

async function applyControlMode() {
  if (!store.sessionId) return
  try {
    await sessionsApi.setControlMode(projectId.value, store.sessionId, controlMode.value)
    pushToast('info', `控制模式已切换为 ${controlMode.value}`)
  } catch {
    pushToast('error', '控制模式切换失败')
  }
}

function setDensity(d: 'dense' | 'normal' | 'sparse') {
  store.density = d
  // Send density change via WS if connected
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: '__density_hint__', density: d }))
  }
}

function scrollNarrative() {
  nextTick(() => {
    if (narrativeEl.value) narrativeEl.value.scrollTop = narrativeEl.value.scrollHeight
  })
}

function scrollHistory() {
  nextTick(() => {
    if (historyEl.value) historyEl.value.scrollTop = historyEl.value.scrollHeight
  })
}

// Context window monitoring
const contextPct = computed(() => Math.min((store.turn / maxTurns) * 100, 100))
const contextFull = computed(() => store.turn >= maxTurns)
const contextClass = computed(() => {
  if (contextPct.value >= 100) return 'ctx-full'
  if (contextPct.value >= 90) return 'ctx-warn'
  return ''
})

watch(() => store.turn, (t) => {
  if (t >= 18 && !contextWarned.value) {
    contextWarned.value = true
    toast.add({ type: 'warning', message: '上下文即将达到上限，建议尽快推进至着陆阶段' })
  }
  if (t >= maxTurns) {
    store.phase = 'PACING_ALERT'
  }
})

// Phase 4 computed — pressure
const pressurePct = computed(() => Math.min((store.scenePressure / 10) * 100, 100))
const pressureClass = computed(() => {
  if (store.scenePressure >= 8) return 'pg-danger'
  if (store.scenePressure >= 5) return 'pg-warn'
  return 'pg-safe'
})

// Phase 4 computed — temperature
const tempCursorPct = computed(() => Math.min((store.emotionalTemperature.current / 10) * 100, 100))
const tempClass = computed(() => {
  const c = store.emotionalTemperature.current
  if (c >= 7) return 'temp-hot'
  if (c <= 3) return 'temp-cold'
  return 'temp-neutral'
})

// Latest DM options
const latestOptions = computed(() => {
  for (let i = store.history.length - 1; i >= 0; i--) {
    const r = store.history[i] as Record<string, unknown>
    if (!r.rolled_back && r.has_decision && (r.decision_options as unknown[])?.length) {
      return r.decision_options as string[]
    }
  }
  return []
})

const antiProxyWarning = computed(() => {
  const last = store.history.at(-1) as Record<string, unknown> | undefined
  return last?.who === 'dm' && /我决定|你应该|最好选择/.test(last.content as string)
})

const phaseLabels: Record<string, string> = {
  INIT: '初始化', OPENING: '开场白', PING_PONG: '对话进行中',
  ROLLBACK: '时间回溯中', INTERRUPT: '帮回介入',
  PACING_ALERT: '节奏预警', LANDING: '着陆收束',
  MAINTENANCE: '章末维护', ENDED: '会话已结束',
}
const phaseLabel = computed(() => phaseLabels[store.phase] ?? store.phase)

// Decision type icon mapping
const decisionTypeIcon = computed(() => {
  const icons: Record<string, string> = {
    action: '⚔️', dialogue: '💬', moral: '🎭', tactical: '🎯', default: '💭'
  }
  return icons[latestDecisionType.value] ?? icons.default
})

// Bangui 8 buttons
const banguiButtons = [
  { trigger: '帮回主动1', label: '主动型1' },
  { trigger: '帮回主动2', label: '主动型2' },
  { trigger: '帮回被动1', label: '被动型1' },
  { trigger: '帮回被动2', label: '被动型2' },
  { trigger: '帮回黑暗1', label: '黑暗型1' },
  { trigger: '帮回黑暗2', label: '黑暗型2' },
  { trigger: '帮回推进1', label: '推进型1' },
  { trigger: '帮回推进2', label: '推进型2' },
]

onUnmounted(() => {
  if (ws) {
    ws.close()
    ws = null
  }
})
</script>

<style scoped>
.trpg-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-base);
  overflow: hidden;
}

/* Init screen */
.session-init {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  gap: var(--spacing-md);
}
.init-title { font-size: var(--text-h1); font-weight: var(--weight-h1); color: var(--color-text-primary); }
.init-sub { color: var(--color-text-secondary); }

/* Session bar */
.session-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-surface-l1);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.session-phase-badge {
  padding: 2px 10px;
  border-radius: 99px;
  font-size: var(--text-caption);
  font-weight: 600;
  background: var(--color-surface-l2);
  color: var(--color-text-primary);
}
.session-turn, .session-density { font-size: 13px; color: var(--color-text-secondary); }

/* Main dual panel */
.session-main {
  display: grid;
  grid-template-columns: 60% 40%;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* DM Area */
.dm-area {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-surface-l2);
  border-left: 3px solid var(--color-ai-active);
  padding: var(--spacing-md);
  overflow: hidden;
  transition: border-left-color 300ms;
}
.dm-header { display: flex; align-items: center; gap: var(--spacing-sm); margin-bottom: var(--spacing-sm); }
.dm-label { font-size: 13px; font-weight: 600; color: var(--color-text-secondary); }
.dm-status-dot {
  width: 8px; height: 8px; border-radius: 50%; background: var(--color-ai-active);
  animation: breathing 2s ease-in-out infinite;
}
.anti-proxy-bar {
  background: var(--color-error);
  color: #fff;
  padding: 4px var(--spacing-sm);
  font-size: var(--text-caption);
  border-radius: var(--radius-btn);
  margin-bottom: var(--spacing-sm);
}
.dm-narrative {
  flex: 1;
  overflow-y: auto;
  font-size: var(--text-body);
  line-height: var(--lh-body);
  color: var(--color-text-primary);
  padding-right: var(--spacing-sm);
}
.dm-options { margin-top: var(--spacing-sm); display: flex; flex-direction: column; gap: 4px; }
.dm-option { font-size: 13px; color: var(--color-ai-active); }

/* Context bar */
.context-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding-top: var(--spacing-sm);
  border-top: 1px solid var(--color-surface-l2);
  margin-top: var(--spacing-sm);
  flex-shrink: 0;
}
.ctx-label { font-size: var(--text-caption); color: var(--color-text-secondary); }
.ctx-track { flex: 1; height: 6px; background: var(--color-surface-l2); border-radius: 3px; overflow: hidden; }
.ctx-fill { height: 100%; background: var(--color-ai-active); border-radius: 3px; transition: width 400ms; }
.ctx-fill.ctx-warn { background: var(--color-warning); }
.ctx-fill.ctx-full { background: var(--color-error); animation: flash 0.5s ease-in-out infinite alternate; }
.ctx-count { font-size: var(--text-caption); color: var(--color-text-secondary); white-space: nowrap; }

/* Player Area */
.player-area {
  display: flex;
  flex-direction: column;
  padding: var(--spacing-md);
  gap: var(--spacing-sm);
  overflow: hidden;
}
.player-options { display: flex; flex-direction: column; gap: 4px; }
.option-btn {
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  color: var(--color-text-primary);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-btn);
  text-align: left;
  cursor: pointer;
  font-size: 13px;
  transition: background 150ms, border-color 150ms;
}
.option-btn:hover { background: #3d3f4a; border-color: var(--color-ai-active); }
.option-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.opt-key { color: var(--color-ai-active); font-weight: 600; margin-right: 6px; }

.player-input-row { display: flex; gap: var(--spacing-sm); }
.player-input {
  flex: 1;
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  color: var(--color-text-primary);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-btn);
  font-size: 14px;
}
.player-input:focus { outline: none; border-color: var(--color-ai-active); }
.player-input:disabled { opacity: 0.4; }

/* Density indicator */
.density-indicator { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.d-track { flex: 1; height: 4px; background: var(--color-surface-l2); border-radius: 2px; }
.d-fill { height: 100%; background: var(--color-ai-active); border-radius: 2px; transition: width 400ms; }
.d-dot { opacity: 0.4; transition: opacity 200ms; }
.d-dot.active { opacity: 1; }
.d-label { color: var(--color-text-secondary); }

/* Turn history */
.turn-history { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
.turn-record {
  padding: var(--spacing-sm);
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  border-left: 3px solid transparent;
}
.turn-record.dm-turn { border-left-color: var(--color-ai-active); }
.turn-record.rewrite { border-left-color: var(--color-ai-active); }
.turn-record.rolled-back { opacity: 0.4; border-left-color: var(--color-warning); border-left-style: dashed; }
.turn-who { font-size: var(--text-caption); color: var(--color-text-secondary); font-weight: 600; }
.rolled-label { margin-left: 6px; font-size: var(--text-caption); color: var(--color-text-secondary); text-decoration: line-through; }
.rewrite-label { margin-left: 6px; font-size: var(--text-caption); color: var(--color-ai-active); }
.turn-content { font-size: 13px; color: var(--color-text-primary); margin-top: 4px; line-height: 1.6; }

/* Bangui bar */
.bangui-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-surface-l1);
  border-top: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.bangui-btn {
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  color: var(--color-text-primary);
  padding: var(--spacing-sm);
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 12px;
  transition: all 200ms;
  text-align: center;
}
.bangui-btn:hover { border-color: var(--color-hitl); color: var(--color-hitl); }
.bangui-btn.active-bangui {
  border-color: var(--color-hitl);
  background: rgba(255, 46, 136, 0.15);
  animation: bangui-pulse 0.3s ease-out;
}
.bangui-btn.disabled-bangui { opacity: 0.35; }

/* Phase frame colors */
.frame-INIT { border-left-color: #999 !important; }
.frame-OPENING { border-left-color: var(--color-ai-active) !important; animation: breathing 2s ease-in-out infinite; }
.frame-PING_PONG { border-left-color: var(--color-ai-active) !important; }
.frame-ROLLBACK { border-left-color: var(--color-warning) !important; }
.frame-INTERRUPT { border-left-color: var(--color-hitl) !important; }
.frame-PACING_ALERT { border-left-color: var(--color-error) !important; animation: flash 0.5s ease-in-out infinite alternate; }
.frame-LANDING { border-left-color: var(--color-success) !important; }
.frame-MAINTENANCE { border-left-color: var(--color-success) !important; animation: breathing 3s ease-in-out infinite; }
.frame-ENDED { border-left-color: #999 !important; }

/* Status dot */
.dot-OPENING, .dot-PING_PONG { background: var(--color-ai-active) !important; }
.dot-INTERRUPT { background: var(--color-hitl) !important; }
.dot-ROLLBACK { background: var(--color-warning) !important; }
.dot-PACING_ALERT { background: var(--color-error) !important; }
.dot-LANDING, .dot-MAINTENANCE { background: var(--color-success) !important; }
.dot-ENDED, .dot-INIT { background: #999 !important; }

/* Phase badge colors */
.phase-PING_PONG { color: var(--color-ai-active); }
.phase-INTERRUPT { color: var(--color-hitl); }
.phase-ROLLBACK { color: var(--color-warning); }
.phase-PACING_ALERT { color: var(--color-error); }
.phase-LANDING, .phase-MAINTENANCE { color: var(--color-success); }

/* ---- Phase 4: Pressure Gauge ---- */
.pressure-gauge-inline {
  display: flex; align-items: center; gap: 5px; flex-shrink: 0;
}
.pg-label { font-size: 12px; color: var(--color-text-secondary); white-space: nowrap; }
.pg-track {
  width: 80px; height: 6px;
  background: var(--color-surface-l2); border-radius: 3px; overflow: hidden;
}
.pg-fill { height: 100%; border-radius: 3px; transition: width 600ms, background 300ms; }
.pg-safe { background: #3fbe8a; }
.pg-warn { background: var(--color-warning); }
.pg-danger { background: var(--color-error); animation: pressure-pulse 1s ease-in-out infinite alternate; }
.pg-value { font-size: 12px; color: var(--color-text-secondary); width: 26px; text-align: right; }

/* ---- Phase 4: Temperature Bar ---- */
.temp-bar-inline {
  display: flex; align-items: center; gap: 5px; flex-shrink: 0;
}
.tb-edge { font-size: 11px; color: var(--color-text-secondary); }
.tb-track {
  position: relative; width: 80px; height: 6px;
  background: linear-gradient(to right, #5588ff, #888, #ff6644);
  border-radius: 3px; overflow: visible;
}
.tb-cursor {
  position: absolute; top: -3px; width: 12px; height: 12px;
  border-radius: 50%; border: 2px solid #fff;
  transform: translateX(-50%); transition: left 600ms;
}
.temp-cold { background: #5588ff; }
.temp-neutral { background: #aaa; }
.temp-hot { background: #ff6644; }
.tb-drift {
  font-size: 11px; font-weight: 600; animation: drift-fade 4s ease-out forwards;
}
.drift-hot { color: #ff6644; }
.drift-cold { color: #5588ff; }

/* ---- Phase 4: Density pills ---- */
.density-pills {
  display: flex; gap: 4px; flex-shrink: 0;
}
.density-pill {
  padding: 3px 9px; font-size: 12px; border-radius: 99px;
  border: 1px solid var(--color-surface-l2);
  background: var(--color-surface-l2); color: var(--color-text-secondary);
  cursor: pointer; transition: all 150ms;
}
.density-pill:hover { border-color: var(--color-ai-active); color: var(--color-ai-active); }
.density-pill.active {
  background: var(--color-ai-active); color: #000;
  border-color: var(--color-ai-active); font-weight: 600;
}

/* ---- Phase 4: Risk badges ---- */
.dm-opt-type-icon { margin-right: 4px; font-size: 13px; }
.dm-opt-risk { float: right; font-size: 11px; font-weight: 700; margin-left: 6px; }
.risk-badge-safe { color: #3fbe8a; }
.risk-badge-risky { color: var(--color-warning); }
.risk-badge-dangerous { color: var(--color-error); }

.opt-decision-icon { margin-right: 4px; font-size: 13px; flex-shrink: 0; }
.opt-risk-badge {
  margin-left: auto; padding-left: 8px; font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.badge-safe { color: #3fbe8a; }
.badge-risky { color: var(--color-warning); }
.badge-dangerous { color: var(--color-error); }

.option-btn { display: flex; align-items: center; }
.risk-opt-risky { border-color: rgba(255, 180, 0, 0.3) !important; }
.risk-opt-dangerous { border-color: rgba(255, 64, 64, 0.4) !important; }
.risk-opt-dangerous:hover { background: rgba(255,64,64,0.08) !important; }

/* ---- Phase 4: Banners ---- */
.pacing-alert-banner {
  display: flex; align-items: center; gap: var(--spacing-sm);
  padding: 8px var(--spacing-md);
  background: rgba(255,64,64,0.12);
  border-bottom: 2px solid var(--color-error);
  flex-shrink: 0;
}
.pa-icon { font-size: 16px; }
.pa-text { flex: 1; font-size: 13px; color: var(--color-error); font-weight: 600; }
.pa-actions { display: flex; gap: var(--spacing-sm); }

.agency-warning-banner {
  display: flex; align-items: center; gap: var(--spacing-sm);
  padding: 6px var(--spacing-md);
  background: rgba(255, 180, 0, 0.1);
  border-bottom: 1px solid var(--color-warning);
  font-size: 13px; color: var(--color-warning);
  flex-shrink: 0;
}
.agency-warning-banner span { flex: 1; }
.banner-close {
  background: transparent; border: none; cursor: pointer;
  color: var(--color-text-secondary); font-size: 14px; padding: 0 4px;
}
.banner-close:hover { color: var(--color-text-primary); }

/* ---- Phase 4: Toast ---- */
.toast-container {
  position: fixed; bottom: var(--spacing-lg); right: var(--spacing-lg);
  display: flex; flex-direction: column; gap: 8px; z-index: 9999; pointer-events: none;
}
.toast-item {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 14px;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  font-size: 13px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.4);
  min-width: 220px; max-width: 360px;
}
.toast-icon { font-size: 14px; flex-shrink: 0; }
.toast-info { border-left: 3px solid var(--color-ai-active); }
.toast-warning { border-left: 3px solid var(--color-warning); }
.toast-error { border-left: 3px solid var(--color-error); }
.toast-success { border-left: 3px solid var(--color-success); }

/* ---- Phase 4 danger confirm ---- */
.danger-confirm-modal {}
.danger-text { font-size: 14px; font-weight: 600; margin-bottom: var(--spacing-sm); }
.danger-warn { font-size: 13px; color: var(--color-warning); }

/* ---- Transitions ---- */
.slide-down-enter-active, .slide-down-leave-active {
  transition: all 250ms ease;
}
.slide-down-enter-from, .slide-down-leave-to {
  transform: translateY(-100%); opacity: 0;
}
.toast-enter-active { transition: all 300ms ease-out; }
.toast-leave-active { transition: all 200ms ease-in; }
.toast-enter-from { transform: translateX(100%); opacity: 0; }
.toast-leave-to { transform: translateX(100%); opacity: 0; }

/* ---- Animations ---- */
@keyframes pressure-pulse {
  from { opacity: 0.7; }
  to { opacity: 1; }
}
@keyframes drift-fade {
  0% { opacity: 1; } 70% { opacity: 1; } 100% { opacity: 0; }
}

/* Modal */
.modal-overlay {
  position: fixed; inset: 0;
  background: rgba(10,10,11,0.8);
  display: flex; align-items: center; justify-content: center;
  z-index: 200;
}
.modal-box {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-modal);
  padding: var(--spacing-lg);
  min-width: 360px;
  max-width: 480px;
}
.modal-box h3 { font-size: var(--text-h2); margin-bottom: var(--spacing-md); }
.modal-actions { display: flex; gap: var(--spacing-sm); justify-content: flex-end; margin-top: var(--spacing-md); }
.rollback-options { display: flex; flex-direction: column; gap: var(--spacing-sm); margin-bottom: var(--spacing-md); }
.radio-row { display: flex; align-items: center; gap: var(--spacing-sm); color: var(--color-text-primary); font-size: 14px; }
.custom-steps { width: 60px; padding: 2px 6px; background: var(--color-surface-l2); border: 1px solid var(--color-surface-l2); color: var(--color-text-primary); border-radius: 4px; }
.rollback-warn { font-size: var(--text-caption); color: var(--color-warning); }
.end-modal p { color: var(--color-text-secondary); }

/* Summary */
.session-summary {
  display: flex; align-items: center; justify-content: center; height: 100%;
}
.summary-card {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-modal);
  padding: var(--spacing-lg);
  min-width: 400px;
}
.summary-title { font-size: var(--text-h2); font-weight: 600; margin-bottom: var(--spacing-md); }
.summary-row { display: flex; justify-content: space-between; padding: 4px 0; font-size: 14px; border-bottom: 1px solid var(--color-surface-l2); }
.summary-hook { margin-top: var(--spacing-md); }
.hook-label, .delta-label { font-size: var(--text-caption); color: var(--color-text-secondary); display: block; margin-bottom: 4px; }
.hook-text { font-size: 14px; color: var(--color-ai-active); }
.delta-item { font-size: 13px; margin: 2px 0; }
.summary-actions { display: flex; gap: var(--spacing-sm); justify-content: flex-end; margin-top: var(--spacing-lg); }

/* Button helpers */
.n-btn {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 14px;
  border: 1px solid transparent;
  transition: all 150ms;
}
.n-btn.primary { background: var(--color-ai-active); color: #000; border-color: var(--color-ai-active); }
.n-btn.primary:hover { filter: brightness(1.15); }
.n-btn.ghost { background: transparent; color: var(--color-text-primary); border-color: var(--color-surface-l2); }
.n-btn.ghost:hover { border-color: var(--color-ai-active); }
.n-btn.danger { background: transparent; color: var(--color-error); border-color: var(--color-error); }
.n-btn.danger:hover { background: rgba(255,64,64,0.1); }
.n-btn.sm { padding: 4px 10px; font-size: 12px; }
.n-btn:disabled { opacity: 0.4; cursor: not-allowed; }

/* Animations */
@keyframes bangui-pulse {
  0% { transform: translateY(0) scale(1); box-shadow: 0 0 0 0 rgba(255,46,136,0.5); }
  50% { transform: translateY(-2px) scale(1.04); box-shadow: 0 0 8px 4px rgba(255,46,136,0.3); }
  100% { transform: translateY(0) scale(1); box-shadow: 0 0 0 0 rgba(255,46,136,0); }
}
@keyframes flash {
  from { border-left-color: var(--color-error); }
  to { border-left-color: transparent; }
}
@keyframes breathing {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.8; }
}

/* Phase 3: Control mode selector */
.control-mode-select {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  color: var(--color-text-primary);
  border-radius: 6px;
  padding: 4px 8px;
  font-size: 12px;
  cursor: pointer;
}
.control-mode-select:hover {
  border-color: var(--color-ai-active);
}

/* Phase 3: SL Modal */
.sl-modal { min-width: 400px; }
.sl-empty { color: var(--color-text-secondary); text-align: center; padding: 20px; }
.sl-list { display: flex; flex-direction: column; gap: 8px; max-height: 300px; overflow-y: auto; }
.sl-item {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 12px;
  background: var(--color-surface-l1);
  border-radius: 6px;
  border: 1px solid var(--color-surface-l2);
}
.sl-info { display: flex; gap: 12px; align-items: center; font-size: 12px; }
.sl-trigger { font-weight: 600; color: var(--color-ai-active); }
.sl-turn, .sl-ts, .sl-pressure { color: var(--color-text-secondary); }
.sl-actions { display: flex; gap: 6px; }
</style>

