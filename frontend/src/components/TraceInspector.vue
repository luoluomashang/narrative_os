<template>
  <div class="trace-inspector">
    <div class="trace-tree" v-if="isRunTrace">
      <div v-if="runSteps.length === 0" class="tree-empty">暂无步骤数据</div>
      <button
        v-for="step in runSteps"
        v-else
        :key="step.step_id"
        class="step-card"
        :class="{ selected: selectedId === step.step_id }"
        @click="selectNode(step.step_id)"
      >
        <div class="step-topline">
          <span class="step-index">{{ step.step_index }}</span>
          <span class="step-agent">{{ step.agent_name }}</span>
          <span class="step-status" :class="`step-status--${step.status}`">{{ formatStatus(step.status) }}</span>
        </div>
        <div class="step-summary">{{ step.artifact?.input_summary || '暂无输入摘要' }}</div>
      </button>
    </div>

    <div class="trace-tree" v-else>
      <div class="tree-empty" v-if="!data || isEmptyTree">
        {{ emptyNote }}
      </div>
      <TraceNode
        v-else
        v-for="node in rootNodes"
        :key="node.id"
        :node="node"
        :selected-id="selectedId"
        @select="selectNode"
      />
    </div>

    <div class="trace-detail">
      <template v-if="isRunTrace">
        <div v-if="runData?.status === 'paused' && runData.approval_checkpoint" class="approval-banner">
          <div>
            <div class="block-label">HITL 审批检查点</div>
            <div class="approval-reason">{{ runData.approval_checkpoint.reason }}</div>
          </div>
          <div class="approval-actions">
            <button class="approval-btn approve" @click="$emit('approve')">批准</button>
            <button class="approval-btn retry" @click="$emit('retry')">重试</button>
            <button class="approval-btn reject" @click="$emit('reject')">驳回</button>
          </div>
        </div>

        <div v-if="runData?.root_cause" class="detail-block root-cause-block">
          <div class="block-label">根因诊断</div>
          <div class="root-cause-pill">{{ rootCauseLabel }}</div>
          <div class="block-value" v-if="runData.root_cause.message">{{ runData.root_cause.message }}</div>
          <div class="trace-meta-grid">
            <div class="trace-meta-item" v-if="runData.root_cause.step_id">
              <div class="trace-meta-key">根因步骤</div>
              <div class="trace-meta-val mono">{{ runData.root_cause.step_id }}</div>
            </div>
            <div class="trace-meta-item" v-if="runData.root_cause.correlation_id || runData.correlation_id">
              <div class="trace-meta-key">Correlation ID</div>
              <div class="trace-meta-val mono">{{ runData.root_cause.correlation_id || runData.correlation_id }}</div>
            </div>
          </div>
        </div>

        <div v-if="!selectedStep" class="detail-empty">选择左侧步骤查看详情</div>
        <template v-else>
          <div class="detail-block">
            <div class="block-label">步骤</div>
            <div class="block-value mono">{{ selectedStep.agent_name }} / {{ selectedStep.step_id }}</div>
          </div>

          <div class="detail-block" v-if="selectedStep.failure_type || selectedStep.failure_message || selectedStep.correlation_id || selectedStep.artifact?.correlation_id">
            <div class="block-label">步骤诊断</div>
            <div class="trace-meta-grid">
              <div class="trace-meta-item" v-if="selectedStep.failure_type">
                <div class="trace-meta-key">失败类型</div>
                <div class="trace-meta-val">{{ selectedStep.failure_type }}</div>
              </div>
              <div class="trace-meta-item" v-if="selectedStep.correlation_id || selectedStep.artifact?.correlation_id">
                <div class="trace-meta-key">Correlation ID</div>
                <div class="trace-meta-val mono">{{ selectedStep.correlation_id || selectedStep.artifact?.correlation_id }}</div>
              </div>
            </div>
            <pre v-if="selectedStep.failure_message" class="block-pre">{{ selectedStep.failure_message }}</pre>
          </div>

          <div class="detail-block" v-if="selectedStep.artifact">
            <div class="block-label">输入摘要</div>
            <pre class="block-pre">{{ selectedStep.artifact.input_summary }}</pre>
          </div>

          <div class="detail-block" v-if="selectedStep.artifact">
            <div class="block-label collapsible" @click="expandOutput = !expandOutput">
              输出内容 {{ expandOutput ? '▲' : '▼' }}
            </div>
            <pre v-if="expandOutput" class="block-pre block-pre--large">{{ selectedStep.artifact.output_content }}</pre>
          </div>

          <div class="detail-block" v-if="selectedStep.artifact && scoreEntries.length">
            <div class="block-label">质量评分</div>
            <div class="score-list">
              <div v-for="entry in scoreEntries" :key="entry.key" class="score-row">
                <span>{{ entry.key }}</span>
                <div class="score-track">
                  <div class="score-fill" :style="{ width: `${Math.max(0, Math.min(entry.percent, 100))}%` }" />
                </div>
                <span class="mono">{{ entry.value.toFixed(2) }}</span>
              </div>
            </div>
          </div>

          <div class="detail-block" v-if="selectedStep.artifact">
            <div class="block-label">运行遥测</div>
            <div class="telemetry-grid">
              <div class="tele-item">
                <div class="tele-key">输入 Token</div>
                <div class="tele-val">{{ selectedStep.artifact.token_in }}</div>
              </div>
              <div class="tele-item">
                <div class="tele-key">输出 Token</div>
                <div class="tele-val">{{ selectedStep.artifact.token_out }}</div>
              </div>
              <div class="tele-item">
                <div class="tele-key">耗时</div>
                <div class="tele-val">{{ selectedStep.artifact.latency_ms }}ms</div>
              </div>
              <div class="tele-item">
                <div class="tele-key">重试</div>
                <div class="tele-val">{{ selectedStep.artifact.retry_count }}</div>
              </div>
            </div>
          </div>

          <div class="detail-block" v-if="selectedStep.artifact?.retry_reason">
            <div class="block-label">重试原因</div>
            <pre class="block-pre">{{ selectedStep.artifact.retry_reason }}</pre>
          </div>
        </template>
      </template>

      <template v-else>
        <div v-if="!selectedNode" class="detail-empty">选择左侧节点查看详情</div>
        <template v-else>
        <div class="detail-block">
          <div class="block-label">节点</div>
          <div class="block-value mono">{{ selectedNode.id }}</div>
        </div>

        <div class="detail-block" v-if="selectedNode.system_prompt">
          <div class="block-label collapsible" @click="expandSP = !expandSP">
            System Prompt {{ expandSP ? '▲' : '▼' }}
          </div>
          <pre v-if="expandSP" class="block-pre">{{ selectedNode.system_prompt }}</pre>
        </div>

        <div class="detail-block" v-if="selectedNode.input">
          <div class="block-label">Input Payload</div>
          <pre class="block-pre">{{ formatJSON(selectedNode.input) }}</pre>
        </div>

        <div class="detail-block" v-if="selectedNode.output">
          <div class="block-label">Output</div>
          <pre class="block-pre">{{ selectedNode.output }}</pre>
        </div>

        <div class="detail-block" v-if="selectedNode.telemetry">
          <div class="block-label">Telemetry</div>
          <div class="telemetry-grid">
            <div class="tele-item">
              <div class="tele-key">延迟</div>
              <div class="tele-val">{{ selectedNode.telemetry.latency_ms ?? '—' }}ms</div>
            </div>
            <div class="tele-item">
              <div class="tele-key">输入 Token</div>
              <div class="tele-val">{{ selectedNode.telemetry.input_tokens ?? '—' }}</div>
            </div>
            <div class="tele-item">
              <div class="tele-key">输出 Token</div>
              <div class="tele-val">{{ selectedNode.telemetry.output_tokens ?? '—' }}</div>
            </div>
            <div class="tele-item">
              <div class="tele-key">状态</div>
              <div class="tele-val">{{ selectedNode.telemetry.status ?? '—' }}</div>
            </div>
          </div>
        </div>
      </template>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineComponent, h, type VNode, watch } from 'vue'

export interface TraceNodeData {
  id: string
  label?: string
  icon?: string
  system_prompt?: string
  input?: unknown
  output?: string
  telemetry?: {
    latency_ms?: number
    input_tokens?: number
    output_tokens?: number
    status?: string
  }
  children?: TraceNodeData[]
}

const props = defineProps<{
  data: object | null
}>()

defineEmits<{
  approve: []
  reject: []
  retry: []
}>()

const selectedId = ref<string | null>(null)
const expandSP = ref(false)
const expandOutput = ref(true)

interface RunArtifact {
  artifact_id: string
  agent_name: string
  correlation_id?: string
  input_summary: string
  output_content: string
  quality_scores: Record<string, number>
  token_in: number
  token_out: number
  latency_ms: number
  retry_count: number
  retry_reason?: string | null
}

interface RunStepData {
  step_id: string
  step_index: number
  agent_name: string
  status: string
  correlation_id?: string
  failure_type?: string | null
  failure_message?: string | null
  artifact?: RunArtifact | null
}

interface RunTraceData {
  run_id: string
  status: string
  correlation_id?: string
  root_cause?: {
    type: string
    message?: string
    step_id?: string | null
    correlation_id?: string
  } | null
  steps: RunStepData[]
  approval_checkpoint?: {
    reason: string
    correlation_id?: string
  } | null
}

const runData = computed<RunTraceData | null>(() => {
  const candidate = props.data as RunTraceData | null
  if (candidate && Array.isArray(candidate.steps)) return candidate
  return null
})

const isRunTrace = computed(() => !!runData.value)
const runSteps = computed(() => runData.value?.steps ?? [])
const selectedStep = computed(() => runSteps.value.find(step => step.step_id === selectedId.value) ?? runSteps.value[0] ?? null)
const rootCauseLabel = computed(() => {
  const type = runData.value?.root_cause?.type
  return {
    model_error: '模型错误',
    rule_blocked: '规则阻断',
    approval_paused: '人工审批暂停',
    persistence_error: '持久化错误',
    unknown: '未知原因',
  }[type ?? ''] ?? type ?? '未知原因'
})
const scoreEntries = computed(() => {
  const scores = selectedStep.value?.artifact?.quality_scores ?? {}
  return Object.entries(scores).map(([key, value]) => ({
    key,
    value,
    percent: value <= 1 ? value * 100 : value,
  }))
})

// Parse incoming data into tree nodes
const rootNodes = computed<TraceNodeData[]>(() => {
  if (!props.data) return []
  const d = props.data as { children?: TraceNodeData[]; note?: string } & TraceNodeData
  if (d.children && Array.isArray(d.children)) return d.children
  if (d.id) return [d]
  return []
})

const isEmptyTree = computed(() => rootNodes.value.length === 0)
const emptyNote = computed(() => {
  const d = props.data as { note?: string } | null
  const note = d?.note ?? ''
  if (!note) return '暂无执行链路数据'
  if (note.toLowerCase().includes('not yet available')) return '当前章节暂无可视化执行链路'
  return note
})

const flatNodes = computed<TraceNodeData[]>(() => {
  const out: TraceNodeData[] = []
  function walk(nodes: TraceNodeData[]) {
    for (const n of nodes) {
      out.push(n)
      if (n.children) walk(n.children)
    }
  }
  walk(rootNodes.value)
  return out
})

const selectedNode = computed(() =>
  flatNodes.value.find(n => n.id === selectedId.value) ?? null
)

watch(runSteps, steps => {
  if (steps.length > 0 && !steps.some(step => step.step_id === selectedId.value)) {
    selectedId.value = steps[0].step_id
  }
}, { immediate: true })

function selectNode(id: string) {
  selectedId.value = id
  expandSP.value = false
  expandOutput.value = true
}

function formatJSON(v: unknown): string {
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function formatStatus(status: string): string {
  return {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    paused: '已暂停',
  }[status] ?? status
}

// Recursive tree node component
const TraceNode: ReturnType<typeof defineComponent> = defineComponent({
  name: 'TraceNode',
  props: {
    node: { type: Object as () => TraceNodeData, required: true },
    selectedId: { type: String as () => string | null, default: null },
    depth: { type: Number, default: 0 },
  },
  emits: ['select'],
  setup(p, { emit }): () => VNode {
    const expanded = ref(true)
    const icon = computed(() => p.node.icon ?? iconFor(p.node.id))
    function iconFor(id: string) {
      if (id.includes('plan')) return '🗺️'
      if (id.includes('write')) return '✍️'
      if (id.includes('check')) return '🔍'
      if (id.includes('edit')) return '✂️'
      if (id.includes('memory')) return '💾'
      if (id.includes('error') || id.includes('fail')) return '✗'
      return '⚡'
    }
    return (): VNode => h('div', { class: 'tree-node' }, [
      h('div', {
        class: ['tree-row', p.selectedId === p.node.id ? 'selected' : ''],
        style: { paddingLeft: `${p.depth * 16 + 8}px` },
        onClick: () => emit('select', p.node.id),
      }, [
        p.node.children?.length
          ? h('span', {
              class: 'tree-expand',
              onClick: (e: Event) => { e.stopPropagation(); expanded.value = !expanded.value },
            }, expanded.value ? '▼' : '▶')
          : h('span', { class: 'tree-expand' }, ' '),
        h('span', { class: 'tree-icon' }, icon.value),
        h('span', { class: 'tree-label' }, p.node.label ?? p.node.id),
      ]),
      expanded.value && p.node.children?.length
        ? h('div', p.node.children!.map((child: TraceNodeData): VNode =>
            h(TraceNode, {
              node: child,
              selectedId: p.selectedId,
              depth: p.depth + 1,
              onSelect: (id: string) => emit('select', id),
            })
          ))
        : null,
    ])
  },
})
</script>

<style scoped>
.trace-inspector {
  display: grid;
  grid-template-columns: 25% 75%;
  height: 100%;
  overflow: hidden;
}

/* Tree */
.trace-tree {
  border-right: 1px solid var(--color-surface-l2);
  overflow-y: auto;
  padding: var(--spacing-xs) 0;
}
.step-card {
  width: calc(100% - 16px);
  margin: 8px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  background: var(--color-base);
  color: inherit;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
}
.step-card.selected {
  border-color: var(--color-ai-active);
  background: color-mix(in srgb, var(--color-ai-active) 8%, var(--color-base));
}
.step-topline {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.step-index {
  width: 24px;
  height: 24px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-l1);
  font-size: 12px;
}
.step-agent {
  flex: 1;
  text-transform: capitalize;
  font-weight: 600;
}
.step-status {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--color-surface-l1);
}
.step-status--completed { background: color-mix(in srgb, var(--color-success) 18%, transparent); }
.step-status--failed { background: color-mix(in srgb, var(--color-error) 18%, transparent); }
.step-status--paused { background: color-mix(in srgb, var(--color-hitl) 18%, transparent); }
.step-summary {
  font-size: 12px;
  color: var(--color-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.tree-empty {
  padding: var(--spacing-md);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}
:deep(.tree-row) {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
  transition: background 100ms;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
:deep(.tree-row:hover) { background: var(--color-surface-l2); }
:deep(.tree-row.selected) { background: color-mix(in srgb, var(--color-ai-active) 15%, transparent); }
:deep(.tree-expand) { width: 12px; flex-shrink: 0; font-size: 10px; color: var(--color-text-secondary); cursor: pointer; }
:deep(.tree-icon) { font-size: 14px; flex-shrink: 0; }
:deep(.tree-label) { overflow: hidden; text-overflow: ellipsis; }

/* Detail */
.trace-detail {
  overflow-y: auto;
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}
.detail-empty {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  text-align: center;
  margin-top: var(--spacing-xl);
}
.detail-block { display: flex; flex-direction: column; gap: 4px; }
.root-cause-block {
  padding: 14px;
  border: 1px solid color-mix(in srgb, var(--color-warning) 32%, transparent);
  border-radius: var(--radius-card);
  background: color-mix(in srgb, var(--color-warning) 8%, transparent);
}
.root-cause-pill {
  width: fit-content;
  padding: 4px 10px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-warning) 20%, transparent);
  font-size: 12px;
  font-weight: 600;
}
.trace-meta-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 10px;
}
.trace-meta-item {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: 10px 12px;
}
.trace-meta-key {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
.trace-meta-val {
  font-size: 13px;
  word-break: break-all;
}
.approval-banner {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 14px;
  border: 1px solid var(--color-hitl);
  border-radius: var(--radius-card);
  background: color-mix(in srgb, var(--color-hitl) 10%, transparent);
}
.approval-reason {
  font-size: 14px;
  font-weight: 600;
}
.approval-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.approval-btn {
  border: none;
  border-radius: 999px;
  padding: 8px 14px;
  cursor: pointer;
}
.approval-btn.approve { background: var(--color-success); color: var(--color-text-primary); }
.approval-btn.retry { background: var(--color-warning); color: var(--color-base); }
.approval-btn.reject { background: var(--color-error); color: var(--color-text-primary); }
.block-label {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.block-label.collapsible { cursor: pointer; user-select: none; }
.block-label.collapsible:hover { color: var(--color-text-primary); }
.block-value { font-size: 14px; }
.mono { font-family: monospace; }
.block-pre {
  margin: 0;
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm);
  font-size: 12px;
  font-family: monospace;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 240px;
  overflow-y: auto;
}
.block-pre--large {
  max-height: 420px;
}
.score-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.score-row {
  display: grid;
  grid-template-columns: 120px 1fr 60px;
  gap: 12px;
  align-items: center;
}
.score-track {
  height: 8px;
  border-radius: 999px;
  background: var(--color-surface-l1);
  overflow: hidden;
}
.score-fill {
  height: 100%;
  background: linear-gradient(90deg, #1bb56b, #f7b500, #ff4d6d);
}
.telemetry-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-sm);
}
.tele-item {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm);
  text-align: center;
}
.tele-key { font-size: var(--text-caption); color: var(--color-text-secondary); }
.tele-val { font-size: 14px; font-weight: 600; margin-top: 2px; }

@media (max-width: 960px) {
  .trace-inspector {
    grid-template-columns: 1fr;
  }

  .trace-tree {
    border-right: none;
    border-bottom: 1px solid var(--color-surface-l2);
    max-height: 280px;
  }

  .approval-banner {
    flex-direction: column;
  }

  .telemetry-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .score-row {
    grid-template-columns: 1fr;
  }
}
</style>
