<template>
  <div class="metrics-page">
    <SystemPageHeader
      eyebrow="Narrative Metrics"
      title="叙事指标仪表盘"
      description="按章节查看张力、贴合度与人味波形，及时识别平坦区和疲劳段。"
    >
      <template #actions>
        <SystemButton v-if="warningInsights.length" variant="secondary" @click="warningDrawerOpen = true">
          查看预警 {{ warningInsights.length }}
        </SystemButton>
        <SystemButton variant="ghost" @click="refreshMetrics">刷新</SystemButton>
      </template>
    </SystemPageHeader>

    <SystemSkeleton v-if="currentState === 'loading'" :rows="8" show-header card />

    <SystemErrorState
      v-else-if="currentState === 'blocking'"
      title="指标历史加载失败"
      :message="error || '暂时无法加载章节指标。'"
      action-label="重新加载"
      @action="refreshMetrics"
    />

    <SystemEmpty
      v-else-if="currentState === 'empty'"
      title="还没有章节指标"
      description="先生成章节或运行一次评测，再回到这里查看趋势、预警和 8D 评分。"
    >
      <template #action>
        <SystemButton variant="primary" @click="refreshMetrics">刷新指标</SystemButton>
      </template>
    </SystemEmpty>

    <template v-else>
      <SystemStatusBanner
        v-if="chartError"
        status="partial-failure"
        title="趋势图已切换为摘要模式"
        :message="chartError"
        description="章节指标数据仍然可用，当前只影响图表渲染，不影响后续判断。"
      >
        <template #actions>
          <SystemButton variant="ghost" @click="retryChartRender">重试图表</SystemButton>
        </template>
      </SystemStatusBanner>

      <div class="summary-cards">
        <SystemCard v-for="stat in summaryStats" :key="stat.label" class="summary-card" tone="subtle">
          <div class="sc-val">{{ stat.value }}</div>
          <div class="sc-label">{{ stat.label }}</div>
        </SystemCard>
      </div>

      <SystemCard
        class="chart-card"
        title="章节趋势波形"
        description="点击节点可查看单章的 8D 评分、贴合度和人味拆解。"
      >
        <div class="chart-shell">
          <div v-if="!chartError" ref="chartEl" class="waveform-chart" />

          <SystemVisualizationFallback
            v-else
            title="趋势图渲染失败，已退回章节摘要"
            description="你仍可从章节列表快速定位异常章节，并继续进入场景 IDE。"
            :items="metricsFallbackItems"
          >
            <div class="metrics-fallback-list">
              <button
                v-for="metric in metrics"
                :key="metric.chapter"
                class="metrics-fallback-item"
                type="button"
                @click="selectedChapter = metric"
              >
                <span class="metrics-fallback-item__chapter">Ch{{ String(metric.chapter).padStart(2, '0') }}</span>
                <span class="metrics-fallback-item__meta">张力 {{ metric.tension.toFixed(1) }} · 贴合 {{ Math.round(metric.benchmarkAdherence * 100) }}%</span>
              </button>
            </div>

            <template #actions>
              <SystemButton variant="ghost" @click="retryChartRender">重新渲染</SystemButton>
            </template>
          </SystemVisualizationFallback>
        </div>
      </SystemCard>

    </template>

    <SystemDrawer
      v-model="chapterDrawerOpen"
      :title="selectedChapter ? `Ch${String(selectedChapter.chapter).padStart(2, '0')} 详情` : '章节详情'"
      description="章节细节改为抽屉查看，保留趋势图作为唯一首屏主视图。"
      size="360px"
    >
      <template v-if="selectedChapter">
        <div class="popup-body">
          <div class="popup-score">综合评分：{{ selectedChapter.score }}/10</div>
          <div class="popup-benchmark">
            <span>对标贴合 {{ Math.round(selectedChapter.benchmarkAdherence * 100) }}%</span>
            <span>人味 {{ Math.round(selectedChapter.benchmarkHumanness * 100) }}%</span>
          </div>

          <SystemVisualizationFallback
            v-if="radarError"
            title="8D 雷达图暂时不可用"
            description="已回退到维度摘要，不阻断当前章节分析。"
            :items="selectedChapterFallbackItems"
          >
            <template #actions>
              <SystemButton variant="ghost" @click="retryRadarRender">重试雷达图</SystemButton>
            </template>
          </SystemVisualizationFallback>
          <div v-else ref="radarEl" class="radar-8d" />

          <SystemButton variant="primary" @click="openInIDE(selectedChapter.chapter)">在场景IDE中打开</SystemButton>
        </div>
      </template>
    </SystemDrawer>

    <SystemDrawer
      v-model="warningDrawerOpen"
      title="质量预警"
      description="预警信息进入抽屉查看，避免与主图同屏竞争注意力。"
      size="380px"
    >
      <div class="warning-drawer">
        <SystemEmpty
          v-if="warningInsights.length === 0"
          title="当前没有预警"
          description="当前章节波形稳定，暂时不需要额外干预动作。"
        />
        <SystemCard v-for="warning in warningInsights" :key="warning.id" :title="warning.title" :description="warning.message" tone="subtle">
          <template #actions>
            <SystemButton size="sm" :variant="warning.actionVariant" @click="triggerWarningAction(warning.id)">
              {{ warning.actionLabel }}
            </SystemButton>
          </template>
        </SystemCard>
      </div>
    </SystemDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed, watch, nextTick } from 'vue'
import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, MarkPointComponent, RadarComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import axios from 'axios'
import { useRouter, useRoute } from 'vue-router'
import { projects } from '@/api/projects'
import { useAsyncViewState } from '@/composables/useAsyncViewState'
import { useThemeMode } from '@/composables/useThemeMode'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'
import SystemVisualizationFallback from '@/components/system/SystemVisualizationFallback.vue'

use([
  GridComponent,
  LineChart,
  MarkPointComponent,
  RadarChart,
  RadarComponent,
  TooltipComponent,
  VisualMapComponent,
  SVGRenderer,
])

const router = useRouter()
const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')
const { resolvedTheme } = useThemeMode()
const chartEl = ref<HTMLElement | null>(null)
let chart: EChartsType | null = null
const loading = ref(false)
const error = ref<string | null>(null)
const chartError = ref<string | null>(null)
const radarError = ref<string | null>(null)

interface ChapterMetric {
  chapter: number
  tension: number
  pacing: number
  score: number
  benchmarkAdherence: number
  benchmarkHumanness: number
  qd: number[]  // 8D quality dimensions [0..7]
  dimensions: Array<{ label: string; value: number; trend: string }>
}

function normalizeScore(value: number | undefined, fallback = 5): number {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return fallback
  }
  return value <= 1 ? Math.round(value * 100) / 10 : value
}

const metrics = ref<ChapterMetric[]>([])
const radarEl = ref<HTMLElement | null>(null)
let radarChart: EChartsType | null = null

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
      { label: '平均贴合', value: '--' },
      { label: '平均人味', value: '--' },
    ]
  }
  const avg = metrics.value.reduce((s, m) => s + m.tension, 0) / metrics.value.length
  const maxT = Math.max(...metrics.value.map(m => m.tension))
  const minT = Math.min(...metrics.value.map(m => m.tension))
  const avgAdherence = metrics.value.reduce((s, m) => s + m.benchmarkAdherence, 0) / metrics.value.length
  const avgHumanness = metrics.value.reduce((s, m) => s + m.benchmarkHumanness, 0) / metrics.value.length
  return [
    { label: '章节数', value: metrics.value.length },
    { label: '平均张力', value: avg.toFixed(1) },
    { label: '峰值张力', value: maxT },
    { label: '谷值张力', value: minT },
    { label: '平均贴合', value: `${Math.round(avgAdherence * 100)}%` },
    { label: '平均人味', value: `${Math.round(avgHumanness * 100)}%` },
  ]
})

const metricsFallbackItems = computed(() => summaryStats.value.slice(0, 4))

interface SelectedChapter {
  chapter: number
  score: number
  benchmarkAdherence: number
  benchmarkHumanness: number
  qd: number[]
  dimensions: Array<{ label: string; value: number; trend: string }>
}
const selectedChapter = ref<SelectedChapter | null>(null)
const chapterDrawerOpen = ref(false)
const warningDrawerOpen = ref(false)

const warningInsights = computed(() => {
  const items: Array<{
    id: 'flat' | 'fatigue'
    title: string
    message: string
    actionLabel: string
    actionVariant: 'primary' | 'ghost'
  }> = []

  if (flatWarning.value) {
    items.push({
      id: 'flat',
      title: '检测到平坦区',
      message: '最近章节存在连续低张力与低节奏段，建议尽快补强冲突和推进动作。',
      actionLabel: '一键调用 Planner',
      actionVariant: 'primary',
    })
  }

  if (fatigueWarning.value) {
    items.push({
      id: 'fatigue',
      title: '高压持续疲劳',
      message: '最近 3 章持续处于高压区，建议主动插入缓冲或情绪下行场景。',
      actionLabel: '插入下行场景',
      actionVariant: 'ghost',
    })
  }

  return items
})

const selectedChapterFallbackItems = computed(() => {
  if (!selectedChapter.value) return []

  return selectedChapter.value.dimensions.map((item) => ({
    label: item.label,
    value: typeof item.value === 'number' ? item.value.toFixed(1) : item.value,
  }))
})

const { currentState } = useAsyncViewState({
  loading,
  blocking: computed(() => Boolean(error.value)),
  empty: computed(() => !loading.value && !error.value && metrics.value.length === 0),
})

function readThemeColor(name: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

function getMetricPalette() {
  return {
    accent: readThemeColor('--color-chart-1', '#127ea8'),
    success: readThemeColor('--color-chart-2', '#198754'),
    warning: readThemeColor('--color-chart-3', '#c27a12'),
    danger: readThemeColor('--color-chart-4', '#c2413b'),
    area: readThemeColor('--color-chart-area', 'rgba(18, 126, 168, 0.2)'),
    grid: readThemeColor('--color-chart-grid', '#dbe5ee'),
    surface: readThemeColor('--color-surface-2', '#f7fafc'),
    textMuted: readThemeColor('--color-text-3', '#7a8794'),
  }
}

function buildOption(data: ChapterMetric[]) {
  const palette = getMetricPalette()
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
        color: [palette.success, palette.warning, palette.danger],
      },
    },
    xAxis: {
      type: 'category',
      data: xData,
      axisLine: { lineStyle: { color: palette.grid } },
      axisLabel: { color: palette.textMuted },
    },
    yAxis: {
      type: 'value',
      min: 0,
      max: 10,
      axisLine: { lineStyle: { color: palette.grid } },
      axisLabel: { color: palette.textMuted },
      splitLine: { lineStyle: { color: palette.grid } },
    },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      areaStyle: { color: palette.area },
      lineStyle: { width: 2, color: palette.accent },
      itemStyle: { color: palette.accent },
      markPoint: {
        data: markPoints.map(mp => ({
          coord: mp.coord,
          symbolSize: 12,
          itemStyle: { color: palette.accent },
        })),
      },
    }],
  }
}

function ensureChartInstance() {
  if (!chartEl.value) {
    chartError.value = '趋势图容器未就绪'
    return null
  }

  try {
    if (!chart) {
      chart = init(chartEl.value, undefined, { renderer: 'svg' })
    }
    chartError.value = null
    return chart
  } catch (e: unknown) {
    chart?.dispose()
    chart = null
    chartError.value = e instanceof Error ? e.message : '趋势图初始化失败'
    return null
  }
}

function renderPrimaryChart() {
  if (metrics.value.length === 0) {
    chart?.clear()
    return
  }

  const chartInstance = ensureChartInstance()
  if (!chartInstance) return

  try {
    chartInstance.setOption(buildOption(metrics.value), true)
    chartInstance.off('click')
    chartInstance.on('click', (params: { dataIndex: number }) => {
      const metric = metrics.value[params.dataIndex]
      if (metric) {
        selectedChapter.value = metric
      }
    })
  } catch (e: unknown) {
    chartError.value = e instanceof Error ? e.message : '趋势图渲染失败'
  }
}

async function refreshMetrics() {
  loading.value = true
  error.value = null
  chartError.value = null
  try {
    const res = await projects.metricsHistory(projectId.value)
    const payload = Array.isArray(res.data) ? res.data : []
    metrics.value = payload.map((item) => {
      const raw = item as typeof item & {
        avg_tension?: number
        pacing_score?: number
        overall_score?: number
        benchmark_adherence_score?: number
        benchmark_humanness_score?: number
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
        tension: normalizeScore(raw.avg_tension ?? item.quality_score, 5),
        pacing: normalizeScore(raw.pacing_score, 5),
        score: normalizeScore(raw.overall_score ?? item.quality_score, 5),
        benchmarkAdherence: typeof raw.benchmark_adherence_score === 'number' ? raw.benchmark_adherence_score : 0,
        benchmarkHumanness: typeof raw.benchmark_humanness_score === 'number' ? raw.benchmark_humanness_score : 0,
        qd: [
          raw.qd_01, raw.qd_02, raw.qd_03, raw.qd_04,
          raw.qd_05, raw.qd_06, raw.qd_07, raw.qd_08,
        ].map(v => normalizeScore(v, 5)) as number[],
        dimensions: [
          { label: '张力', value: normalizeScore(raw.avg_tension ?? item.quality_score, 5), trend: '→' },
          { label: '节奏', value: normalizeScore(raw.pacing_score, 5), trend: '↑' },
          { label: '贴合', value: Math.round((raw.benchmark_adherence_score ?? 0) * 100) / 10, trend: '→' },
          { label: '人味', value: Math.round((raw.benchmark_humanness_score ?? 0) * 100) / 10, trend: '→' },
        ],
      }
    })
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '指标历史加载失败'
    metrics.value = []
  } finally {
    loading.value = false
  }

  if (metrics.value.length === 0) {
    chart?.clear()
    selectedChapter.value = null
    return
  }

  await nextTick()
  renderPrimaryChart()
}

function callPlanner() {
  axios.post('/api/chapters/plan', { chapter: metrics.value.length + 1, summary: '' }).catch(() => {})
}
function insertRelief() {
  // trigger relief scene generation
}

function triggerWarningAction(kind: 'flat' | 'fatigue') {
  if (kind === 'flat') {
    callPlanner()
    return
  }

  insertRelief()
}

function openInIDE(chapter: number) {
  router.push(`/project/${projectId.value}/write?chapter=${chapter}`)
  selectedChapter.value = null
}

function renderRadar8D() {
  if (!radarEl.value || !selectedChapter.value) return

  try {
    if (!radarChart) {
      radarChart = init(radarEl.value, undefined, { renderer: 'svg' })
    }

    const palette = getMetricPalette()
    const qd = selectedChapter.value.qd
    radarChart.setOption({
      backgroundColor: 'transparent',
      radar: {
        indicator: [
          { name: '宣泄感', max: 10 }, { name: '金手指', max: 10 }, { name: '节奏', max: 10 },
          { name: '对白', max: 10 }, { name: '人物', max: 10 }, { name: '意义', max: 10 },
          { name: '钩子', max: 10 }, { name: '易读', max: 10 },
        ],
        axisName: { color: palette.textMuted, fontSize: 11 },
        splitArea: { areaStyle: { color: [palette.surface, 'transparent'] } },
        splitLine: { lineStyle: { color: palette.grid } },
      },
      series: [{
        type: 'radar',
        data: [{ value: qd, name: `Ch${String(selectedChapter.value.chapter).padStart(2, '0')}` }],
        areaStyle: { color: palette.area },
        lineStyle: { color: palette.accent, width: 2 },
        itemStyle: { color: palette.accent },
      }],
    })
    radarError.value = null
  } catch (e: unknown) {
    radarChart?.dispose()
    radarChart = null
    radarError.value = e instanceof Error ? e.message : '8D 雷达图渲染失败'
  }
}

function retryChartRender() {
  chartError.value = null
  nextTick(renderPrimaryChart)
}

function retryRadarRender() {
  radarError.value = null
  nextTick(renderRadar8D)
}

watch(selectedChapter, async (val) => {
  chapterDrawerOpen.value = Boolean(val)
  radarError.value = null
  if (val) await nextTick().then(renderRadar8D)
  else { radarChart?.dispose(); radarChart = null }
})

watch(chapterDrawerOpen, (open) => {
  if (!open) {
    selectedChapter.value = null
  }
})

watch(resolvedTheme, async () => {
  if (metrics.value.length > 0) {
    await nextTick()
    renderPrimaryChart()
  }

  if (selectedChapter.value) {
    await nextTick()
    renderRadar8D()
  }
})

onMounted(async () => {
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

.summary-cards {
  display: flex;
  gap: var(--spacing-sm);
  flex-wrap: wrap;
  flex-shrink: 0;
}
.summary-card {
  flex: 1;
  min-width: 120px;
  text-align: center;
}
.sc-val { font-size: var(--text-h2); font-weight: 700; }
.sc-label { font-size: var(--text-caption); color: var(--color-text-secondary); }

.chart-card :deep(.system-card__body) {
  position: relative;
}

.chart-shell {
  min-height: 180px;
  position: relative;
}

.waveform-chart { flex: 1; min-height: 180px; }
.metrics-fallback-list {
  display: grid;
  gap: var(--spacing-2);
}
.metrics-fallback-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  color: inherit;
  cursor: pointer;
}
.metrics-fallback-item__chapter {
  color: var(--color-text-1);
  font-weight: 600;
}
.metrics-fallback-item__meta {
  color: var(--color-text-2);
  font-size: 13px;
}

.warning-drawer {
  display: grid;
  gap: 12px;
}

.popup-header-title {
  font-weight: 600;
}
.popup-body { padding: var(--spacing-md); display: flex; flex-direction: column; gap: var(--spacing-sm); }
.radar-8d { height: 180px; width: 100%; }
.popup-score { font-size: var(--text-h2); font-weight: 700; }
.popup-benchmark {
  display: flex;
  justify-content: space-between;
  gap: var(--spacing-sm);
  color: var(--color-text-secondary);
  font-size: 13px;
}
.popup-dims { display: flex; flex-direction: column; gap: 4px; }
.popup-dim { display: flex; align-items: center; gap: var(--spacing-sm); font-size: 13px; }
.dim-bar { flex: 1; height: 4px; background: var(--color-surface-l2); border-radius: 2px; }
.dim-fill { height: 100%; background: var(--color-ai-active); border-radius: 2px; }
.dim-trend { color: var(--color-text-secondary); font-size: var(--text-caption); }

@media (max-width: 900px) {
  .metrics-fallback-item {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
