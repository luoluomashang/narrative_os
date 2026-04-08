<template>
  <div class="trace-inspector">
    <!-- Left: tree (25%) -->
    <div class="trace-tree">
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

    <!-- Right: detail (75%) -->
    <div class="trace-detail">
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
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineComponent, h, type VNode } from 'vue'

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

const selectedId = ref<string | null>(null)
const expandSP = ref(false)

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
  return d?.note ?? '无 Trace 数据'
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

function selectNode(id: string) {
  selectedId.value = id
  expandSP.value = false
}

function formatJSON(v: unknown): string {
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
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
</style>
