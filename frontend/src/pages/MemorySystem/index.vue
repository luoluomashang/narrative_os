<template>
  <div class="memory-page">
    <div v-if="error" style="padding:16px">
      <NCard><p style="color:var(--color-error)">加载失败：{{ error }}</p><NButton variant="ghost" @click="load">重试</NButton></NCard>
    </div>
    <template v-else>
      <!-- Search bar -->
      <div class="search-bar">
        <input v-model="searchQ" class="search-input" placeholder="搜索记忆（RAG）…" @input="onSearch" />
        <NBreathingLight v-if="searching" :size="8" style="margin-left:8px" />
      </div>

      <!-- Search results -->
      <div v-if="searchResults.length" class="search-results">
        <NCard v-for="r in searchResults" :key="r.record_id" style="margin-bottom:8px">
          <div class="result-row">
            <span class="similarity">{{ (r.similarity ?? 0).toFixed(2) }}</span>
            <span class="result-content">{{ r.content }}</span>
          </div>
        </NCard>
      </div>

      <!-- 3-layer drawers -->
      <div class="layers">
        <div v-for="layer in layerOrder" :key="layer" class="layer-drawer">
          <button class="layer-header" @click="toggleLayer(layer)">
            <span>{{ layerLabels[layer] }}</span>
            <span class="layer-count">{{ snapshot?.collections?.[layer] ?? '…' }}</span>
            <span>{{ openLayers.has(layer) ? '▲' : '▼' }}</span>
          </button>
          <div v-if="openLayers.has(layer)" class="layer-body">
            <!-- Short-term: timeline -->
            <template v-if="layer === 'short_term'">
              <div v-if="snapshot?.recent_anchors?.length" class="anchor-list">
                <div v-for="a in snapshot.recent_anchors" :key="a.record_id"
                  class="anchor-card" :class="anchorColorClass(a.similarity)">
                  <div class="anchor-text">{{ a.content.slice(0, 60) }}{{ a.content.length > 60 ? '…' : '' }}</div>
                  <div class="anchor-meta">
                    <span class="anchor-score">{{ (a.similarity ?? 0).toFixed(2) }}</span>
                    <span class="anchor-time">{{ anchorTime(a.metadata) }}</span>
                  </div>
                </div>
              </div>
              <p v-else style="color:var(--color-text-secondary);padding:8px">暂无短期记忆</p>
            </template>

            <!-- Mid-term: card grid -->
            <template v-if="layer === 'mid_term'">
              <p style="color:var(--color-text-secondary);padding:8px">中期记忆（{{ snapshot?.collections?.['mid_term'] ?? 0 }} 条）</p>
            </template>

            <!-- Long-term: D3 starfield -->
            <template v-if="layer === 'long_term'">
              <div ref="starfieldEl" class="starfield"></div>
            </template>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import * as d3 from 'd3'
import NCard from '@/components/common/NCard.vue'
import NButton from '@/components/common/NButton.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import { projects } from '@/api/projects'
import type { MemorySnapshot, MemoryRecord } from '@/types/api'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const loading = ref(false)
const error = ref<string | null>(null)
const snapshot = ref<MemorySnapshot | null>(null)
const searchQ = ref('')
const searching = ref(false)
const searchResults = ref<MemoryRecord[]>([])
const openLayers = ref(new Set<string>(['short_term']))
const starfieldEl = ref<HTMLElement | null>(null)

const layerOrder = ['short_term', 'mid_term', 'long_term']
const layerLabels: Record<string, string> = {
  short_term: '短期记忆（时间流）',
  mid_term: '中期记忆（事件卡片）',
  long_term: '长期记忆（知识星空）',
}

let searchTimer: ReturnType<typeof setTimeout> | null = null

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQ.value.trim()) { searchResults.value = []; return }
  searchTimer = setTimeout(doSearch, 300)
}

async function doSearch() {
  searching.value = true
  try {
    const res = await projects.memorySearch(projectId.value, searchQ.value.slice(0, 200))
    searchResults.value = res.data.results
  } catch { searchResults.value = [] }
  finally { searching.value = false }
}

function anchorColorClass(sim?: number): string {
  const s = sim ?? 0
  if (s >= 0.8) return 'anchor-blue'
  if (s >= 0.6) return 'anchor-cyan'
  return 'anchor-gray'
}

function anchorTime(meta: Record<string, unknown>): string {
  const t = meta?.timestamp as string | undefined
  return t ? new Date(t).toLocaleTimeString() : ''
}

function toggleLayer(layer: string) {
  if (openLayers.value.has(layer)) {
    openLayers.value.delete(layer)
  } else {
    openLayers.value.add(layer)
    if (layer === 'long_term') nextTick(renderStarfield)
  }
}

function renderStarfield() {
  if (!starfieldEl.value) return
  const el = starfieldEl.value, w = el.clientWidth || 500, h = 260
  d3.select(el).selectAll('*').remove()
  const svg = d3.select(el).append('svg').attr('width', w).attr('height', h)

  const count = snapshot.value?.collections?.['long_term'] ?? 0
  const nodeCount = Math.min(count, 60)
  if (nodeCount === 0) {
    svg.append('text').attr('x', w / 2).attr('y', h / 2).attr('text-anchor', 'middle').attr('fill', '#999').text('暂无长期记忆')
    return
  }

  type StarNode = d3.SimulationNodeDatum & { id: number; label: string; color: string; r: number }
  const colors = ['#2ef2ff', '#9b59b6', '#f5a623', '#e67e22']
  const sdata: StarNode[] = Array.from({ length: nodeCount }, (_, i) => ({
    id: i,
    label: `记忆${i + 1}`,
    color: colors[i % colors.length],
    r: 4 + Math.random() * 6,
    x: w / 2 + (Math.random() - 0.5) * w * 0.8,
    y: h / 2 + (Math.random() - 0.5) * h * 0.8,
  }))

  const sim = d3.forceSimulation<StarNode>(sdata)
    .force('charge', d3.forceManyBody().strength(-30))
    .force('center', d3.forceCenter(w / 2, h / 2))
    .force('collision', d3.forceCollide<StarNode>().radius((d) => d.r + 4))

  const circles = svg.selectAll<SVGCircleElement, StarNode>('circle').data(sdata).enter()
    .append('circle')
    .attr('r', (d) => d.r)
    .attr('fill', (d) => d.color)
    .attr('opacity', 0.7)

  const tooltip = d3.select(el).append<HTMLDivElement>('div').attr('class', 'star-tooltip').style('display', 'none')
    .style('position', 'absolute').style('background', '#1b1c22').style('border', '1px solid #2d2f3a')
    .style('padding', '4px 8px').style('border-radius', '4px').style('font-size', '12px').style('color', '#f2efe9')
    .style('pointer-events', 'none')

  circles
    .on('mouseover', (event: MouseEvent, d: StarNode) => {
      tooltip.style('display', 'block').text(`${d.label} (${d.color})`)
        .style('left', `${(event as MouseEvent & { offsetX: number }).offsetX + 10}px`)
        .style('top', `${(event as MouseEvent & { offsetY: number }).offsetY - 20}px`)
    })
    .on('mouseout', () => tooltip.style('display', 'none'))

  sim.on('tick', () => {
    circles.attr('cx', (d) => d.x ?? 0).attr('cy', (d) => d.y ?? 0)
  })
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await projects.memory(projectId.value)
    snapshot.value = res.data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.memory-page { height: 100%; overflow-y: auto; }
.search-bar { display: flex; align-items: center; margin-bottom: 16px; }
.search-input { flex: 1; background: var(--color-surface-l1); border: 1px solid var(--color-surface-l2); color: var(--color-text-primary); padding: 8px 12px; border-radius: var(--radius-btn); font-size: 14px; outline: none; }
.search-input:focus { border-color: var(--color-ai-active); }
.search-results { margin-bottom: 16px; }
.result-row { display: flex; gap: 12px; align-items: flex-start; }
.similarity { font-size: 12px; color: var(--color-ai-active); flex-shrink: 0; padding-top: 2px; }
.result-content { font-size: 13px; color: var(--color-text-primary); }
.layers { display: flex; flex-direction: column; gap: 8px; }
.layer-drawer { background: var(--color-surface-l1); border-radius: var(--radius-card); border: 1px solid var(--color-surface-l2); overflow: hidden; }
.layer-header { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: transparent; border: none; color: var(--color-text-primary); cursor: pointer; font-size: 14px; font-weight: 600; transition: background 150ms; }
.layer-header:hover { background: var(--color-surface-l2); }
.layer-count { font-size: 12px; color: var(--color-ai-active); margin-left: auto; margin-right: 8px; }
.layer-body { padding: 12px 16px; }
.anchor-list { display: flex; flex-direction: column; gap: 6px; }
.anchor-card { padding: 8px 10px; border-radius: 6px; border-left: 3px solid var(--color-surface-l2); background: var(--color-surface-l1); }
.anchor-card.anchor-blue { border-left-color: #2ef2ff; background: rgba(46,242,255,0.06); }
.anchor-card.anchor-cyan { border-left-color: #00c8e0; background: rgba(0,200,224,0.06); }
.anchor-card.anchor-gray { border-left-color: #555; }
.anchor-text { font-size: 13px; color: var(--color-text-primary); margin-bottom: 4px; }
.anchor-meta { display: flex; gap: 10px; align-items: center; }
.anchor-score { font-size: 11px; font-weight: 600; color: var(--color-ai-active); }
.anchor-time { font-size: 11px; color: var(--color-text-secondary); }
.starfield { min-height: 260px; width: 100%; position: relative; }
</style>
