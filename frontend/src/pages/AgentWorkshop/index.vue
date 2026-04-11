<template>
  <div class="workshop-page">
    <!-- Agent monitor cards -->
    <div class="agent-monitor-row">
      <div v-if="agents.length === 0" class="monitor-empty">暂无 Agent 运行记录</div>
      <el-card
        v-for="agent in agents"
        :key="agent.id"
        shadow="hover"
        class="monitor-card"
        :class="`status-${agent.status}`"
        :body-style="{ padding: '10px 14px', display: 'flex', alignItems: 'center', gap: '10px' }"
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
      </el-card>
    </div>

    <!-- Swimlane diagram -->
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
            <!-- Rejection particle line -->
            <div v-if="ticket.rejected" class="reject-particle" />
          </div>
        </div>
      </div>
    </div>

    <!-- Trace Inspector (bottom panel) -->
    <div class="trace-section">
      <div class="trace-header">
        <span class="trace-title">执行链路 Trace</span>
        <el-select v-model="selectedChapter" style="width: 120px" @change="loadTrace">
          <el-option v-for="n in chapterOptions" :key="n" :label="`第 ${n} 章`" :value="n" />
        </el-select>
      </div>
      <el-empty v-if="!traceData" description="暂无执行记录" :image-size="60" />
      <TraceInspector v-else :data="traceData" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import TraceInspector from '@/components/TraceInspector.vue'
import axios from 'axios'
import { projects } from '@/api/projects'

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

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')
const agents = ref<AgentDef[]>([])
const chapterOptions = ref<number[]>([1])

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
  if (raw.includes('done') || raw.includes('success') || raw.includes('finish')) return 'done'
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
  try {
    const res = await axios.get(`/api/traces/${selectedChapter.value}`)
    traceData.value = res.data
    agents.value = buildAgentsFromTrace(res.data as Record<string, unknown>)
  } catch {
    traceData.value = null
    agents.value = []
  }
}

async function loadChapterOptions() {
  try {
    const res = await projects.chapterList(projectId.value)
    const nums = (res.data ?? []).map(c => c.chapter).filter(n => Number.isFinite(n))
    chapterOptions.value = nums.length > 0 ? nums : [1]
    selectedChapter.value = chapterOptions.value[0]
  } catch {
    chapterOptions.value = [1]
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
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Monitor row */
.agent-monitor-row {
  display: flex;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.monitor-empty {
  width: 100%;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: var(--text-caption);
  padding: var(--spacing-md) 0;
}
.monitor-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-surface-l2);
  padding: var(--spacing-sm) var(--spacing-md);
  flex: 1;
  min-width: 0;
  transition: border-color 200ms;
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
  border-top: 1px solid var(--color-surface-l2);
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
.chapter-select {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  padding: 2px 8px;
  font-size: var(--text-caption);
}
</style>
