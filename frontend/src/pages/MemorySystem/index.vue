<template>
  <div class="memory-page">
    <SystemPageHeader
      eyebrow="Memory System"
      title="记忆系统"
      description="检索与浏览短期、中期、长期记忆分层，快速核对项目上下文与 RAG 召回结果。"
    />

    <SystemErrorState
      v-if="currentState === 'blocking'"
      title="记忆系统加载失败"
      :message="error || '记忆系统暂时不可用。'"
      action-label="重试"
      @action="load"
    />

    <SystemSkeleton v-else-if="currentState === 'loading'" :rows="8" show-header card />

    <SystemEmpty
      v-else-if="currentState === 'empty'"
      title="当前项目还没有可用记忆"
      description="先完成一次写作、会话或记忆写入，再回到这里查看时间流、事件卡片和知识星空。"
    >
      <template #action>
        <SystemButton variant="primary" @click="load">刷新记忆</SystemButton>
      </template>
    </SystemEmpty>

    <template v-else>
      <SystemSection title="记忆检索" description="输入关键词检索 RAG 记忆片段与相似度结果。" dense>
        <SystemStatusBanner
          v-if="searchError"
          status="partial-failure"
          title="检索结果未返回"
          :message="searchError"
          description="记忆分层仍可继续浏览，检索区只发生局部异常。"
        >
          <template #actions>
            <SystemButton variant="ghost" @click="doSearch">重试检索</SystemButton>
          </template>
        </SystemStatusBanner>

        <SystemCard tone="subtle">
          <div class="search-bar">
            <input v-model="searchQ" class="search-input" placeholder="搜索记忆（RAG）…" @input="onSearch" />
            <NBreathingLight v-if="searching" :size="8" class="search-spinner" />
          </div>
        </SystemCard>

        <div v-if="searchQ.trim()" class="search-results">
          <SystemCard
            v-for="r in searchResults"
            :key="r.record_id"
            tone="subtle"
            class="search-result-card"
            interactive
            @click="openRecordDetail(r)"
          >
            <div class="result-row">
              <span class="similarity">{{ (r.similarity ?? 0).toFixed(2) }}</span>
              <span class="result-content">{{ r.content }}</span>
            </div>
            <div class="result-meta">
              <span v-for="entry in formatRecordMetadata(r.metadata)" :key="entry" class="result-chip">{{ entry }}</span>
            </div>
            <div class="result-actions">
              <SystemButton size="sm" variant="secondary" @click.stop="openRecordDetail(r)">查看详情</SystemButton>
              <SystemButton
                v-if="getSourceLink(r)"
                size="sm"
                variant="ghost"
                @click.stop="openRecordSource(r)"
              >
                打开来源
              </SystemButton>
            </div>
          </SystemCard>

          <SystemEmpty
            v-if="!searching && searchResults.length === 0"
            title="没有匹配的记忆片段"
            description="换一个关键词，或等待更多记忆被写入后再检索。"
          />
        </div>
      </SystemSection>

      <SystemSection title="记忆分层" description="浏览短期锚点、中期统计以及长期知识星空。" dense>
        <SystemStatusBanner
          v-if="starfieldError"
          status="partial-failure"
          title="长期记忆图谱暂时不可用"
          :message="starfieldError"
          description="已自动切回摘要视图，避免局部图谱异常影响整个页面。"
        >
          <template #actions>
            <SystemButton variant="ghost" @click="retryStarfield">重试图谱</SystemButton>
          </template>
        </SystemStatusBanner>

        <div class="layers">
          <SystemCard v-for="layer in layerOrder" :key="layer" class="layer-drawer" padding="none">
            <button class="layer-header" @click="toggleLayer(layer)">
              <span>{{ layerLabels[layer] }}</span>
              <span class="layer-count">{{ snapshot?.collections?.[layer] ?? '…' }}</span>
              <span>{{ openLayers.has(layer) ? '▲' : '▼' }}</span>
            </button>
            <div v-if="openLayers.has(layer)" class="layer-body">
              <template v-if="layer === 'short_term'">
                <div v-if="snapshot?.recent_anchors?.length" class="anchor-list">
                  <button
                    v-for="a in snapshot.recent_anchors"
                    :key="a.record_id"
                    class="anchor-card"
                    :class="anchorColorClass(a.similarity)"
                    type="button"
                    @click="openRecordDetail(a)"
                  >
                    <div class="anchor-text">{{ a.content.slice(0, 60) }}{{ a.content.length > 60 ? '…' : '' }}</div>
                    <div class="anchor-meta">
                      <span class="anchor-score">{{ (a.similarity ?? 0).toFixed(2) }}</span>
                      <span class="anchor-time">{{ anchorTime(a.metadata) }}</span>
                    </div>
                  </button>
                </div>
                <SystemEmpty v-else title="暂无短期记忆" description="最近事件与锚点会在这里按时间流展示。" />
              </template>

              <template v-if="layer === 'mid_term'">
                <SystemCard tone="subtle" class="mid-term-summary">
                  中期记忆当前共 {{ snapshot?.collections?.['mid_term'] ?? 0 }} 条，可用于后续事件卡片与阶段摘要展示。
                </SystemCard>
              </template>

              <template v-if="layer === 'long_term'">
                <SystemVisualizationFallback
                  v-if="starfieldError"
                  title="知识星空已退回摘要视图"
                  description="你仍可查看核心记忆规模和最近锚点，图谱恢复后再回到可视化模式。"
                  :items="longTermFallbackItems"
                >
                  <div class="fallback-anchor-list">
                    <button
                      v-for="anchor in fallbackAnchors"
                      :key="anchor.record_id"
                      class="fallback-anchor-card"
                      type="button"
                      @click="openRecordDetail(anchor)"
                    >
                      <span class="fallback-anchor-card__text">{{ anchor.content }}</span>
                      <span class="fallback-anchor-card__meta">{{ anchorTime(anchor.metadata) || '最近写入' }}</span>
                    </button>
                  </div>

                  <template #actions>
                    <SystemButton variant="ghost" @click="retryStarfield">重新渲染</SystemButton>
                  </template>
                </SystemVisualizationFallback>
                <div v-else ref="starfieldEl" class="starfield"></div>
              </template>
            </div>
          </SystemCard>
        </div>
      </SystemSection>
    </template>

    <SystemDrawer
      v-model="detailDrawerOpen"
      title="记忆详情"
      description="浏览与来源定位统一进入抽屉，不再让记忆层级和详情信息同屏堆叠。"
      size="420px"
    >
      <div v-if="selectedRecord" class="memory-drawer">
        <SystemCard tone="subtle" title="记忆正文" :description="`来源：${describeMemorySource(selectedRecord)}`">
          <p class="memory-drawer__content">{{ selectedRecord.content }}</p>
        </SystemCard>

        <SystemCard title="来源定位" tone="subtle">
          <p class="memory-drawer__source-copy">
            {{ selectedRecordSource?.hint || '当前元数据未提供可直接跳转的来源页面。' }}
          </p>
          <template #actions>
            <SystemButton
              v-if="selectedRecordSource"
              size="sm"
              variant="primary"
              @click="router.push(selectedRecordSource.to)"
            >
              {{ selectedRecordSource.label }}
            </SystemButton>
          </template>
        </SystemCard>

        <SystemCard title="元数据明细">
          <div class="memory-drawer__meta">
            <div v-for="entry in selectedRecordMetadata" :key="entry.label" class="memory-drawer__meta-row">
              <span>{{ entry.label }}</span>
              <strong>{{ entry.value }}</strong>
            </div>
          </div>
        </SystemCard>
      </div>
    </SystemDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, nextTick, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import * as d3 from 'd3'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import { projects } from '@/api/projects'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'
import SystemVisualizationFallback from '@/components/system/SystemVisualizationFallback.vue'
import { useAsyncViewState } from '@/composables/useAsyncViewState'
import { useThemeMode } from '@/composables/useThemeMode'
import type { MemorySnapshot, MemoryRecord } from '@/types/api'
import {
  buildMemoryMetadataItems,
  describeMemorySource,
  formatMemoryMetadata,
  resolveMemorySourceLink,
} from '@/utils/memoryRecords'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => (route.params.id as string) || 'default')

const loading = ref(false)
const error = ref<string | null>(null)
const snapshot = ref<MemorySnapshot | null>(null)
const searchQ = ref('')
const searching = ref(false)
const searchResults = ref<MemoryRecord[]>([])
const searchError = ref<string | null>(null)
const openLayers = ref(new Set<string>(['short_term']))
const starfieldEl = ref<HTMLElement | null>(null)
const starfieldError = ref<string | null>(null)
const detailDrawerOpen = ref(false)
const selectedRecord = ref<MemoryRecord | null>(null)
const { resolvedTheme } = useThemeMode()

const layerOrder = ['short_term', 'mid_term', 'long_term']
const layerLabels: Record<string, string> = {
  short_term: '短期记忆（时间流）',
  mid_term: '中期记忆（事件卡片）',
  long_term: '长期记忆（知识星空）',
}

let searchTimer: ReturnType<typeof setTimeout> | null = null

const hasNoMemoryData = computed(() => {
  if (!snapshot.value) return false
  const totalCollections = Object.values(snapshot.value.collections ?? {}).reduce(
    (sum, value) => sum + Number(value ?? 0),
    0,
  )
  return totalCollections === 0 && (snapshot.value.recent_anchors?.length ?? 0) === 0
})

const { currentState } = useAsyncViewState({
  loading,
  blocking: computed(() => Boolean(error.value)),
  empty: hasNoMemoryData,
})

const longTermFallbackItems = computed(() => [
  { label: '长期记忆', value: snapshot.value?.collections?.long_term ?? 0 },
  { label: '中期记忆', value: snapshot.value?.collections?.mid_term ?? 0 },
  { label: '最近锚点', value: snapshot.value?.recent_anchors?.length ?? 0 },
])

const fallbackAnchors = computed(() => (snapshot.value?.recent_anchors ?? []).slice(0, 4))
const selectedRecordMetadata = computed(() => buildMemoryMetadataItems(selectedRecord.value, 16))
const selectedRecordSource = computed(() => (
  selectedRecord.value ? resolveMemorySourceLink(projectId.value, selectedRecord.value) : null
))

function readThemeColor(variable: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

function onSearch() {
  if (searchTimer) clearTimeout(searchTimer)
  if (!searchQ.value.trim()) {
    searchError.value = null
    searchResults.value = []
    return
  }
  searchTimer = setTimeout(doSearch, 300)
}

function getSourceLink(record: MemoryRecord) {
  return resolveMemorySourceLink(projectId.value, record)
}

function formatRecordMetadata(meta: Record<string, unknown>) {
  return formatMemoryMetadata(meta, 4)
}

function openRecordDetail(record: MemoryRecord) {
  selectedRecord.value = record
  detailDrawerOpen.value = true
}

function openRecordSource(record: MemoryRecord) {
  const source = getSourceLink(record)
  if (!source) return
  router.push(source.to)
}

async function doSearch() {
  if (!searchQ.value.trim()) {
    searchError.value = null
    searchResults.value = []
    return
  }

  searching.value = true
  searchError.value = null
  try {
    const res = await projects.memorySearch(projectId.value, searchQ.value.slice(0, 200))
    searchResults.value = res.data.results ?? []
  } catch (e: unknown) {
    searchError.value = e instanceof Error ? e.message : '记忆检索请求失败'
    searchResults.value = []
  } finally {
    searching.value = false
  }
}

function anchorColorClass(sim?: number | null): string {
  const s = sim ?? 0
  if (s >= 0.8) return 'anchor-blue'
  if (s >= 0.6) return 'anchor-cyan'
  return 'anchor-gray'
}

function anchorTime(meta?: Record<string, unknown>): string {
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

  try {
    starfieldError.value = null
    const el = starfieldEl.value
    const w = el.clientWidth || 500
    const h = 260
    d3.select(el).selectAll('*').remove()
    const svg = d3.select(el).append('svg').attr('width', w).attr('height', h)

    const count = snapshot.value?.collections?.long_term ?? 0
    const nodeCount = Math.min(count, 60)
    if (nodeCount === 0) {
      svg.append('text')
        .attr('x', w / 2)
        .attr('y', h / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', readThemeColor('--color-text-3', '#7a8794'))
        .text('暂无长期记忆')
      return
    }

    type StarNode = d3.SimulationNodeDatum & { id: number; label: string; color: string; r: number }
    const colors = [
      readThemeColor('--color-chart-1', '#127ea8'),
      readThemeColor('--color-hitl', '#b45790'),
      readThemeColor('--color-chart-3', '#c27a12'),
      readThemeColor('--color-accent-hover', '#0f6d90'),
    ]
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
      .style('position', 'absolute').style('background', readThemeColor('--color-surface-1', '#ffffff')).style('border', `1px solid ${readThemeColor('--color-border-subtle', '#dbe5ee')}`)
      .style('padding', '4px 8px').style('border-radius', '4px').style('font-size', '12px').style('color', readThemeColor('--color-text-1', '#1f2937'))
      .style('box-shadow', readThemeColor('--shadow-sm', '0 8px 18px rgba(15, 23, 42, 0.08)'))
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
  } catch (e: unknown) {
    starfieldError.value = e instanceof Error ? e.message : '长期记忆图谱渲染失败'
  }
}

function retryStarfield() {
  starfieldError.value = null
  nextTick(renderStarfield)
}

async function load() {
  loading.value = true
  error.value = null
  starfieldError.value = null
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
onBeforeUnmount(() => {
  if (searchTimer) {
    clearTimeout(searchTimer)
  }
})

watch(resolvedTheme, () => {
  if (openLayers.value.has('long_term')) {
    nextTick(renderStarfield)
  }
})

watch(detailDrawerOpen, (open) => {
  if (!open) {
    selectedRecord.value = null
  }
})
</script>

<style scoped>
.memory-page {
  display: grid;
  gap: var(--spacing-5);
  min-height: 100%;
  align-content: start;
  overflow-y: auto;
  padding: var(--spacing-5);
  box-sizing: border-box;
}

.search-bar { display: flex; align-items: center; }
.search-input { flex: 1; background: var(--color-surface-l1); border: 1px solid var(--color-surface-l2); color: var(--color-text-primary); padding: 8px 12px; border-radius: var(--radius-btn); font-size: 14px; outline: none; }
.search-input:focus { border-color: var(--color-ai-active); }
.search-spinner { margin-left: 8px; }
.search-results { display: grid; gap: var(--spacing-3); }
.result-row { display: flex; gap: 12px; align-items: flex-start; }
.similarity { font-size: 12px; color: var(--color-ai-active); flex-shrink: 0; padding-top: 2px; }
.result-content { font-size: 13px; color: var(--color-text-primary); }
.search-result-card { cursor: pointer; }
.search-result-card :deep(.system-card__body) { display: grid; gap: 10px; }
.result-meta { display: flex; flex-wrap: wrap; gap: 6px; }
.result-actions { display: flex; gap: 10px; flex-wrap: wrap; }
.result-chip {
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: 999px;
  padding: 2px 8px;
}
.layers { display: flex; flex-direction: column; gap: 8px; }
.layer-drawer { overflow: hidden; }
.layer-header { width: 100%; display: flex; justify-content: space-between; align-items: center; padding: 12px 16px; background: transparent; border: none; color: var(--color-text-primary); cursor: pointer; font-size: 14px; font-weight: 600; transition: background 150ms; }
.layer-header:hover { background: var(--color-surface-l2); }
.layer-count { font-size: 12px; color: var(--color-ai-active); margin-left: auto; margin-right: 8px; }
.layer-body { padding: 12px 16px; }
.mid-term-summary { font-size: 13px; color: var(--color-text-secondary); }
.anchor-list { display: flex; flex-direction: column; gap: 6px; }
.anchor-card { width: 100%; padding: 8px 10px; border-radius: 6px; border: none; text-align: left; border-left: 3px solid var(--color-surface-l2); background: var(--color-surface-l1); cursor: pointer; }
.anchor-card.anchor-blue { border-left-color: var(--color-accent); background: var(--color-accent-soft); }
.anchor-card.anchor-cyan { border-left-color: var(--color-info); background: color-mix(in srgb, var(--color-info) 10%, transparent); }
.anchor-card.anchor-gray { border-left-color: var(--color-text-3); }
.anchor-text { font-size: 13px; color: var(--color-text-primary); margin-bottom: 4px; }
.anchor-meta { display: flex; gap: 10px; align-items: center; }
.anchor-score { font-size: 11px; font-weight: 600; color: var(--color-ai-active); }
.anchor-time { font-size: 11px; color: var(--color-text-secondary); }
.starfield { min-height: 260px; width: 100%; position: relative; }
.fallback-anchor-list {
  display: grid;
  gap: var(--spacing-2);
}
.fallback-anchor-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  background: color-mix(in srgb, var(--color-surface-1) 92%, transparent);
  border: 1px solid var(--color-border-subtle);
  width: 100%;
  cursor: pointer;
}
.fallback-anchor-card__text {
  color: var(--color-text-1);
  font-size: 13px;
  line-height: 1.5;
}
.fallback-anchor-card__meta {
  color: var(--color-text-3);
  font-size: 12px;
  flex-shrink: 0;
}

.memory-drawer {
  display: grid;
  gap: 14px;
}

.memory-drawer__content,
.memory-drawer__source-copy {
  margin: 0;
  color: var(--color-text-1);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-drawer__meta {
  display: grid;
  gap: 10px;
}

.memory-drawer__meta-row {
  display: grid;
  gap: 4px;
}

.memory-drawer__meta-row span {
  color: var(--color-text-3);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

@media (max-width: 720px) {
  .memory-page {
    padding: var(--spacing-4);
  }

  .result-actions {
    flex-direction: column;
  }

  .fallback-anchor-card {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
