<template>
  <div class="plot-canvas-page app-page-surface">
    <section class="app-hero-card">
      <div>
        <p class="app-eyebrow">Plot Canvas</p>
        <h1 class="app-hero-title">剧情画布</h1>
        <p class="app-hero-copy">维护当前卷目标与剧情节点张力，让项目主页、写前检查和剧情图谱保持一致。</p>
      </div>
      <div class="app-hero-meta">
        <span class="app-pill">项目 {{ projectId }}</span>
        <span class="app-pill app-pill--accent">节点 {{ nodes.length }}</span>
        <span class="app-pill">{{ volumeGoalDraft.trim() ? '卷目标已配置' : '卷目标待配置' }}</span>
      </div>
    </section>

    <div v-if="error" class="error-card">
      <NCard>
        <p style="color: var(--color-error)">加载失败：{{ error }}</p>
        <NButton variant="ghost" @click="loadPlot">重试</NButton>
      </NCard>
    </div>

    <div v-else class="plot-layout">
      <div class="flow-container">
        <VueFlow
          :nodes="nodes"
          :edges="edges"
          :node-types="nodeTypes"
          fit-view-on-init
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
          <p>暂无剧情节点（项目：{{ projectId }}）</p>
        </div>
      </div>

      <aside class="right-panel">
        <NCard>
          <h3>当前卷目标</h3>
          <textarea
            v-model="volumeGoalDraft"
            class="goal-input"
            placeholder="输入当前卷的核心推进目标，保存后首页和章节撰写前检会同步更新。"
            rows="5"
          />
          <div class="goal-actions">
            <NButton :disabled="savingGoal || !volumeGoalDraft.trim()" @click="saveVolumeGoal">
              {{ savingGoal ? '保存中…' : '保存卷目标' }}
            </NButton>
          </div>
          <p class="goal-help">没有完整 PlotGraph 时，会自动创建一个激活节点作为当前卷目标。</p>
        </NCard>
        <NCard>
          <h3>全局张力曲线</h3>
          <div ref="chartEl" class="tension-chart"></div>
        </NCard>
        <NCard style="margin-top: 16px">
          <h3>选中节点</h3>
          <div v-if="selectedNode">
            <p><strong>状态：</strong>{{ selectedNode.data?.status }}</p>
            <label>张力值：{{ localTension }}</label>
            <NSlider
              v-model="localTension"
              :min="0"
              :max="10"
              gradient="linear-gradient(to right, #2ef2ff, #f5a623, #ff4040)"
            />
          </div>
          <p v-else style="color: var(--color-text-secondary)">点击节点查看详情</p>
        </NCard>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, markRaw, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import { VueFlow, type Node, type Edge, type NodeComponent } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import '@vue-flow/core/dist/style.css'
import * as echarts from 'echarts'
import NCard from '@/components/common/NCard.vue'
import NButton from '@/components/common/NButton.vue'
import NSlider from '@/components/common/NSlider.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import NarrativeNode from './NarrativeNode.vue'
import { projects } from '@/api/projects'
import type { PlotNode, PlotEdge, PlotGraphData } from '@/types/api'

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
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

const STATUS_COLORS: Record<string, string> = {
  ACTIVE: '#2ef2ff',
  COMPLETED: '#3f5a48',
  PENDING: '#2d2f3a',
}

const nodeTypes: Record<string, NodeComponent> = { narrative: markRaw(NarrativeNode) as unknown as NodeComponent }

function mapNode(n: PlotNode, idx: number): Node {
  return {
    id: n.id,
    type: 'narrative',
    position: { x: (idx % 4) * 280, y: Math.floor(idx / 4) * 180 },
    data: {
      label: (n as Record<string, unknown>).title ?? (n as Record<string, unknown>).summary ?? n.id,
      status: n.status,
      tension: n.tension,
      borderColor: STATUS_COLORS[n.status] ?? '#2d2f3a',
    },
  }
}

function mapEdge(e: PlotEdge, idx: number): Edge {
  const source = (e as PlotEdge & { from_id?: string }).source ?? (e as PlotEdge & { from_id?: string }).from_id
  const target = (e as PlotEdge & { to_id?: string }).target ?? (e as PlotEdge & { to_id?: string }).to_id
  return { id: `e-${idx}`, source, target, style: { stroke: '#555' } }
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
  chart?.dispose()
  chart = echarts.init(chartEl.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 8, bottom: 18, left: 8, right: 8 },
    xAxis: { type: 'category', data: tensions.map((_, i) => `Ch${i + 1}`), show: false },
    yAxis: { type: 'value', min: 0, max: 10, show: false },
    series: [{
      type: 'line', data: tensions, smooth: true, symbol: 'none',
      lineStyle: { color: '#2ef2ff', width: 2 },
      areaStyle: { color: { type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
        colorStops: [{ offset: 0, color: 'rgba(46,242,255,0.4)' }, { offset: 1, color: 'rgba(46,242,255,0)' }],
      }},
    }],
  })
}

onMounted(loadPlot)
</script>

<style scoped>
.plot-canvas-page {
  height: 100%;
  display: flex;
  flex-direction: column;
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
.tension-chart { height: 120px; width: 100%; }
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
.error-card { padding: 16px; }
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
