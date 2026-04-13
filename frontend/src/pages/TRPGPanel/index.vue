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
        <div v-if="summaryHookText" class="summary-hook">
          <span class="hook-label">下章钩子</span>
          <p class="hook-text">{{ summaryHookText }}</p>
        </div>
        <div v-if="store.summary?.character_delta?.length" class="summary-delta">
          <span class="delta-label">角色状态变化</span>
          <p v-for="d in store.summary.character_delta" :key="d.name" class="delta-item">
            {{ d.name }}：{{ d.change }}
          </p>
        </div>
        <div v-if="summaryArchivePreview" class="archive-preview-block">
          <div class="archive-tabs">
            <button
              v-for="tab in archiveTabs"
              :key="tab.key"
              class="archive-tab"
              :class="{ active: archivePreviewTab === tab.key }"
              @click="archivePreviewTab = tab.key"
            >
              {{ tab.label }}
            </button>
          </div>

          <div v-if="archivePreviewTab === 'session_only'" class="archive-preview-card">
            <div class="preview-title">会话归档</div>
            <p class="preview-summary">{{ summarySessionOnlyText || '本次会话将仅归档为互动记录。' }}</p>
            <div v-if="summaryArchivePreview.preview_session_only.memory_anchors.length" class="preview-chip-row">
              <span
                v-for="anchor in summaryArchivePreview.preview_session_only.memory_anchors"
                :key="anchor.label"
                class="preview-chip"
              >
                {{ anchor.label }}
              </span>
            </div>
          </div>

          <div v-else-if="archivePreviewTab === 'draft_chapter'" class="archive-preview-card">
            <div class="preview-title">章节草稿</div>
            <div class="preview-metric-row">
              <span>预计字数</span>
              <strong>{{ summaryArchivePreview.preview_draft_chapter.word_count }}</strong>
            </div>
            <div class="preview-metric-row">
              <span>质量评估</span>
              <strong>{{ summaryArchivePreview.preview_draft_chapter.quality_estimate || '待评估' }}</strong>
            </div>
            <p class="preview-excerpt">{{ summaryDraftExcerptText || '暂无可预览正文。' }}</p>
          </div>

          <div v-else class="archive-preview-card">
            <div class="preview-title">正史审批</div>
            <p class="preview-summary">该模式会把互动结果整理为待审 Canon 变更集。</p>
            <div class="preview-chip-row">
              <span
                v-for="field in summaryArchivePreview.preview_canon_chapter.approval_required_fields"
                :key="field"
                class="preview-chip warning"
              >
                {{ field }}
              </span>
            </div>
            <div v-if="summaryArchivePreview.preview_canon_chapter.pending_changes.length" class="canon-change-list">
              <div
                v-for="(item, index) in summaryArchivePreview.preview_canon_chapter.pending_changes"
                :key="`${item.change_type}-${index}`"
                class="canon-change-item"
              >
                <span class="canon-change-type">{{ item.change_type }}</span>
                <span class="canon-change-desc">{{ item.description }}</span>
              </div>
            </div>
          </div>
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
            <NTypewriter :text="sanitizedNarrativeText" :speed="35" />
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
              <p class="turn-content">{{ sanitizeDisplayText(rec.content) }}</p>
            </div>
          </div>
        </div>
      </div>

      <!-- Bangui shortcut bar -->
      <div class="bangui-bar">
        <div class="bangui-bar-header">
          <span class="bangui-title">帮回指令</span>
          <span class="bangui-subtitle">用于卡顿解套、抬压、补反馈或快速推进，不会替换你的输入权限。</span>
        </div>
        <button
          v-for="(btn, i) in banguiButtons"
          :key="i"
          class="bangui-btn"
          :class="{
            'active-bangui': activeBangui === btn.trigger,
            'disabled-bangui': store.phase === 'INTERRUPT' && activeBangui !== btn.trigger,
          }"
          :title="`${btn.label}：${btn.description}`"
          :aria-label="`${btn.label}：${btn.description}`"
          :style="{ pointerEvents: store.phase === 'INTERRUPT' && activeBangui !== btn.trigger ? 'none' : 'auto' }"
          @click="triggerBangui(btn.trigger)"
        >
          <span class="bangui-btn-label">{{ btn.label }}</span>
          <span class="bangui-btn-desc">{{ btn.description }}</span>
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
              <input type="radio" v-model="rollbackSteps" :value="CUSTOM_ROLLBACK_VALUE" />
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
        <div class="modal-box end-modal preview-modal">
          <h3>结束前归档预览</h3>
          <p>确认着陆前，先检查三种归档结果。当前会话尚未结束。</p>
          <div v-if="previewLoading" class="preview-loading">正在生成归档预览…</div>
          <div v-else-if="modalArchivePreview" class="archive-preview-block compact">
            <div class="archive-tabs">
              <button
                v-for="tab in archiveTabs"
                :key="tab.key"
                class="archive-tab"
                :class="{ active: archivePreviewTab === tab.key }"
                @click="archivePreviewTab = tab.key"
              >
                {{ tab.label }}
              </button>
            </div>

            <div v-if="archivePreviewTab === 'session_only'" class="archive-preview-card">
              <div class="preview-title">会话归档</div>
              <p class="preview-summary">{{ modalSessionOnlyText || '本次会话将仅归档为互动记录。' }}</p>
              <div v-if="modalArchivePreview.preview_session_only.character_changes.length" class="canon-change-list">
                <div
                  v-for="item in modalArchivePreview.preview_session_only.character_changes"
                  :key="item.name"
                  class="canon-change-item"
                >
                  <span class="canon-change-type">{{ item.name }}</span>
                  <span class="canon-change-desc">{{ item.change }}</span>
                </div>
              </div>
            </div>

            <div v-else-if="archivePreviewTab === 'draft_chapter'" class="archive-preview-card">
              <div class="preview-title">章节草稿</div>
              <div class="preview-metric-row">
                <span>预计字数</span>
                <strong>{{ modalArchivePreview.preview_draft_chapter.word_count }}</strong>
              </div>
              <div class="preview-metric-row">
                <span>质量评估</span>
                <strong>{{ modalArchivePreview.preview_draft_chapter.quality_estimate || '待评估' }}</strong>
              </div>
              <p class="preview-excerpt">{{ modalArchivePreview.preview_draft_chapter.excerpt || '暂无可预览正文。' }}</p>
            </div>

            <div v-else class="archive-preview-card">
              <div class="preview-title">正史审批</div>
              <p class="preview-summary">该模式会生成待审批变更集，需要二次确认后才能回流正史。</p>
              <div class="preview-chip-row">
                <span
                  v-for="field in modalArchivePreview.preview_canon_chapter.approval_required_fields"
                  :key="field"
                  class="preview-chip warning"
                >
                  {{ field }}
                </span>
              </div>
              <div v-if="modalArchivePreview.preview_canon_chapter.pending_changes.length" class="canon-change-list">
                <div
                  v-for="(item, index) in modalArchivePreview.preview_canon_chapter.pending_changes"
                  :key="`${item.change_type}-${index}`"
                  class="canon-change-item"
                >
                  <span class="canon-change-type">{{ item.change_type }}</span>
                  <span class="canon-change-desc">{{ item.description }}</span>
                </div>
              </div>
            </div>
          </div>
          <p v-else class="preview-loading">归档预览暂不可用，仍可直接结束会话。</p>
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
                <span class="sl-turn">回合 {{ displayTurn(s.turn) }}</span>
                <span class="sl-ts">{{ s.timestamp.slice(0, 16) }}</span>
                <span class="sl-pressure">压力 {{ s.scene_pressure?.toFixed(1) }}</span>
              </div>
              <div class="sl-actions">
                <button class="n-btn primary sm" @click="doLoadSave(s)">读档</button>
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
import type { ArchivePreviewResponse } from '@/types/session'

interface PreviewSessionOnlyModel {
  summary: string
  memory_anchors: Array<{ label: string; source: string; importance?: number | null }>
  character_changes: Array<{ name: string; change: string; actions_count: number; final_pressure?: number | null }>
  projected_changeset_status: string
}

interface PreviewDraftChapterModel {
  chapter_text: string
  excerpt: string
  word_count: number
  quality_estimate: string
}

interface PreviewCanonChangeModel {
  change_type: string
  description: string
  tag: string
  chapter: number
  before_snapshot?: Record<string, unknown> | null
  after_value?: Record<string, unknown>
}

interface PreviewCanonChapterModel {
  draft_content: string
  pending_changes: PreviewCanonChangeModel[]
  approval_required_fields: string[]
  requires_confirmation: boolean
  projected_changeset_status: string
}

interface ArchivePreviewModel {
  session_id: string
  preview_session_only: PreviewSessionOnlyModel
  preview_draft_chapter: PreviewDraftChapterModel
  preview_canon_chapter: PreviewCanonChapterModel
}

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
const CUSTOM_ROLLBACK_VALUE = -1
const rollbackSteps = ref<number>(1)
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
type ArchiveTabKey = 'session_only' | 'draft_chapter' | 'canon_chapter'
const archivePreviewTab = ref<ArchiveTabKey>('session_only')
const archivePreview = ref<ArchivePreviewModel | null>(null)
const previewLoading = ref(false)
const archiveTabs: Array<{ key: ArchiveTabKey; label: string }> = [
  { key: 'session_only', label: '会话归档' },
  { key: 'draft_chapter', label: '章节草稿' },
  { key: 'canon_chapter', label: '正史审批' },
]

function emptyArchivePreview(): ArchivePreviewModel {
  return {
    session_id: '',
    preview_session_only: {
      summary: '',
      memory_anchors: [],
      character_changes: [],
      projected_changeset_status: 'runtime_only',
    },
    preview_draft_chapter: {
      chapter_text: '',
      excerpt: '',
      word_count: 0,
      quality_estimate: '',
    },
    preview_canon_chapter: {
      draft_content: '',
      pending_changes: [],
      approval_required_fields: [],
      requires_confirmation: true,
      projected_changeset_status: 'canon_pending',
    },
  }
}

function normalizeArchivePreview(
  preview: Partial<ArchivePreviewResponse> | null | undefined,
): ArchivePreviewModel {
  const fallback = emptyArchivePreview()
  const previewSessionOnly: Partial<PreviewSessionOnlyModel> = preview?.preview_session_only ?? {}
  const previewDraftChapter: Partial<PreviewDraftChapterModel> = preview?.preview_draft_chapter ?? {}
  const previewCanonChapter: Partial<PreviewCanonChapterModel> = preview?.preview_canon_chapter ?? {}
  return {
    session_id: preview?.session_id ?? fallback.session_id,
    preview_session_only: {
      summary: previewSessionOnly.summary ?? fallback.preview_session_only.summary,
      memory_anchors: previewSessionOnly.memory_anchors ?? fallback.preview_session_only.memory_anchors,
      character_changes: previewSessionOnly.character_changes ?? fallback.preview_session_only.character_changes,
      projected_changeset_status:
        previewSessionOnly.projected_changeset_status ?? fallback.preview_session_only.projected_changeset_status,
    },
    preview_draft_chapter: {
      chapter_text: previewDraftChapter.chapter_text ?? fallback.preview_draft_chapter.chapter_text,
      excerpt: previewDraftChapter.excerpt ?? fallback.preview_draft_chapter.excerpt,
      word_count: previewDraftChapter.word_count ?? fallback.preview_draft_chapter.word_count,
      quality_estimate: previewDraftChapter.quality_estimate ?? fallback.preview_draft_chapter.quality_estimate,
    },
    preview_canon_chapter: {
      draft_content: previewCanonChapter.draft_content ?? fallback.preview_canon_chapter.draft_content,
      pending_changes: previewCanonChapter.pending_changes ?? fallback.preview_canon_chapter.pending_changes,
      approval_required_fields:
        previewCanonChapter.approval_required_fields ?? fallback.preview_canon_chapter.approval_required_fields,
      requires_confirmation:
        previewCanonChapter.requires_confirmation ?? fallback.preview_canon_chapter.requires_confirmation,
      projected_changeset_status:
        previewCanonChapter.projected_changeset_status ?? fallback.preview_canon_chapter.projected_changeset_status,
    },
  }
}

interface ToastItem { id: number; type: 'info' | 'warning' | 'error' | 'success'; message: string }
const toasts = ref<ToastItem[]>([])
let toastSeq = 0
function pushToast(type: ToastItem['type'], message: string, duration = 4000) {
  const id = ++toastSeq
  toasts.value.push({ id, type, message })
  setTimeout(() => { toasts.value = toasts.value.filter(t => t.id !== id) }, duration)
}

function displayTurn(turn: number | null | undefined) {
  const turnValue = Number(turn)
  if (!Number.isFinite(turnValue) || turnValue <= 0) return 0
  return Math.floor((turnValue + 1) / 2)
}

const latestNarrativeFromHistory = computed(() => {
  for (let i = store.history.length - 1; i >= 0; i--) {
    const record = store.history[i] as Record<string, unknown>
    if (record.rolled_back) continue
    if (record.who && record.who !== 'dm') continue
    if (typeof record.content === 'string' && record.content.trim()) {
      return record.content
    }
  }
  return ''
})

function syncNarrativeFromHistory(forceEmpty = false) {
  const nextNarrative = latestNarrativeFromHistory.value
  if (!nextNarrative && !forceEmpty) return
  if (narrativeText.value !== nextNarrative) {
    narrativeText.value = nextNarrative
    scrollNarrative()
  }
}

function applyLoadedSaveState(restoredTurn: number, save?: SaveEntry) {
  store.turn = displayTurn(restoredTurn)
  store.phase = 'PING_PONG'
  if (typeof save?.scene_pressure === 'number') {
    store.scenePressure = save.scene_pressure
  }
  store.history = store.history.map((record) => ({
    ...record,
    rolled_back: record.turn_id >= restoredTurn,
  }))
  syncNarrativeFromHistory(true)
}

// WebSocket
let ws: WebSocket | null = null
let wsRetries = 0
const maxWsRetries = 3
let wsReconnectTimer: number | null = null
let wsOpenedAt = 0
let shouldReconnectWs = false

function resolveBackendWsUrl(sessionId: string) {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  if (import.meta.env.DEV) {
    const apiPort = String(import.meta.env.VITE_API_PORT || '8000')
    return `${proto}://${location.hostname}:${apiPort}/ws/sessions/${sessionId}`
  }
  return `${proto}://${location.host}/ws/sessions/${sessionId}`
}

function disconnectWs(manual = true) {
  if (manual) shouldReconnectWs = false
  if (wsReconnectTimer !== null) {
    window.clearTimeout(wsReconnectTimer)
    wsReconnectTimer = null
  }
  if (ws) {
    const activeWs = ws
    ws = null
    activeWs.close()
  }
}

function connectWs() {
  if (!store.sessionId) return
  disconnectWs(false)
  shouldReconnectWs = true
  const url = resolveBackendWsUrl(store.sessionId)
  ws = new WebSocket(url)

  ws.onopen = () => { wsOpenedAt = Date.now() }

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
          syncNarrativeFromHistory()
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
        disconnectWs()
      }
    } catch { /* ignore malformed */ }
  }

  ws.onclose = () => {
    ws = null
    if (!shouldReconnectWs || store.phase === 'ENDED') return
    const connectionLifetime = wsOpenedAt ? Date.now() - wsOpenedAt : 0
    if (connectionLifetime > 1500) {
      wsRetries = 0
    }
    if (wsRetries >= maxWsRetries) {
      shouldReconnectWs = false
      pushToast('warning', 'TRPG 实时流连接已断开，已切换为非流式交互。')
      return
    }
    const delay = Math.min(1000 * 2 ** wsRetries, 8000)
    wsRetries++
    wsReconnectTimer = window.setTimeout(() => {
      wsReconnectTimer = null
      connectWs()
    }, delay)
  }
}

async function startSession() {
  disconnectWs()
  await store.createSession({ project_id: projectId.value })
  if (store.sessionId) {
    syncNarrativeFromHistory(true)
    latestDecisionType.value = 'action'
    latestRiskLevels.value = []
    connectWs()
  }
}

async function submitAction(rawText: string) {
  const text = rawText.trim()
  if (!text || store.loading) return
  inputText.value = ''
  await store.sendStep(text)
  scrollHistory()
}

async function sendAction() {
  await submitAction(inputText.value)
}

async function selectOption(opt: string) {
  await submitAction(opt)
}

async function handleOptionClick(opt: string, idx: number) {
  const risk = latestRiskLevels.value[idx] ?? 'safe'
  if (risk === 'dangerous') {
    dangerConfirm.value = { opt, idx }
  } else {
    await selectOption(opt)
  }
}

async function confirmDangerous() {
  if (dangerConfirm.value) {
    const opt = dangerConfirm.value.opt
    dangerConfirm.value = null
    await selectOption(opt)
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
  const steps = rollbackSteps.value === CUSTOM_ROLLBACK_VALUE ? customSteps.value : rollbackSteps.value
  showRollbackModal.value = false
  await store.rollback(steps)
}

async function loadArchivePreview() {
  if (!store.sessionId) {
    archivePreview.value = null
    return
  }
  previewLoading.value = true
  try {
    const res = await sessionsApi.previewArchives(store.sessionId)
    archivePreview.value = normalizeArchivePreview(res.data)
  } catch {
    archivePreview.value = null
    pushToast('warning', '无法加载归档预览，将允许直接结束会话')
  } finally {
    previewLoading.value = false
  }
}

async function confirmEnd() {
  archivePreviewTab.value = 'session_only'
  showEndModal.value = true
  await loadArchivePreview()
}

async function doEndSession() {
  showEndModal.value = false
  await store.endSession()
}

// Phase 3: SL functions
async function doCreateSave() {
  if (!store.sessionId) return
  try {
    const res = await sessionsApi.createSave(projectId.value, store.sessionId, 'manual')
    pushToast('success', `存档成功 (回合 ${displayTurn(res.data.turn)})`)
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

async function doLoadSave(save: SaveEntry) {
  if (!store.sessionId) return
  try {
    const res = await sessionsApi.loadSave(projectId.value, store.sessionId, save.save_id)
    showSLModal.value = false
    applyLoadedSaveState(res.data.restored_turn, save)
    pushToast('success', `已读档至回合 ${displayTurn(res.data.restored_turn)}`)
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

function sanitizeDisplayText(text: unknown) {
  if (typeof text !== 'string') return ''
  return text.replace(/\*\*/g, '')
}

function sanitizeSummaryText(text: unknown, maxLength = 220) {
  const cleaned = sanitizeDisplayText(text)
    .replace(/\|/g, ' ')
    .replace(/(?:\[选项\s*[A-Z]\][\s\S]*)$/g, '')
    .replace(/\s+/g, ' ')
    .trim()

  if (!cleaned) {
    return ''
  }

  if (cleaned.length <= maxLength) {
    return cleaned
  }

  return `${cleaned.slice(0, maxLength).trim()}…`
}

function normalizeDecisionOption(option: unknown) {
  return sanitizeDisplayText(option)
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[。；;，,\s]+$/g, '')
    .trim()
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

watch(latestNarrativeFromHistory, (text) => {
  if (text) {
    syncNarrativeFromHistory()
    return
  }
  if (!store.sessionId) {
    syncNarrativeFromHistory(true)
  }
}, { immediate: true })

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

function extractDecisionOptions(content: string) {
  const normalized = content.replace(/\r/g, ' ').replace(/\n+/g, ' ')
  const options: string[] = []
  const optionPattern = /(?:\*\*)?\[选项\s*[A-Z]\](?:\*\*)?\s*[：:]\s*([\s\S]*?)(?=(?:\*\*)?\[选项\s*[A-Z]\](?:\*\*)?\s*[：:]|$)/g

  let match: RegExpExecArray | null = null
  while ((match = optionPattern.exec(normalized)) !== null) {
    const optionText = normalizeDecisionOption(match[1])
    if (optionText) {
      options.push(optionText)
    }
  }

  return options
}

const sanitizedNarrativeText = computed(() => sanitizeDisplayText(narrativeText.value))

// Latest DM options
const latestOptions = computed(() => {
  for (let i = store.history.length - 1; i >= 0; i--) {
    const r = store.history[i] as Record<string, unknown>
    if (r.rolled_back) continue
    if (r.has_decision && (r.decision_options as unknown[])?.length) {
      return (r.decision_options as unknown[])
        .map(normalizeDecisionOption)
        .filter((option): option is string => Boolean(option))
    }
    if (typeof r.content === 'string') {
      const parsedOptions = extractDecisionOptions(r.content)
      if (parsedOptions.length) {
        return parsedOptions
      }
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

const summaryArchivePreview = computed(() => {
  if (!store.summary) return null
  return normalizeArchivePreview({
    session_id: '',
    preview_session_only: store.summary.preview_session_only,
    preview_draft_chapter: store.summary.preview_draft_chapter,
    preview_canon_chapter: store.summary.preview_canon_chapter,
  })
})

const summaryHookText = computed(() => sanitizeSummaryText(store.summary?.next_hook, 280))

const summarySessionOnlyText = computed(() =>
  sanitizeSummaryText(summaryArchivePreview.value?.preview_session_only.summary, 140),
)

const summaryDraftExcerptText = computed(() =>
  sanitizeSummaryText(summaryArchivePreview.value?.preview_draft_chapter.excerpt, 180),
)

const modalArchivePreview = computed(() => archivePreview.value)

const modalSessionOnlyText = computed(() =>
  sanitizeSummaryText(modalArchivePreview.value?.preview_session_only.summary, 140),
)

// Bangui 8 buttons
const banguiButtons = [
  { trigger: '帮回主动1', label: '主动介入', description: '立刻插入外部动作，打破僵局' },
  { trigger: '帮回主动2', label: '主动施压', description: '让 NPC 或局势先出招，快速抬压' },
  { trigger: '帮回被动1', label: '被动回应', description: '顺着当前行动，给出明确反馈' },
  { trigger: '帮回被动2', label: '被动揭示', description: '补充线索、后果或隐藏反应' },
  { trigger: '帮回黑暗1', label: '黑暗压迫', description: '提高代价、风险和压迫感' },
  { trigger: '帮回黑暗2', label: '黑暗扭转', description: '引入反噬、恶意变化或失控感' },
  { trigger: '帮回推进1', label: '快速推进', description: '跳过拉扯，直接推进到下一节点' },
  { trigger: '帮回推进2', label: '抛出钩子', description: '给出新目标、新人物或新冲突' },
]

onUnmounted(() => {
  disconnectWs()
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

.session-summary {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: var(--spacing-lg);
}

.summary-card {
  width: min(760px, 100%);
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  padding: var(--spacing-lg);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.summary-title {
  margin: 0 0 var(--spacing-xs);
  color: var(--color-text-primary);
}

.summary-row,
.preview-metric-row {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-md);
  color: var(--color-text-secondary);
}

.summary-hook,
.summary-delta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.hook-label,
.delta-label,
.preview-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.hook-text,
.delta-item,
.preview-summary,
.preview-excerpt {
  margin: 0;
  color: var(--color-text-primary);
  line-height: 1.7;
}

.summary-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.archive-preview-block {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  margin-top: var(--spacing-sm);
}

.archive-preview-block.compact {
  margin-top: var(--spacing-md);
}

.archive-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.archive-tab {
  border: 1px solid var(--color-surface-l2);
  background: var(--color-surface-l2);
  color: var(--color-text-secondary);
  border-radius: 999px;
  padding: 6px 12px;
  cursor: pointer;
}

.archive-tab.active {
  color: var(--color-text-primary);
  border-color: var(--color-ai-active);
  background: color-mix(in srgb, var(--color-ai-active) 18%, var(--color-surface-l2));
}

.archive-preview-card {
  border: 1px solid var(--color-surface-l2);
  background: var(--color-base);
  border-radius: var(--radius-card);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.preview-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.preview-chip {
  padding: 4px 10px;
  border-radius: 999px;
  background: var(--color-surface-l2);
  color: var(--color-text-secondary);
  font-size: 12px;
}

.preview-chip.warning {
  background: color-mix(in srgb, var(--color-warning) 18%, var(--color-surface-l2));
  color: var(--color-text-primary);
}

.canon-change-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.canon-change-item {
  display: grid;
  grid-template-columns: 140px 1fr;
  gap: 10px;
  padding: 10px 12px;
  border-radius: var(--radius-btn);
  background: var(--color-surface-l1);
}

.canon-change-type {
  color: var(--color-ai-active);
  font-size: 12px;
  font-weight: 600;
  word-break: break-word;
}

.canon-change-desc {
  color: var(--color-text-primary);
  line-height: 1.6;
}

.preview-loading {
  margin: 0;
  color: var(--color-text-secondary);
}

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
.bangui-bar-header {
  grid-column: 1 / -1;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.bangui-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-primary);
}
.bangui-subtitle {
  font-size: 12px;
  color: var(--color-text-secondary);
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
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 72px;
}
.bangui-btn-label { font-size: 13px; font-weight: 700; }
.bangui-btn-desc { font-size: 12px; line-height: 1.4; color: var(--color-text-secondary); }
.bangui-btn:hover { border-color: var(--color-hitl); color: var(--color-hitl); }
.bangui-btn:hover .bangui-btn-desc { color: var(--color-text-primary); }
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

