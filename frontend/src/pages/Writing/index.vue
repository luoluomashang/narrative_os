<template>
  <div class="writing-page app-page-surface">
    <SystemPageHeader
      eyebrow="Writing Workbench"
      title="创作主工作台"
      description="把世界、角色、Hook 和运行链路收进单主任务界面，减少章节生成前的上下文断裂。"
    >
      <template #meta>
        <span class="meta-pill">项目 {{ projectId }}</span>
        <span class="meta-pill">待确认变更 {{ writingContext.pending_changes_count }}</span>
        <span class="meta-pill">章节 {{ currentChapter }}</span>
        <span class="meta-pill">目标 {{ wordCountTarget }} 字</span>
      </template>
      <template #actions>
        <SystemButton variant="ghost" @click="refreshWorkbench">刷新</SystemButton>
        <SystemButton variant="secondary" @click="contextDrawerOpen = true">上下文</SystemButton>
        <SystemButton variant="quiet" @click="operationsTrayOpen = true">
          运行托盘
        </SystemButton>
      </template>
    </SystemPageHeader>

    <SystemStatusBanner
      v-if="failedErrorPrechecks.length"
      status="blocking"
      title="生成前存在阻塞项"
      :message="generationBlockReason || '请先处理错误级前置检查后再开始生成。'"
      description="阻塞项会直接拦截主流程，已把跳转入口收敛到这里。"
    >
      <template #actions>
        <SystemButton v-if="primaryPrecheckActionPath" variant="primary" @click="goTo(primaryPrecheckActionPath)">处理阻塞项</SystemButton>
        <SystemButton variant="ghost" @click="contextDrawerOpen = true">查看全部前置检查</SystemButton>
      </template>
    </SystemStatusBanner>

    <SystemStatusBanner
      v-else-if="failedWarningPrechecks.length && !forceGenerate"
      status="partial-failure"
      title="生成前仍有待确认项"
      :message="generationBlockReason || '当前有 warning 级前置检查，确认后才建议继续生成。'"
      description="你仍可切换为强制生成，但建议先确认上下文和依赖是否齐备。"
    >
      <template #actions>
        <SystemButton v-if="primaryPrecheckActionPath" variant="ghost" @click="goTo(primaryPrecheckActionPath)">前往处理</SystemButton>
        <SystemButton variant="quiet" @click="contextDrawerOpen = true">查看详情</SystemButton>
      </template>
    </SystemStatusBanner>

    <div class="writing-layout">
      <main class="main-column">
        <section class="composer panel-shell">
          <div class="section-head">
            <h2>章节生成</h2>
            <div class="control-row">
              <label class="field compact-field">
                <span>章节</span>
                <input v-model.number="currentChapter" type="number" min="1" max="9999" />
              </label>
              <label class="field compact-field">
                <span>目标字数</span>
                <input v-model.number="wordCountTarget" type="number" min="500" max="20000" step="100" />
              </label>
            </div>
          </div>

          <label class="field">
            <span>本章摘要</span>
            <textarea
              v-model="targetSummary"
              rows="4"
              placeholder="输入本章要解决的情节、冲突和情绪目标"
            />
          </label>

          <div class="control-row lower-row">
            <label class="toggle-row">
              <input v-model="forceGenerate" type="checkbox" />
              <span>强制生成（忽略 warning 类前置检查）</span>
            </label>
            <div class="action-row">
              <SystemButton variant="secondary" :disabled="busy || !hasTargetSummary" @click="planOnly">
                {{ planning ? '规划中…' : '仅规划' }}
              </SystemButton>
              <SystemButton variant="primary" :disabled="busy || !canGenerate" @click="generate">
                {{ generating ? '生成中…' : '开始生成' }}
              </SystemButton>
            </div>
          </div>
          <p v-if="generationBlockReason" class="precheck-hint">
            当前不可生成：{{ generationBlockReason }}
          </p>
        </section>

        <section class="output-shell panel-shell">
          <div class="section-head">
            <h2>生成结果</h2>
            <div class="hero-meta">
              <span class="meta-pill">run {{ currentRunId || '未建立' }}</span>
              <span class="meta-pill">{{ runStatusLabel }}</span>
              <span v-if="hasBenchmarkScore" class="meta-pill meta-pill-score">
                对标贴合 {{ formatPercent(benchmarkAdherenceScore) }}
              </span>
              <span v-if="hasBenchmarkScore" class="meta-pill meta-pill-score">
                人味 {{ formatPercent(benchmarkHumannessScore) }}
              </span>
            </div>
          </div>
          <p v-if="errorMessage" class="error-banner">{{ errorMessage }}</p>
          <div v-if="benchmarkViolations.length" class="benchmark-warning">
            <strong>对标回归提示</strong>
            <p>{{ benchmarkViolations.join(' / ') }}</p>
          </div>
          <pre v-else class="output-text">{{ generatedText || '生成结果会显示在这里。' }}</pre>
        </section>

      </main>
    </div>

    <SystemDrawer
      v-model="contextDrawerOpen"
      title="写作上下文"
      description="把前置检查、WorldState 和角色 Runtime 收进独立上下文抽屉，避免与主任务争抢首屏。"
      size="420px"
    >
      <div class="section-head">
        <h2>前置检查</h2>
        <SystemButton variant="ghost" size="sm" @click="refreshWorkbench">刷新</SystemButton>
      </div>

      <div class="precheck-stack">
        <article
          v-for="item in writingContext.prechecks"
          :key="item.key"
          class="precheck-card"
          :class="item.passed ? 'precheck-pass' : `precheck-${item.severity}`"
        >
          <div>
            <strong>{{ item.passed ? '已满足' : '需处理' }}</strong>
            <p>{{ item.message }}</p>
          </div>
          <SystemButton v-if="item.action_path" variant="ghost" size="sm" @click="goTo(item.action_path)">
            前往
          </SystemButton>
        </article>
      </div>

      <div class="section-head compact context-section-head">
        <h2>WorldState</h2>
        <span class="status-chip" :class="writingContext.world.published ? 'ok' : 'warn'">
          {{ writingContext.world.published ? '已发布' : '未发布' }}
        </span>
      </div>
      <div class="summary-grid">
        <div class="summary-card">
          <h3>势力 Top 5</h3>
          <p>{{ joinOrFallback(writingContext.world.factions, '暂无势力摘要') }}</p>
        </div>
        <div class="summary-card">
          <h3>地区 Top 5</h3>
          <p>{{ joinOrFallback(writingContext.world.regions, '暂无地区摘要') }}</p>
        </div>
        <div class="summary-card">
          <h3>规则 Top 5</h3>
          <p>{{ joinOrFallback(writingContext.world.rules, '暂无规则摘要') }}</p>
        </div>
      </div>

      <div class="section-head compact context-section-head">
        <h2>角色 Runtime</h2>
        <span>{{ writingContext.characters.length }} 人</span>
      </div>
      <div class="character-stack">
        <article v-for="character in writingContext.characters" :key="character.name" class="character-card">
          <div class="character-topline">
            <h3>{{ character.name }}</h3>
            <span>{{ pressureLabel(character.current_pressure) }}</span>
          </div>
          <p><strong>位置：</strong>{{ character.current_location || '未标注' }}</p>
          <p><strong>Agenda：</strong>{{ character.current_agenda || '未标注' }}</p>
          <p><strong>最近事件：</strong>{{ joinOrFallback(character.recent_key_events, '暂无关键事件') }}</p>
        </article>
        <p v-if="writingContext.characters.length === 0" class="empty-copy">当前没有可展示的角色 Runtime 信息。</p>
      </div>
    </SystemDrawer>

    <SystemDrawer
      v-model="operationsTrayOpen"
      title="运行托盘"
      description="把 Hook、Benchmark、Skill 与 AgentRun 收进辅助抽屉，避免和章节生成首屏争抢注意力。"
      size="460px"
    >
      <div class="section-head compact">
        <h2>运行摘要</h2>
        <span>{{ runStatusLabel }}</span>
      </div>
      <div class="summary-grid">
        <div class="summary-card">
          <h3>WorldState</h3>
          <p>{{ writingContext.world.published ? '已发布，可直接参与生成。' : '仍是草稿态，建议先发布后再生成。' }}</p>
        </div>
        <div class="summary-card">
          <h3>当前对标</h3>
          <p>{{ activeBenchmark?.profile_name || '未挂载 Benchmark。' }}</p>
        </div>
        <div class="summary-card">
          <h3>当前 Skill</h3>
          <p>{{ activeAuthorSkill?.profile_name || '未挂载 Author Skill。' }}</p>
        </div>
        <div class="summary-card">
          <h3>Token</h3>
          <p>输入 {{ tokenInTotal }} / 输出 {{ tokenOutTotal }}</p>
        </div>
      </div>

      <div class="prompt-ribbon">
        <div>
          <span class="ribbon-label">上一章 Hook</span>
          <p>{{ writingContext.previous_hook || '当前暂无上章 Hook。' }}</p>
        </div>
        <div>
          <span class="ribbon-label">当前卷目标</span>
          <p>{{ writingContext.current_volume_goal || '当前暂无卷目标。' }}</p>
        </div>
      </div>

      <div v-if="activeBenchmark" class="benchmark-ribbon">
        <div>
          <span class="ribbon-label">当前对标</span>
          <p>
            {{ activeBenchmark.profile_name }}
            <span class="benchmark-anchor-count">
              共 {{ activeBenchmark.active_scene_anchor_count }} 个场景锚点
            </span>
          </p>
        </div>
        <div>
          <span class="ribbon-label">Top Rules</span>
          <p>{{ joinOrFallback(activeBenchmark.top_rules, '当前对标尚未生成稳定规则摘要。') }}</p>
        </div>
      </div>

      <div v-if="activeAuthorSkill" class="skill-ribbon">
        <div>
          <span class="ribbon-label">当前 Skill</span>
          <p>
            {{ activeAuthorSkill.profile_name }}
            <span class="benchmark-anchor-count">
              {{ activeAuthorSkill.application_mode || activeAuthorSkill.mode }}
            </span>
          </p>
        </div>
        <div>
          <span class="ribbon-label">Scene Hints</span>
          <p>{{ joinOrFallback(activeAuthorSkill.scene_hints, '当前 Skill 尚未生成场景提示。') }}</p>
        </div>
        <div>
          <span class="ribbon-label">Anti Rules</span>
          <p>{{ joinOrFallback(activeAuthorSkill.anti_rules, '当前 Skill 尚未生成反向约束。') }}</p>
        </div>
      </div>

      <div class="section-head compact operation-tray-head">
        <h2>AgentRun</h2>
        <span>输入 {{ tokenInTotal }} / 输出 {{ tokenOutTotal }}</span>
      </div>
      <div class="step-grid">
        <article v-for="step in runSteps" :key="step.step_id" class="step-card" :class="step.statusClass">
          <div class="step-index">{{ step.step_index }}</div>
          <div>
            <h3>{{ step.agent_name }}</h3>
            <p>{{ step.statusLabel }}</p>
            <small>{{ step.tokenLabel }}</small>
          </div>
        </article>
        <p v-if="runSteps.length === 0" class="empty-copy">当前暂无执行链路，生成章节后会显示 5 步 Agent 进度。</p>
      </div>
    </SystemDrawer>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import client from '@/api/client'
import { chapters } from '@/api/chapters'
import { projects } from '@/api/projects'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'

type PrecheckItem = {
  key: string
  passed: boolean
  severity: string
  message: string
  action_path?: string | null
}

type WritingContextPayload = {
  project_id: string
  chapter: number
  previous_hook: string
  current_volume_goal: string
  pending_changes_count: number
  active_benchmark?: {
    profile_id: string
    profile_name: string
    mode: string
    top_rules: string[]
    active_scene_anchor_count: number
    anti_rules?: string[]
    scene_hints?: string[]
    application_mode?: string | null
  } | null
  active_author_skill?: {
    profile_id: string
    profile_name: string
    mode: string
    top_rules: string[]
    anti_rules?: string[]
    scene_hints?: string[]
    active_scene_anchor_count: number
    application_mode?: string | null
  } | null
  world: {
    published: boolean
    factions: string[]
    regions: string[]
    rules: string[]
  }
  characters: Array<{
    name: string
    current_location: string
    current_agenda: string
    current_pressure: number
    recent_key_events: string[]
  }>
  prechecks: PrecheckItem[]
}

type RunStepView = {
  step_id: string
  step_index: number
  agent_name: string
  statusClass: string
  statusLabel: string
  tokenIn: number
  tokenOut: number
  tokenLabel: string
}

type PlanNodeView = {
  id?: string
  type?: string
  summary?: string
  tension?: number
  characters?: string[]
}

type PlanResponseView = {
  chapter_outline: string
  planned_nodes: PlanNodeView[]
  dialogue_goals: string[]
  hook_suggestion: string
  hook_type: string
  tension_curve: number[]
}

type RunChapterResult = {
  text: string
  run_id?: string
  benchmark_adherence_score?: number | null
  benchmark_humanness_score?: number | null
  benchmark_violations?: string[]
}

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)

const currentChapter = ref(Number(route.query.chapter || 1) || 1)
const wordCountTarget = ref(2000)
const targetSummary = ref('')
const forceGenerate = ref(false)
const contextDrawerOpen = ref(false)
const operationsTrayOpen = ref(false)
const generating = ref(false)
const planning = ref(false)
const generatedText = ref('')
const errorMessage = ref('')
const currentRunId = ref('')
const runStatus = ref('idle')
const runSteps = ref<RunStepView[]>([])
const tokenInTotal = ref(0)
const tokenOutTotal = ref(0)
const benchmarkAdherenceScore = ref<number | null>(null)
const benchmarkHumannessScore = ref<number | null>(null)
const benchmarkViolations = ref<string[]>([])

const writingContext = ref<WritingContextPayload>({
  project_id: '',
  chapter: 1,
  previous_hook: '',
  current_volume_goal: '',
  pending_changes_count: 0,
  active_benchmark: null,
  active_author_skill: null,
  world: {
    published: false,
    factions: [],
    regions: [],
    rules: [],
  },
  characters: [],
  prechecks: [],
})

let pollTimer: number | null = null

const busy = computed(() => generating.value || planning.value)
const hasTargetSummary = computed(() => Boolean(targetSummary.value.trim()))
const activeBenchmark = computed(() => writingContext.value.active_benchmark ?? null)
const activeAuthorSkill = computed(() => writingContext.value.active_author_skill ?? null)
const failedErrorPrechecks = computed(() =>
  writingContext.value.prechecks.filter((item) => !item.passed && item.severity === 'error'),
)
const failedWarningPrechecks = computed(() =>
  writingContext.value.prechecks.filter((item) => !item.passed && item.severity !== 'error'),
)
const primaryPrecheckActionPath = computed(() =>
  failedErrorPrechecks.value.find((item) => item.action_path)?.action_path
  ?? failedWarningPrechecks.value.find((item) => item.action_path)?.action_path
  ?? null,
)
const generationBlockReason = computed(() => {
  if (failedErrorPrechecks.value.length) {
    return failedErrorPrechecks.value[0]?.message ?? '存在未处理的错误级前置检查'
  }
  if (!forceGenerate.value && failedWarningPrechecks.value.length) {
    return failedWarningPrechecks.value[0]?.message ?? '存在未处理的 warning 级前置检查'
  }
  return ''
})
const canGenerate = computed(() => hasTargetSummary.value && !generationBlockReason.value)
const hasBenchmarkScore = computed(
  () => benchmarkAdherenceScore.value !== null || benchmarkHumannessScore.value !== null,
)

const runStatusLabel = computed(() => {
  if (runStatus.value === 'planning') return '规划中'
  if (runStatus.value === 'running') return '运行中'
  if (runStatus.value === 'completed') return '已完成'
  if (runStatus.value === 'failed') return '失败'
  if (runStatus.value === 'paused') return '暂停中'
  return '未启动'
})

function joinOrFallback(values: string[] | null | undefined, fallback: string) {
  return values?.length ? values.join(' / ') : fallback
}

function pressureLabel(pressure: number) {
  if (pressure >= 0.75) return '高压'
  if (pressure >= 0.4) return '中压'
  return '低压'
}

function formatPercent(value: number | null) {
  if (value === null || Number.isNaN(value)) {
    return '--'
  }
  return `${Math.round(value * 100)}%`
}

function goTo(path: string) {
  router.push(path)
}

function resolveTargetSummary() {
  const summary = targetSummary.value.trim()
  if (summary) {
    return summary
  }
  errorMessage.value = '请先填写本章摘要'
  generatedText.value = ''
  runStatus.value = 'idle'
  return null
}

function decodeQuotedJsonString(value: string) {
  try {
    return JSON.parse(`"${value}"`) as string
  } catch {
    return value
  }
}

function extractOutlineText(outline: string) {
  const trimmed = outline.trim()
  if (!trimmed) {
    return ''
  }

  const unfenced = trimmed.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim()
  const candidates = [unfenced, trimmed]

  for (const candidate of candidates) {
    if (candidate.startsWith('{') && candidate.endsWith('}')) {
      try {
        const parsed = JSON.parse(candidate) as { outline?: unknown }
        if (typeof parsed.outline === 'string' && parsed.outline.trim()) {
          return parsed.outline.trim()
        }
      } catch {
        // Fall through to regex extraction below.
      }
    }
  }

  const outlineMatch = unfenced.match(/"outline"\s*:\s*"((?:\\.|[^\"])*)"/s)
  if (outlineMatch) {
    return decodeQuotedJsonString(outlineMatch[1]).trim()
  }

  return trimmed
}

function formatPlanNode(node: PlanNodeView, index: number) {
  const title = typeof node.summary === 'string' && node.summary.trim()
    ? node.summary.trim()
    : `节点 ${index + 1}`
  const type = typeof node.type === 'string' && node.type.trim() ? node.type.trim() : 'unknown'
  const tension = typeof node.tension === 'number' ? `${node.tension}/10` : '未标注'
  const characters = Array.isArray(node.characters) && node.characters.length
    ? node.characters.join('、')
    : '未指定'
  return `${index + 1}. [${type}] ${title} | 张力 ${tension} | 角色 ${characters}`
}

function formatPlanResponse(plan: PlanResponseView) {
  const lines: string[] = []
  const outline = extractOutlineText(plan.chapter_outline)

  if (outline) {
    lines.push('剧情骨架')
    lines.push(outline)
  }

  lines.push('')
  lines.push('规划节点')
  if (plan.planned_nodes.length) {
    lines.push(...plan.planned_nodes.map((node, index) => formatPlanNode(node, index)))
  } else {
    lines.push('暂无节点')
  }

  lines.push('')
  lines.push(`Hook 建议: ${plan.hook_suggestion || '暂无'}`)
  lines.push(`Hook 类型: ${plan.hook_type || '未知'}`)
  lines.push(`对话目标: ${plan.dialogue_goals.length ? plan.dialogue_goals.join(' / ') : '暂无'}`)
  lines.push(`张力曲线: ${plan.tension_curve.length ? plan.tension_curve.join(' → ') : '暂无'}`)

  return lines.join('\n').trim()
}

async function refreshWorkbench() {
  const [statusResp, contextResp] = await Promise.all([
    projects.status(projectId.value),
    chapters.writingContext(projectId.value, currentChapter.value),
  ])
  const statusData = statusResp.data as Record<string, unknown>
  const contextData = contextResp.data as WritingContextPayload
  writingContext.value = {
    ...contextData,
    pending_changes_count: Number(statusData.pending_changes_count ?? contextData.pending_changes_count ?? 0),
  }
}

async function hydrateRunTrace(runId: string) {
  const response = await client.get(`/runs/${runId}/steps`)
  const run = response.data as {
    status?: string
    steps?: Array<{
      step_id: string
      step_index: number
      agent_name: string
      status: string
      artifact?: { token_in?: number; token_out?: number }
    }>
  }

  currentRunId.value = runId
  runStatus.value = run.status ?? 'idle'

  let totalIn = 0
  let totalOut = 0
  runSteps.value = (run.steps ?? []).map((step) => {
    const tokenIn = Number(step.artifact?.token_in ?? 0)
    const tokenOut = Number(step.artifact?.token_out ?? 0)
    totalIn += tokenIn
    totalOut += tokenOut
    return {
      step_id: step.step_id,
      step_index: step.step_index,
      agent_name: step.agent_name,
      statusClass: `step-${step.status}`,
      statusLabel: step.status,
      tokenIn,
      tokenOut,
      tokenLabel: `${tokenIn}/${tokenOut} tokens`,
    }
  })
  tokenInTotal.value = totalIn
  tokenOutTotal.value = totalOut
}

async function discoverLatestRun() {
  const response = await client.get(`/projects/${projectId.value}/runs`)
  const items = ((response.data as { items?: Array<Record<string, unknown>> }).items ?? [])
  const candidate = items.find((item) => Number(item.chapter_num ?? 0) === currentChapter.value)
  if (candidate?.run_id) {
    await hydrateRunTrace(String(candidate.run_id))
  }
}

function stopPolling() {
  if (pollTimer !== null) {
    window.clearInterval(pollTimer)
    pollTimer = null
  }
}

function startPolling() {
  stopPolling()
  pollTimer = window.setInterval(async () => {
    try {
      if (!currentRunId.value) {
        await discoverLatestRun()
      } else {
        await hydrateRunTrace(currentRunId.value)
      }
      if (!generating.value && runStatus.value !== 'running') {
        stopPolling()
      }
    } catch {
      // ignore polling noise while the request is still running
    }
  }, 1000)
}

async function generate() {
  const summary = resolveTargetSummary()
  if (!summary) return
  if (generationBlockReason.value) {
    errorMessage.value = `无法开始生成：${generationBlockReason.value}`
    runStatus.value = 'failed'
    return
  }

  errorMessage.value = ''
  generatedText.value = ''
  currentRunId.value = ''
  runSteps.value = []
  tokenInTotal.value = 0
  tokenOutTotal.value = 0
  benchmarkAdherenceScore.value = null
  benchmarkHumannessScore.value = null
  benchmarkViolations.value = []
  generating.value = true
  runStatus.value = 'running'
  startPolling()

  try {
    const response = await chapters.run({
      chapter: currentChapter.value,
      volume: 1,
      target_summary: summary,
      word_count_target: wordCountTarget.value,
      strategy: 'COST_OPTIMIZED',
      previous_hook: writingContext.value.previous_hook || '',
      existing_arc_summary: '',
      project_id: projectId.value,
      force_generate: forceGenerate.value,
    })
    const result = response.data as RunChapterResult
    generatedText.value = result.text
    benchmarkAdherenceScore.value = result.benchmark_adherence_score ?? null
    benchmarkHumannessScore.value = result.benchmark_humanness_score ?? null
    benchmarkViolations.value = result.benchmark_violations ?? []
    if (result.run_id) {
      await hydrateRunTrace(result.run_id)
    }
    await refreshWorkbench()
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    errorMessage.value = err.response?.data?.detail ?? err.message ?? '章节生成失败'
    runStatus.value = 'failed'
    benchmarkAdherenceScore.value = null
    benchmarkHumannessScore.value = null
    benchmarkViolations.value = []
  } finally {
    generating.value = false
    if (currentRunId.value) {
      await hydrateRunTrace(currentRunId.value)
    }
    stopPolling()
  }
}

async function planOnly() {
  const summary = resolveTargetSummary()
  if (!summary) return

  errorMessage.value = ''
  generatedText.value = '规划中…'
  benchmarkAdherenceScore.value = null
  benchmarkHumannessScore.value = null
  benchmarkViolations.value = []
  planning.value = true
  runStatus.value = 'planning'
  try {
    const response = await chapters.plan({
      chapter: currentChapter.value,
      volume: 1,
      target_summary: summary,
      word_count_target: wordCountTarget.value,
      previous_hook: writingContext.value.previous_hook || '',
      project_id: projectId.value,
    })
    generatedText.value = formatPlanResponse(response.data as PlanResponseView)
    runStatus.value = 'completed'
  } catch (error: unknown) {
    const err = error as { response?: { data?: { detail?: string } }; message?: string }
    errorMessage.value = err.response?.data?.detail ?? err.message ?? '章节规划失败'
    generatedText.value = ''
    runStatus.value = 'failed'
  } finally {
    planning.value = false
  }
}

watch(currentChapter, async () => {
  await refreshWorkbench()
})

onMounted(async () => {
  await refreshWorkbench()
})

onBeforeUnmount(() => {
  stopPolling()
})
</script>

<style scoped>
.writing-page {
  display: grid;
  gap: var(--spacing-5);
  min-height: 100%;
  align-content: start;
}

.panel-shell {
  border: 1px solid var(--color-border-subtle);
  border-radius: 24px;
  background: color-mix(in srgb, var(--color-surface-1) 92%, transparent);
  box-shadow: var(--shadow-md);
}

.hero-meta {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.meta-pill,
.status-chip {
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  background: var(--color-surface-2);
  color: var(--color-text-1);
}

.meta-pill-benchmark {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.meta-pill-skill {
  background: var(--color-info-soft);
  color: var(--color-info);
}

.meta-pill-score {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.status-chip.ok {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.status-chip.warn {
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.writing-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
}

.composer,
.output-shell {
  padding: 22px;
}

.main-column {
  display: grid;
  gap: 18px;
}

.operation-tray-head {
  margin-top: 8px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border-subtle);
}

.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
}

.section-head.compact {
  margin-bottom: 12px;
}

.section-head h2,
.summary-card h3,
.character-card h3,
.step-card h3 {
  margin: 0;
  color: var(--color-text-1);
}

.precheck-hint {
  margin: 12px 0 0;
  color: var(--color-warning);
  font-size: 13px;
  line-height: 1.6;
}

.precheck-stack,
.character-stack {
  display: grid;
  gap: 12px;
}

.precheck-card,
.character-card,
.summary-card,
.step-card {
  border-radius: 18px;
  padding: 14px 16px;
  background: var(--color-surface-2);
}

.precheck-pass {
  border: 1px solid color-mix(in srgb, var(--color-success) 28%, transparent);
}

.precheck-warning {
  border: 1px solid color-mix(in srgb, var(--color-warning) 32%, transparent);
}

.precheck-error {
  border: 1px solid color-mix(in srgb, var(--color-danger) 30%, transparent);
}

.precheck-card p,
.summary-card p,
.character-card p,
.step-card p,
.empty-copy {
  margin: 6px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.summary-grid,
.step-grid {
  display: grid;
  gap: 12px;
}

.context-section-head {
  margin-top: var(--spacing-4);
}

.field {
  display: grid;
  gap: 8px;
  margin-bottom: 16px;
}

.field span,
.ribbon-label {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.field input,
.field textarea {
  width: 100%;
  border-radius: 16px;
  border: 1px solid var(--color-border-default);
  padding: 12px 14px;
  font: inherit;
  color: var(--color-text-1);
  background: var(--color-surface-1);
}

.control-row {
  display: flex;
  gap: 14px;
  align-items: flex-end;
  justify-content: space-between;
  flex-wrap: wrap;
}

.compact-field {
  min-width: 140px;
  margin-bottom: 0;
}

.lower-row {
  margin-top: 4px;
}

.action-row {
  display: flex;
  gap: 12px;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--color-text-2);
}

.prompt-ribbon {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 18px;
}

.benchmark-ribbon {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 18px;
}

.skill-ribbon {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 0 0 18px;
}

.prompt-ribbon > div {
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--color-surface-3) 72%, transparent), color-mix(in srgb, var(--color-accent-soft) 72%, transparent));
}

.benchmark-ribbon > div {
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--color-accent-soft) 72%, transparent), color-mix(in srgb, var(--color-warning-soft) 72%, transparent));
}

.skill-ribbon > div {
  padding: 14px 16px;
  border-radius: 18px;
  background: linear-gradient(135deg, color-mix(in srgb, var(--color-info-soft) 72%, transparent), color-mix(in srgb, var(--color-surface-3) 86%, transparent));
}

.prompt-ribbon p {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.benchmark-ribbon p {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.skill-ribbon p {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.benchmark-anchor-count {
  margin-left: 8px;
  color: var(--color-text-3);
  font-size: 12px;
}

.benchmark-warning {
  margin: 0 0 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-warning-soft);
  color: var(--color-warning);
}

.benchmark-warning strong {
  display: block;
  margin-bottom: 6px;
}

.benchmark-warning p {
  margin: 0;
  line-height: 1.6;
}

.output-text {
  margin: 0;
  white-space: pre-wrap;
  line-height: 1.8;
  color: var(--color-text-1);
  min-height: 280px;
}

.error-banner {
  margin: 0 0 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.step-grid {
  grid-template-columns: repeat(5, minmax(0, 1fr));
}

.step-card {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  border: 1px solid transparent;
}

.step-index {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-3);
  font-weight: 700;
}

.step-running {
  border-color: color-mix(in srgb, var(--color-warning) 42%, transparent);
}

.step-completed {
  border-color: color-mix(in srgb, var(--color-success) 38%, transparent);
}

.step-failed {
  border-color: color-mix(in srgb, var(--color-danger) 38%, transparent);
}

@media (max-width: 1080px) {
  .step-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .writing-status-strip :deep(.system-card__body) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .control-row,
  .prompt-ribbon,
  .benchmark-ribbon,
  .skill-ribbon {
    grid-template-columns: 1fr;
    display: grid;
  }

  .step-grid {
    grid-template-columns: 1fr;
  }
}
</style>