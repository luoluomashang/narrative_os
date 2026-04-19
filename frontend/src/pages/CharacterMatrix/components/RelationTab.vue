<template>
  <div class="relation-tab">
    <!-- D3 Force Graph -->
    <div class="section-title">关系力导向图</div>
    <div ref="graphEl" class="relation-graph"></div>

    <!-- Add relation -->
    <div class="add-relation">
      <div class="section-title">新增关系</div>
      <div class="add-relation-row">
        <el-input v-model="newTarget" placeholder="角色名" size="small" style="flex:1" />
        <div class="slider-wrap">
          <span class="slider-label">{{ newValue.toFixed(1) }}</span>
          <el-slider v-model="newValue" :min="-1" :max="1" :step="0.1" :show-tooltip="false" style="flex:1" />
        </div>
        <el-button size="small" @click="addRelation">添加</el-button>
      </div>
    </div>

    <!-- List view (collapsible) -->
    <div class="relation-list-section">
      <div class="section-title clickable" @click="showList = !showList">
        关系列表 {{ showList ? '▾' : '▸' }}
      </div>
      <div v-if="showList" class="relation-list">
        <div v-for="(_val, name) in localRelationships" :key="name" class="relation-list-item">
          <span class="rel-name">{{ name }}</span>
          <el-slider
            v-model="localRelationships[name]"
            :min="-1" :max="1" :step="0.1"
            :show-tooltip="false"
            style="flex:1; margin: 0 12px;"
          />
          <span class="rel-value" :style="{ color: relColor(localRelationships[name]) }">{{ localRelationships[name].toFixed(1) }}</span>
          <button class="rel-del" @click="removeRelation(name as string)">×</button>
        </div>
        <div v-if="!Object.keys(localRelationships).length" class="empty-hint">暂无关系</div>
      </div>
    </div>

    <!-- Save button -->
    <div class="relation-actions">
      <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as d3 from 'd3'
import { useThemeMode } from '@/composables/useThemeMode'
import type { CharacterDetail, CharacterSummary } from '@/types/api'

const props = defineProps<{
  model: CharacterDetail
  loading: boolean
  allCharacters: CharacterSummary[]
}>()

const emit = defineEmits<{
  (e: 'save', relationships: Record<string, number>): void
}>()

const graphEl = ref<HTMLElement | null>(null)
const localRelationships = ref<Record<string, number>>({})
const newTarget = ref('')
const newValue = ref(0.5)
const showList = ref(true)
const { resolvedTheme } = useThemeMode()

function readThemeColor(variable: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

watch(() => props.model, (m) => {
  if (m) {
    const raw = m.relationships ?? {}
    const obj: Record<string, number> = {}
    for (const [k, v] of Object.entries(raw)) {
      obj[k] = typeof v === 'number' ? v : parseFloat(v as any) || 0
    }
    localRelationships.value = obj
    nextTick(renderGraph)
  }
}, { immediate: true })

function relColor(value: number): string {
  if (value >= 0.6) return readThemeColor('--color-success', '#198754')
  if (value >= 0.2) return readThemeColor('--color-accent', '#127ea8')
  if (value > -0.2) return readThemeColor('--color-text-3', '#7a8794')
  if (value > -0.6) return readThemeColor('--color-warning', '#c27a12')
  return readThemeColor('--color-danger', '#c2413b')
}

function addRelation() {
  const name = newTarget.value.trim()
  if (!name) return
  localRelationships.value[name] = newValue.value
  newTarget.value = ''
  newValue.value = 0.5
  nextTick(renderGraph)
}

function removeRelation(name: string) {
  delete localRelationships.value[name]
  nextTick(renderGraph)
}

function handleSave() {
  emit('save', { ...localRelationships.value })
}

let simulation: d3.Simulation<any, any> | null = null

function renderGraph() {
  if (!graphEl.value) return
  const container = graphEl.value
  // Clear previous
  d3.select(container).selectAll('*').remove()

  const width = container.clientWidth || 400
  const height = 240

  const selfName = props.model.name
  const rels = localRelationships.value
  const names = Object.keys(rels)
  if (!names.length) return

  const nodeNames = [selfName, ...names.filter(n => n !== selfName)]
  const nodes = nodeNames.map((name, i) => ({ id: name, x: width / 2, y: height / 2, index: i }))
  const links = names.map(name => ({
    source: selfName,
    target: name,
    value: rels[name],
  }))

  const svg = d3.select(container).append('svg')
    .attr('width', width)
    .attr('height', height)

  simulation = d3.forceSimulation(nodes as any)
    .force('link', d3.forceLink(links as any).id((d: any) => d.id).distance(80))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))

  const link = svg.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('stroke', (d: any) => relColor(d.value))
    .attr('stroke-width', 2)
    .attr('stroke-opacity', 0.7)

  const node = svg.append('g')
    .selectAll('g')
    .data(nodes)
    .join('g')
    .call(d3.drag<any, any>()
      .on('start', (event: any, d: any) => {
        if (!event.active) simulation?.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event: any, d: any) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event: any, d: any) => {
        if (!event.active) simulation?.alphaTarget(0)
        d.fx = null
        d.fy = null
      }) as any
    )

  node.append('circle')
    .attr('r', (d: any) => d.id === selfName ? 16 : 12)
    .attr('fill', (d: any) => d.id === selfName ? readThemeColor('--color-accent', '#127ea8') : readThemeColor('--color-surface-4', '#c7d2de'))
    .attr('stroke', readThemeColor('--color-accent', '#127ea8'))
    .attr('stroke-width', 1.5)

  node.append('text')
    .text((d: any) => d.id)
    .attr('font-size', '11px')
    .attr('fill', readThemeColor('--color-text-2', '#4f6475'))
    .attr('text-anchor', 'middle')
    .attr('dy', -20)

  simulation.on('tick', () => {
    link
      .attr('x1', (d: any) => d.source.x)
      .attr('y1', (d: any) => d.source.y)
      .attr('x2', (d: any) => d.target.x)
      .attr('y2', (d: any) => d.target.y)
    node.attr('transform', (d: any) => `translate(${d.x},${d.y})`)
  })
}

onMounted(() => {
  nextTick(renderGraph)
})

watch(resolvedTheme, () => {
  nextTick(renderGraph)
})

onBeforeUnmount(() => {
  simulation?.stop()
})
</script>

<style scoped>
.relation-tab { padding: 4px 0; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.section-title.clickable { cursor: pointer; user-select: none; }
.relation-graph {
  height: 240px;
  width: 100%;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  margin-bottom: 12px;
  overflow: hidden;
}
.add-relation {
  margin-bottom: 12px;
  padding: 10px;
  border: 1px dashed var(--color-surface-l2);
  border-radius: var(--radius-btn);
}
.add-relation-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.slider-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}
.slider-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  min-width: 32px;
  text-align: right;
}
.relation-list { margin-bottom: 12px; }
.relation-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.rel-name { font-size: 13px; color: var(--color-text-primary); min-width: 60px; }
.rel-value { font-size: 12px; font-weight: 600; min-width: 32px; text-align: right; }
.rel-del {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
}
.rel-del:hover { color: var(--color-danger); }
.empty-hint {
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 8px 0;
}
.relation-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
