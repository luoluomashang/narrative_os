<template>
  <div class="metrics-page">
    <div class="metrics-header">
      <span class="metrics-title">叙事指标仪表盘</span>
      <NButton variant="ghost" @click="refreshMetrics">刷新</NButton>
    </div>

    <!-- Chapter summary cards -->
    <div class="summary-cards">
      <div class="summary-card" v-for="stat in summaryStats" :key="stat.label">
        <div class="sc-val">{{ stat.value }}</div>
        <div class="sc-label">{{ stat.label }}</div>
      </div>
    </div>

    <!-- AI warning banners -->
    <transition-group name="slide-in-right" tag="div" class="warning-banners">
      <div v-if="flatWarning" key="flat" class="warn-banner flat">
        <span>📊 检测到平坦区（2+章节低张力）</span>
        <NButton variant="primary" @click="callPlanner">一键调用 Planner</NButton>
      </div>
      <div v-if="fatigueWarning" key="fatigue" class="warn-banner fatigue">
        <span>🔥 高压持续疲劳（3+章节高张力）</span>
        <NButton variant="ghost" @click="insertRelief">插入下行场景</NButton>
      </div>
    </transition-group>

    <!-- Waveform area chart -->
    <div v-if="metrics.length > 0" ref="chartEl" class="waveform-chart" />
    <div v-else class="empty-state">暂无章节指标数据，请先生成章节后再查看趋势。</div>

    <!-- Chapter detail popup -->
    <div v-if="selectedChapter" class="chapter-popup">
      <div class="popup-header">
        <span>Ch{{ String(selectedChapter.chapter).padStart(2, '0') }} 详情</span>
        <button class="popup-close" @click="selectedChapter = null">✕</button>
      </div>
      <div class="popup-body">
        <div class="popup-score">综合评分：{{ selectedChapter.score }}/10</div>
        <!-- 8D Radar Chart -->
        <div ref="radarEl" class="radar-8d" />
        <NButton variant="primary" @click="openInIDE(selectedChapter.chapter)">在场景IDE中打开</NButton>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import NButton from '@/components/common/NButton.vue'
import axios from 'axios'
import { useRouter, useRoute } from 'vue-router'
import { projects } from '@/api/projects'

const router = useRouter()
const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')
const chartEl = ref<HTMLElement | null>(null)
let chart: echarts.ECharts | null = null

interface ChapterMetric {
  chapter: number
  tension: number
  pacing: number
  score: number
  qd: number[]  // 8D quality dimensions [0..7]
  dimensions: Array<{ label: string; value: number; trend: string }>
}

const metrics = ref<ChapterMetric[]>([])
const radarEl = ref<HTMLElement | null>(null)
let radarChart: echarts.ECharts | null = null

// Derived warnings
const flatWarning = computed(() => {
  const recent = metrics.value.slice(-3)
  return recent.length >= 2 && recent.filter(m => m.tension < 3 && m.pacing < 0.4).length >= 2
})
const fatigueWarning = computed(() => {
  const recent = metrics.value.slice(-3)
  return recent.length === 3 && recent.every(m => m.tension > 8)
})

const summaryStats = computed(() => {
  if (metrics.value.length === 0) {
    return [
      { label: '章节数', value: 0 },
      { label: '平均张力', value: '0.0' },
      { label: '峰值张力', value: 0 },
      { label: '谷值张力', value: 0 },
    ]
  }
  const avg = metrics.value.reduce((s, m) => s + m.tension, 0) / metrics.value.length
  const maxT = Math.max(...metrics.value.map(m => m.tension))
  const minT = Math.min(...metrics.value.map(m => m.tension))
  return [
    { label: '章节数', value: metrics.value.length },
    { label: '平均张力', value: avg.toFixed(1) },
    { label: '峰值张力', value: maxT },
    { label: '谷值张力', value: minT },
  ]
})

interface SelectedChapter {
  chapter: number
  score: number
  qd: number[]
  dimensions: Array<{ label: string; value: number; trend: string }>
}
const selectedChapter = ref<SelectedChapter | null>(null)

function buildOption(data: ChapterMetric[]) {
  const xData = data.map(m => `Ch${String(m.chapter).padStart(2, '0')}`)
  const yData = data.map(m => m.tension)

  // Detect peaks/valleys/turns
  const markPoints: Array<{ coord: [string, number]; symbol: string }> = []
  for (let i = 1; i < data.length - 1; i++) {
    const prev = data[i - 1].tension
    const cur = data[i].tension
    const next = data[i + 1].tension
    if (cur > prev && cur > next) {
      markPoints.push({ coord: [xData[i], cur], symbol: 'triangle' })
    } else if (cur < prev && cur < next) {
      markPoints.push({ coord: [xData[i], cur], symbol: 'pin' })
    } else if (Math.abs(cur - prev) > 2) {
      markPoints.push({ coord: [xData[i], cur], symbol: 'circle' })
    }
  }

  return {
    backgroundColor: 'transparent',
    tooltip: {
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) => {
        const p = params[0]
        return `${p.name}  张力: ${p.value}`
      },
    },
    visualMap: {
      show: false,
      type: 'continuous',
      seriesIndex: 0,
      min: 0,
      max: 10,
      inRange: {
        color: ['#3f5a48', '#f5a623', '#ff2e88'],
      },
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: '#2d2f3a' } },
      axisLabel: { color: '#999' },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 10,
      axisLine: { lineStyle: { color: '#2d2f3a' } },
      axisLabel: { color: '#999' },
      splitLine: { lineStyle: { color: '#1b1c22' } },
    },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      areaStyle: { opacity: 0.3 },
      lineStyle: { width: 2 },
      markPoint: {
        data: markPoints.map(mp => ({
          coord: mp.coord,
          symbolSize: 12,
          itemStyle: { color: '#2ef2ff' },
        })),
      },
    }],
  }
}

async function refreshMetrics() {
  metrics.value = []
  try {
    const res = await projects.metricsHistory(projectId.value)
    if (Array.isArray(res.data) && res.data.length > 0) {
      metrics.value = res.data.map((item) => {
        const raw = item as typeof item & {
          avg_tension?: number
          pacing_score?: number
          overall_score?: number
          qd_01?: number
          qd_02?: number
          qd_03?: number
          qd_04?: number
          qd_05?: number
          qd_06?: number
          qd_07?: number
          qd_08?: number
        }

        return {
        chapter: item.chapter,
        tension: raw.avg_tension ?? item.quality_score ?? 5,
        pacing: raw.pacing_score ?? 0.5,
        score: raw.overall_score ?? item.quality_score ?? 5,
        qd: [
          raw.qd_01, raw.qd_02, raw.qd_03, raw.qd_04,
          raw.qd_05, raw.qd_06, raw.qd_07, raw.qd_08,
        ].map(v => typeof v === 'number' ? Math.round(v * 10) : 5) as number[],
        dimensions: [
          { label: '张力', value: raw.avg_tension ?? 5, trend: '→' },
          { label: '节奏', value: raw.pacing_score ?? 5, trend: '↑' },
        ],
      }})
      chart?.setOption(buildOption(metrics.value))
      chart?.off('click')
      chart?.on('click', (params: { dataIndex: number }) => {
        const m = metrics.value[params.dataIndex]
        if (m) selectedChapter.value = m
      })
    }
  } catch {
    metrics.value = []
  }

  chart?.clear()
  if (metrics.value.length === 0) {
    selectedChapter.value = null
    return
  }

  chart?.setOption(buildOption(metrics.value))
  chart?.off('click')
  chart?.on('click', (params: { dataIndex: number }) => {
    const m = metrics.value[params.dataIndex]
    if (m) selectedChapter.value = m
  })
}

function callPlanner() {
  axios.post('/api/chapters/plan', { chapter: metrics.value.length + 1, summary: '' }).catch(() => {})
}
function insertRelief() {
  // trigger relief scene generation
}
function openInIDE(chapter: number) {
  router.push(`/project/${projectId.value}/write?chapter=${chapter}`)
  selectedChapter.value = null
}

function renderRadar8D() {
  if (!radarEl.value || !selectedChapter.value) return
  if (!radarChart) radarChart = echarts.init(radarEl.value, null, { renderer: 'svg' })
  const qd = selectedChapter.value.qd
  radarChart.setOption({
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '宣泄感', max: 10 }, { name: '金手指', max: 10 }, { name: '节奏', max: 10 },
        { name: '对白', max: 10 }, { name: '人物', max: 10 }, { name: '意义', max: 10 },
        { name: '钩子', max: 10 }, { name: '易读', max: 10 },
      ],
      axisName: { color: '#999', fontSize: 11 },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'] } },
      splitLine: { lineStyle: { color: '#2d2f3a' } },
    },
    series: [{
      type: 'radar',
      data: [{ value: qd, name: `Ch${String(selectedChapter.value.chapter).padStart(2, '0')}` }],
      areaStyle: { color: 'rgba(46,242,255,0.2)' },
      lineStyle: { color: '#2ef2ff', width: 2 },
      itemStyle: { color: '#2ef2ff' },
    }],
  })
}

watch(selectedChapter, async (val) => {
  if (val) await nextTick().then(renderRadar8D)
  else { radarChart?.dispose(); radarChart = null }
})

onMounted(async () => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value, null, { renderer: 'svg' })
  await refreshMetrics()
})

onBeforeUnmount(() => { chart?.dispose(); radarChart?.dispose() })
</script>

<style scoped>
.metrics-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: var(--spacing-md);
  gap: var(--spacing-md);
  box-sizing: border-box;
  position: relative;
}
.metrics-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.metrics-title { font-size: var(--text-h2); font-weight: var(--weight-h2); }

/* Summary cards */
.summary-cards {
  display: flex;
  gap: var(--spacing-sm);
  flex-shrink: 0;
}
.summary-card {
  flex: 1;
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm) var(--spacing-md);
  text-align: center;
}
.sc-val { font-size: var(--text-h2); font-weight: 700; }
.sc-label { font-size: var(--text-caption); color: var(--color-text-secondary); }

/* Warning banners */
.warning-banners { display: flex; flex-direction: column; gap: 4px; flex-shrink: 0; }
.warn-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-card);
  font-size: 14px;
}
.warn-banner.flat { background: color-mix(in srgb, var(--color-warning) 15%, transparent); border: 1px solid var(--color-warning); }
.warn-banner.fatigue { background: color-mix(in srgb, var(--color-hitl) 15%, transparent); border: 1px solid var(--color-hitl); }

/* Waveform chart */
.waveform-chart { flex: 1; min-height: 180px; }

.empty-state {
  flex: 1;
  min-height: 180px;
  border: 1px dashed var(--color-surface-l2);
  border-radius: var(--radius-card);
  color: var(--color-text-secondary);
  font-size: 13px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 16px;
}

/* Chapter popup */
.chapter-popup {
  position: absolute;
  bottom: var(--spacing-xl);
  right: var(--spacing-xl);
  width: 300px;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-ai-active);
  border-radius: var(--radius-modal);
  overflow: hidden;
  z-index: 10;
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.popup-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  font-weight: 600;
}
.popup-close {
  background: none; border: none; color: var(--color-text-secondary); cursor: pointer; font-size: 14px;
}
.popup-body { padding: var(--spacing-md); display: flex; flex-direction: column; gap: var(--spacing-sm); }
.radar-8d { height: 180px; width: 100%; }
.popup-score { font-size: var(--text-h2); font-weight: 700; }
.popup-dims { display: flex; flex-direction: column; gap: 4px; }
.popup-dim { display: flex; align-items: center; gap: var(--spacing-sm); font-size: 13px; }
.dim-bar { flex: 1; height: 4px; background: var(--color-surface-l2); border-radius: 2px; }
.dim-fill { height: 100%; background: var(--color-ai-active); border-radius: 2px; }
.dim-trend { color: var(--color-text-secondary); font-size: var(--text-caption); }
</style>
