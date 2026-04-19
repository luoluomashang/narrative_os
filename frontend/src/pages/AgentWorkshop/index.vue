<template>
  <div class="workshop-page">
    <SystemPageHeader
      eyebrow="Agent Workshop"
      title="Agent 编排工作台"
      description="查看章节维度的执行泳道、Ticket 状态与 Trace 回放，统一审视当前自动化链路。"
    >
      <template #meta>
        <span class="workshop-pill">项目 {{ projectId }}</span>
        <span class="workshop-pill">章节 {{ chapterOptions.length ? selectedChapter : '暂无' }}</span>
      </template>
      <template #actions>
        <SystemButton variant="ghost" @click="loadTrace">刷新 Trace</SystemButton>
      </template>
    </SystemPageHeader>

    <SystemCard class="panel-switch-card" tone="subtle">
      <div class="panel-switch-row">
        <SystemButton size="sm" :variant="activePanel === 'monitor' ? 'primary' : 'ghost'" @click="activePanel = 'monitor'">Agent 监控</SystemButton>
        <SystemButton size="sm" :variant="activePanel === 'swimlane' ? 'primary' : 'ghost'" @click="activePanel = 'swimlane'">执行泳道</SystemButton>
        <SystemButton size="sm" :variant="activePanel === 'trace' ? 'primary' : 'ghost'" @click="activePanel = 'trace'">Trace 回放</SystemButton>
      </div>
      <p class="panel-switch-copy">
        {{ activePanel === 'monitor'
          ? '默认先看 Agent 运行状态。'
          : activePanel === 'swimlane'
            ? 'Ticket 分布改为单独面板查看，避免与 Trace 同时争抢主视线。'
            : '详细 Trace 只在需要回放时展开。'
        }}
      </p>
    </SystemCard>

    <SystemSection v-if="activePanel === 'monitor'" title="Agent 监控" description="横向查看各 Agent 当前状态、最近日志和运行呼吸灯。" dense>
      <div class="agent-monitor-row">
        <SystemEmpty
          v-if="agents.length === 0"
          class="monitor-empty"
          title="暂无 Agent 运行记录"
          description="当前章节尚未生成可视化执行链路，先触发一次相关任务后再回来查看。"
        />
        <SystemCard
          v-for="agent in agents"
          :key="agent.id"
          class="monitor-card"
          :class="`status-${agent.status}`"
        >
          <div class="mc-icon">{{ agent.icon }}</div>
          <div class="mc-body">
            <div class="mc-name">{{ agent.name }}</div>
            <div class="mc-status">{{ statusLabel(agent.status) }}</div>
            <div class="mc-log">{{ agent.lastLog }}</div>
          </div>
          <NBreathingLight
            v-if="agent.status === 'running'"
            :size="8"
            color="var(--color-ai-active)"
          />
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection v-else-if="activePanel === 'swimlane'" title="执行泳道" description="按 Agent 查看各自 Ticket 的排队、运行、重试和失败分布。" dense>
      <SystemCard class="swimlane-shell" padding="none">
        <div class="swimlane-container">
          <div v-if="agents.length === 0" class="lane-empty">当前章节未生成可视化执行链路</div>
          <div
            v-for="agent in agents"
            :key="agent.id"
            class="swimlane"
          >
            <div class="lane-label">{{ agent.name }}</div>
            <div class="lane-track">
              <div
                v-for="ticket in agent.tickets"
                :key="ticket.id"
                class="job-ticket"
                :class="[`ticket-${ticket.status}`, { rejected: ticket.rejected }]"
              >
                <div class="ticket-id">{{ ticket.id }}</div>
                <div class="ticket-status-text">{{ ticketLabel(ticket.status) }}</div>
                <div v-if="ticket.retries > 0" class="ticket-retries">重写 #{{ ticket.retries }}</div>
                <div class="ticket-meta">{{ ticket.elapsed }}ms</div>
                <div v-if="ticket.rejected" class="reject-particle" />
              </div>
            </div>
          </div>
        </div>
      </SystemCard>
    </SystemSection>

    <SystemCard v-else class="trace-section" padding="none">
      <div class="trace-header">
        <div>
          <span class="trace-title">执行链路 Trace</span>
          <p class="trace-copy">选择已生成运行记录的章节，查看详细回放。</p>
        </div>
        <div class="trace-controls">
          <el-select v-model="selectedChapter" style="width: 120px" @change="loadTrace">
            <el-option v-for="n in chapterOptions" :key="n" :label="`第 ${n} 章`" :value="n" />
          </el-select>
          <SystemButton size="sm" variant="ghost" @click="loadChapterOptions(); loadTrace()">刷新</SystemButton>
        </div>
      </div>
      <SystemEmpty
        v-if="!traceData"
        title="暂无执行记录"
        description="选择一个已生成运行记录的章节后，这里会展示对应的执行链路。"
      />
      <TraceInspector v-else :data="traceData" />
    </SystemCard>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import TraceInspector from '@/components/TraceInspector.vue'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import axios from 'axios'

// ── Agent definitions ─────────────────────────────────────────────
type AgentStatus = 'idle' | 'running' | 'done' | 'error'
type TicketStatus = 'queued' | 'running' | 'done' | 'failed'

interface JobTicket {
  id: string
  status: TicketStatus
  retries: number
  elapsed: number
  rejected: boolean
}

interface AgentDef {
  id: string
  name: string
  icon: string
  status: AgentStatus
  lastLog: string
  tickets: JobTicket[]
}

interface RunListItem {
  run_id: string
  status: string
  chapter_num?: number | null
  started_at: string
}

interface RunArtifact {
  input_summary?: string
  output_content?: string
  latency_ms?: number
  retry_count?: number
}

interface RunStepData {
  step_id: string
  step_index: number
  agent_name: string
  status: string
  artifact?: RunArtifact | null
}

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')
const activePanel = ref<'monitor' | 'swimlane' | 'trace'>('monitor')
const agents = ref<AgentDef[]>([])
const chapterOptions = ref<number[]>([])
const runs = ref<RunListItem[]>([])

function statusLabel(s: AgentStatus) {
  return { idle: '等待中', running: '运行中', done: '已完成', error: '错误' }[s]
}
function ticketLabel(s: TicketStatus) {
  return { queued: '队列中', running: '进行中', done: '完成', failed: '失败' }[s]
}

// ── Trace ─────────────────────────────────────────────────────────
const selectedChapter = ref(1)
const traceData = ref<object | null>(null)

function toAgentStatus(v: unknown): AgentStatus {
  const raw = String(v ?? '').toLowerCase()
  if (raw.includes('run')) return 'running'
  if (raw.includes('done') || raw.includes('success') || raw.includes('finish') || raw.includes('complete')) return 'done'
  if (raw.includes('error') || raw.includes('fail')) return 'error'
  return 'idle'
}

function toTicketStatus(v: unknown): TicketStatus {
  const s = toAgentStatus(v)
  if (s === 'running') return 'running'
  if (s === 'done') return 'done'
  if (s === 'error') return 'failed'
  return 'queued'
}

function iconFor(name: string): string {
  const key = name.toLowerCase()
  if (key.includes('plan')) return '🗺️'
  if (key.includes('write')) return '✍️'
  if (key.includes('critic') || key.includes('review')) return '🔍'
  if (key.includes('edit')) return '✂️'
  if (key.includes('maint')) return '🛠️'
  return '🤖'
}

function buildAgentsFromTrace(payload: Record<string, unknown>): AgentDef[] {
  if (Array.isArray(payload.steps)) {
    const steps = payload.steps as RunStepData[]
    return steps.map((step) => ({
      id: step.agent_name,
      name: step.agent_name.charAt(0).toUpperCase() + step.agent_name.slice(1),
      icon: iconFor(step.agent_name),
      status: toAgentStatus(step.status),
      lastLog: step.artifact?.input_summary || step.artifact?.output_content?.slice(0, 80) || '等待中',
      tickets: [{
        id: step.step_id,
        status: toTicketStatus(step.status),
        retries: step.artifact?.retry_count ?? 0,
        elapsed: Math.round(step.artifact?.latency_ms ?? 0),
        rejected: false,
      }],
    }))
  }

  const nodes = Array.isArray(payload.nodes) ? payload.nodes as Array<Record<string, unknown>> : []
  if (nodes.length === 0) return []

  const grouped = new Map<string, AgentDef>()
  for (const node of nodes) {
    const nodeId = String(node.id ?? 'node')
    const nodeName = String(node.name ?? node.agent ?? nodeId)
    const agentKey = nodeName.split(/[._-]/)[0] || nodeName

    if (!grouped.has(agentKey)) {
      grouped.set(agentKey, {
        id: agentKey,
        name: agentKey.charAt(0).toUpperCase() + agentKey.slice(1),
        icon: iconFor(agentKey),
        status: 'idle',
        lastLog: '等待中',
        tickets: [],
      })
    }

    const agent = grouped.get(agentKey)!
    const status = toAgentStatus(node.status)
    const elapsed = typeof node.elapsed_ms === 'number'
      ? node.elapsed_ms
      : (typeof node.duration_ms === 'number' ? node.duration_ms : 0)
    const retries = typeof node.retries === 'number' ? node.retries : 0

    agent.tickets.push({
      id: nodeId,
      status: toTicketStatus(node.status),
      retries,
      elapsed,
      rejected: Boolean(node.rejected),
    })

    agent.status = status
    agent.lastLog = String(node.message ?? node.summary ?? nodeName)
  }

  return Array.from(grouped.values())
}

async function loadTrace() {
  const candidate = runs.value.find((run) => run.chapter_num === selectedChapter.value)
  if (!candidate) {
    traceData.value = null
    agents.value = []
    return
  }

  try {
    const res = await axios.get(`/api/runs/${candidate.run_id}/steps`)
    traceData.value = res.data
    agents.value = buildAgentsFromTrace(res.data as Record<string, unknown>)
  } catch {
    traceData.value = null
    agents.value = []
  }
}

async function loadChapterOptions() {
  try {
    const res = await axios.get(`/api/projects/${projectId.value}/runs`)
    runs.value = res.data.items ?? []
    const nums = Array.from(new Set(
      runs.value
        .map((run) => run.chapter_num)
        .filter((n): n is number => typeof n === 'number' && Number.isFinite(n)),
    ))
    chapterOptions.value = nums
    selectedChapter.value = nums[0] ?? 1
  } catch {
    runs.value = []
    chapterOptions.value = []
    selectedChapter.value = 1
  }
}

onMounted(async () => {
  await loadChapterOptions()
  await loadTrace()
})
</script>

<style scoped>
.workshop-page {
  display: grid;
  gap: 18px;
  height: 100%;
  overflow: auto;
  padding: 24px;
}

.workshop-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.panel-switch-card :deep(.system-card__body) {
  gap: 10px;
}

.panel-switch-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.panel-switch-copy {
  margin: 0;
  color: var(--color-text-3);
  line-height: 1.6;
}

/* Monitor row */
.agent-monitor-row {
  display: flex;
  gap: var(--spacing-sm);
  flex-shrink: 0;
  align-items: stretch;
}
.monitor-empty {
  width: 100%;
}
.monitor-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  flex: 1;
  min-width: 0;
}
.monitor-card.status-running { border-color: var(--color-ai-active); }
.monitor-card.status-error { border-color: var(--color-error); }
.mc-icon { font-size: 20px; flex-shrink: 0; }
.mc-body { min-width: 0; flex: 1; }
.mc-name { font-size: 13px; font-weight: 600; }
.mc-status { font-size: var(--text-caption); color: var(--color-text-secondary); }
.mc-log {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Swimlane */
.swimlane-shell {
  overflow: hidden;
}

.swimlane-container {
  display: flex;
  flex-direction: column;
  gap: 1px;
  flex: 1;
  overflow-y: auto;
  background: var(--color-surface-l2);
}
.lane-empty {
  background: var(--color-base);
  color: var(--color-text-secondary);
  font-size: 13px;
  text-align: center;
  padding: var(--spacing-lg) var(--spacing-md);
}
.swimlane {
  display: flex;
  align-items: center;
  background: var(--color-base);
  padding: var(--spacing-sm) var(--spacing-md);
  gap: var(--spacing-md);
  min-height: 80px;
}
.lane-label {
  width: 64px;
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
.lane-track {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  flex: 1;
}

/* Job ticket */
.job-ticket {
  position: relative;
  width: 160px;
  background: var(--color-surface-l2);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-surface-l2);
  padding: var(--spacing-sm);
  font-size: var(--text-caption);
  overflow: hidden;
  transition: border-color 200ms;
}
.ticket-running { border-color: var(--color-ai-active); animation: breathing 2s ease-in-out infinite; }
.ticket-done { background: color-mix(in srgb, var(--color-success) 15%, var(--color-surface-l2)); border-color: var(--color-success); }
.ticket-failed { border-color: var(--color-error); }
.ticket-id { font-weight: 600; margin-bottom: 2px; }
.ticket-status-text { color: var(--color-text-secondary); }
.ticket-retries { color: var(--color-warning); font-size: 11px; }
.ticket-meta { color: var(--color-text-secondary); margin-top: 2px; }

/* Rejection particle */
.reject-particle {
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--color-hitl);
  top: 50%;
  left: 100%;
  animation: reject-travel 600ms ease-in forwards;
}
@keyframes reject-travel {
  from { left: 100%; opacity: 1; }
  to   { left: -20px; opacity: 0; }
}

/* Trace section */
.trace-section {
  flex-shrink: 0;
  max-height: 40%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.trace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.trace-title { font-size: 13px; font-weight: 600; }
.trace-copy {
  margin: 6px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.trace-controls {
  display: flex;
  align-items: center;
  gap: 8px;
}
.chapter-select {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  padding: 2px 8px;
  font-size: var(--text-caption);
}

@media (max-width: 960px) {
  .workshop-page {
    padding: 20px 16px;
  }

  .agent-monitor-row {
    flex-direction: column;
  }

  .monitor-card {
    width: 100%;
  }

  .trace-header,
  .trace-controls {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
