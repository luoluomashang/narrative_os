<template>
  <div class="plot-canvas-page app-page-surface">
    <SystemPageHeader
      eyebrow="Plot Canvas"
      title="剧情画布"
      description="维护当前卷目标与剧情节点张力，让项目主页、写前检查和剧情图谱保持一致。"
    >
      <template #meta>
        <span class="plot-meta-pill">项目 {{ projectId }}</span>
        <span class="plot-meta-pill plot-meta-pill--accent">节点 {{ nodes.length }}</span>
        <span class="plot-meta-pill">{{ volumeGoalDraft.trim() ? '卷目标已配置' : '卷目标待配置' }}</span>
      </template>
    </SystemPageHeader>

    <SystemErrorState
      v-if="error"
      class="error-card"
      :message="`加载失败：${error}`"
      action-label="重试"
      @action="loadPlot"
    />

    <div v-else class="plot-layout">
      <div class="flow-container">
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :node-types="nodeTypes"
          fit-view-on-init
          @node-click="onNodeSelect"
        >
          <Background />
          <Controls />
          <MiniMap />
        </VueFlow>
        <div v-if="loading" class="loading-overlay">
          <NBreathingLight :size="12" />
          <span>加载剧情图谱…</span>
        </div>
        <div v-if="!loading && nodes.length === 0 && !error" class="empty-state">
          <SystemEmpty title="暂无剧情节点" :description="`项目 ${projectId} 还没有可视化剧情节点。`" />
        </div>
      </div>

      <aside class="right-panel">
        <SystemCard class="sidebar-nav-card" tone="subtle">
          <div class="sidebar-nav">
            <SystemButton size="sm" :variant="activeSidebar === 'goal' ? 'primary' : 'ghost'" @click="activeSidebar = 'goal'">卷目标</SystemButton>
            <SystemButton size="sm" :variant="activeSidebar === 'curve' ? 'primary' : 'ghost'" @click="activeSidebar = 'curve'">张力曲线</SystemButton>
            <SystemButton size="sm" :variant="activeSidebar === 'selected' ? 'primary' : 'ghost'" @click="activeSidebar = 'selected'">选中节点</SystemButton>
          </div>
          <p class="sidebar-copy">
            {{ activeSidebar === 'goal'
              ? '默认只保留当前卷目标编辑。'
              : activeSidebar === 'curve'
                ? '张力曲线改为按需查看，避免和卷目标同屏竞争。'
                : '点击画布节点后自动切到详情面板。'
            }}
          </p>
        </SystemCard>

        <SystemCard v-if="activeSidebar === 'goal'" title="当前卷目标">
          <h3>当前卷目标</h3>
          <textarea
            v-model="volumeGoalDraft"
            class="goal-input"
            placeholder="输入当前卷的核心推进目标，保存后首页和章节撰写前检会同步更新。"
            rows="5"
          />
          <div class="goal-actions">
            <SystemButton :disabled="savingGoal || !volumeGoalDraft.trim()" :loading="savingGoal" @click="saveVolumeGoal">
              {{ savingGoal ? '保存中…' : '保存卷目标' }}
            </SystemButton>
          </div>
          <p class="goal-help">没有完整 PlotGraph 时，会自动创建一个激活节点作为当前卷目标。</p>
        </SystemCard>
        <SystemCard v-else-if="activeSidebar === 'curve'" title="全局张力曲线">
          <div ref="chartEl" class="tension-chart"></div>
        </SystemCard>
        <SystemCard v-else title="选中节点" class="selected-card">
          <div v-if="selectedNode">
            <p><strong>状态：</strong>{{ selectedNode.data?.status }}</p>
            <label>张力值：{{ localTension }}</label>
            <NSlider
              v-model="localTension"
              :min="0"
              :max="10"
              gradient="linear-gradient(to right, var(--color-accent), var(--color-warning), var(--color-danger))"
            />
          </div>
          <p v-else style="color: var(--color-text-secondary)">点击节点查看详情</p>
        </SystemCard>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, markRaw, nextTick, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { VueFlow, type Node, type Edge, type NodeComponent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import { LineChart } from 'echarts/charts'
import { GridComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import NSlider from '@/components/common/NSlider.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import NarrativeNode from './NarrativeNode.vue'
import { projects } from '@/api/projects'
import { useThemeMode } from '@/composables/useThemeMode'
import type { PlotNode, PlotEdge, PlotGraphData } from '@/types/api'

use([LineChart, GridComponent, SVGRenderer])

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')
const loading = ref(false)
const savingGoal = ref(false)
const error = ref<string | null>(null)
const nodes = ref<Node[]>([])
const edges = ref<Edge[]>([])
const selectedNode = ref<Node | null>(null)
const localTension = ref(5)
const volumeGoalDraft = ref('')
const activeSidebar = ref<'goal' | 'curve' | 'selected'>('goal')
const chartEl = ref<HTMLElement | null>(null)
const lastTensions = ref<number[]>([])
const { resolvedTheme } = useThemeMode()
let chart: EChartsType | null = null

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: 'var(--color-accent)',
  COMPLETED: 'var(--color-success)',
  PENDING: 'var(--color-surface-4)',
}

const nodeTypes: Record<string, NodeComponent> = { narrative: markRaw(NarrativeNode) as unknown as NodeComponent }

function readThemeColor(variable: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

function mapNode(n: PlotNode, idx: number): Node {
  return {
    id: n.id,
    type: 'narrative',
    position: { x: (idx % 4) * 280, y: Math.floor(idx / 4) * 180 },
    data: {
      label: (n as Record<string, unknown>).title ?? (n as Record<string, unknown>).summary ?? n.id,
      status: n.status,
      tension: n.tension,
      borderColor: STATUS_COLORS[n.status] ?? 'var(--color-surface-4)',
    },
  }
}

function mapEdge(e: PlotEdge, idx: number): Edge {
  const source = (e as PlotEdge & { from_id?: string }).source ?? (e as PlotEdge & { from_id?: string }).from_id
  const target = (e as PlotEdge & { to_id?: string }).target ?? (e as PlotEdge & { to_id?: string }).to_id
  return { id: `e-${idx}`, source, target, style: { stroke: 'var(--color-border-strong)' } }
}

function onNodeSelect(event: { node: Node }) {
  selectedNode.value = event.node
  localTension.value = Number(event.node.data?.tension ?? 5)
  activeSidebar.value = 'selected'
}

async function loadPlot() {
  loading.value = true
  error.value = null
  try {
    const res = await projects.plot(projectId.value as string)
    const plotNodes = res.data.nodes ?? []
    const plotEdges = res.data.edges ?? []
    nodes.value = plotNodes.map(mapNode)
    edges.value = plotEdges.map(mapEdge)
    volumeGoalDraft.value = (res.data as PlotGraphData & { current_volume_goal?: string }).current_volume_goal ?? ''
    await nextTick()
    renderChart(plotNodes.map((n) => n.tension))
    labelFlowControls()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

async function saveVolumeGoal() {
  const nextGoal = volumeGoalDraft.value.trim()
  if (!nextGoal) return
  savingGoal.value = true
  error.value = null
  try {
    const res = await projects.updatePlotVolumeGoal(projectId.value as string, nextGoal)
    const plotNodes = res.data.nodes ?? []
    const plotEdges = res.data.edges ?? []
    nodes.value = plotNodes.map(mapNode)
    edges.value = plotEdges.map(mapEdge)
    volumeGoalDraft.value = (res.data as PlotGraphData & { current_volume_goal?: string }).current_volume_goal ?? nextGoal
    await nextTick()
    renderChart(plotNodes.map((n) => n.tension))
    labelFlowControls()
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '保存卷目标失败'
  } finally {
    savingGoal.value = false
  }
}

function labelFlowControls() {
  window.requestAnimationFrame(() => {
    const labels = ['放大', '缩小', '适应视图', '切换交互']
    document.querySelectorAll<HTMLButtonElement>('.vue-flow__controls button').forEach((button, index) => {
      const label = labels[index] ?? '画布控制'
      button.setAttribute('title', label)
      button.setAttribute('aria-label', label)
    })
  })
}

function renderChart(tensions: number[]) {
  if (!chartEl.value) return
  lastTensions.value = tensions
  chart?.dispose()
  chart = init(chartEl.value, undefined, { renderer: 'svg' })
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 8, bottom: 18, left: 8, right: 8 },
    xAxis: { type: 'category', data: tensions.map((_, i) => `Ch${i + 1}`), show: false },
    yAxis: { type: 'value', min: 0, max: 10, show: false },
    series: [{
      type: 'line', data: tensions, smooth: true, symbol: 'none',
      lineStyle: { color: readThemeColor('--color-chart-1', '#127ea8'), width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [
          { offset: 0, color: readThemeColor('--color-chart-area', 'rgba(18, 126, 168, 0.2)') },
          { offset: 1, color: 'transparent' },
        ],
      }},
    }],
  })
}

onMounted(loadPlot)

watch(resolvedTheme, () => {
  if (lastTensions.value.length) {
    renderChart(lastTensions.value)
  }
})
</script>

<style scoped>
.plot-canvas-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.plot-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.plot-meta-pill--accent {
  background: var(--color-accent-soft);
  color: var(--color-accent);
}

.plot-layout {
  display: flex;
  gap: 16px;
  flex: 1;
  min-height: 0;
}

.flow-container {
  flex: 1; background: var(--color-surface-l1);
  border-radius: var(--radius-card); border: 1px solid var(--color-surface-l2);
  position: relative; min-height: 400px; height: 100%; overflow: hidden;
}
.right-panel { width: 260px; flex-shrink: 0; overflow-y: auto; }
.sidebar-nav-card :deep(.system-card__body) { gap: 10px; }
.sidebar-nav { display: flex; gap: 8px; flex-wrap: wrap; }
.sidebar-copy { margin: 0; color: var(--color-text-secondary); font-size: 13px; line-height: 1.6; }
.tension-chart { height: 120px; width: 100%; }
.selected-card { margin-top: 16px; }
.goal-input {
  width: 100%;
  resize: vertical;
  min-height: 108px;
  margin-top: 8px;
  padding: 10px 12px;
  border-radius: var(--radius-btn);
  border: 1px solid var(--color-surface-l2);
  background: var(--color-base);
  color: var(--color-text-primary);
}
.goal-actions { margin-top: 12px; display: flex; justify-content: flex-end; }
.goal-help { margin-top: 10px; font-size: 12px; color: var(--color-text-secondary); line-height: 1.5; }
.loading-overlay, .empty-state {
  position: absolute; inset: 0; display: flex; align-items: center;
  justify-content: center; gap: 8px; color: var(--color-text-secondary);
}
.empty-state :deep(.system-empty) {
  width: min(420px, calc(100% - 32px));
}

.error-card { padding: 0 16px; }
h3 { font-size: var(--text-h2); margin-bottom: 12px; }

@media (max-width: 960px) {
  .plot-layout {
    flex-direction: column;
  }

  .right-panel {
    width: 100%;
  }
}
</style>
