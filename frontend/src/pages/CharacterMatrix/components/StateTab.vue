<template>
  <div class="state-tab">
    <!-- Radar Chart -->
    <div class="state-section">
      <h4 class="section-title">角色六维雷达</h4>
      <div ref="radarEl" class="radar-chart"></div>
    </div>
    <!-- Arc Timeline -->
    <div class="state-section">
      <h4 class="section-title">弧光时间线</h4>
      <div v-if="!hasTimeline" class="timeline-empty">尚未生成章节，暂无时间线数据</div>
      <div v-else ref="timelineEl" class="timeline-chart"></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { LineChart, RadarChart } from 'echarts/charts'
import { GridComponent, RadarComponent, TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useThemeMode } from '@/composables/useThemeMode'
import type { CharacterDetail } from '@/types/api'

use([GridComponent, LineChart, RadarChart, RadarComponent, TooltipComponent, SVGRenderer])

const props = defineProps<{
  model: CharacterDetail
}>()

const radarEl = ref<HTMLElement | null>(null)
const timelineEl = ref<HTMLElement | null>(null)
let radarChart: EChartsType | null = null
let timelineChart: EChartsType | null = null
let resizeObserver: ResizeObserver | null = null
const { resolvedTheme } = useThemeMode()

type SnapshotPoint = { chapter: number; arc_stage: string; emotion: string; health: number }

const hasTimeline = computed(() => (props.model.snapshot_history?.length ?? 0) >= 2)

const ARC_STAGES = ['防御', '裂缝', '代偿', '承认', '改变']

function readThemeColor(variable: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

function calcRadarData(d: CharacterDetail): number[] {
  const EMOTION_SCORE: Record<string, number> = {
    平静: 8, 开心: 9, 愉快: 9, 兴奋: 7,
    焦虑: 4, 紧张: 5, 愤怒: 2, 恐惧: 3, 悲伤: 4,
  }
  const arcIdx = ARC_STAGES.indexOf(d.arc_stage)
  return [
    Math.round((d.health ?? 1) * 10),
    EMOTION_SCORE[d.emotion] ?? 5,
    arcIdx >= 0 ? (arcIdx + 1) * 2 : 2,
    Math.min(Object.keys(d.relationships ?? {}).length * 2, 10),
    Math.min(d.memory?.length ?? 0, 10),
    Math.min((d.behavior_constraints?.length ?? 0) * 2, 10),
  ]
}

function renderRadar() {
  if (!radarEl.value || !props.model) return
  if (!radarChart) radarChart = init(radarEl.value, undefined, { renderer: 'svg' })
  const data = calcRadarData(props.model)
  radarChart.setOption({
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '生命值', max: 10 },
        { name: '情绪稳定', max: 10 },
        { name: '弧光进度', max: 10 },
        { name: '关系密度', max: 10 },
        { name: '记忆丰富', max: 10 },
        { name: '约束严格', max: 10 },
      ],
      axisName: { color: readThemeColor('--color-text-3', '#7a8794') },
      splitArea: { areaStyle: { color: [readThemeColor('--color-surface-2', '#f7fafc'), readThemeColor('--color-surface-3', '#edf3f8')] } },
    },
    series: [{
      type: 'radar',
      data: [{ value: data, name: props.model.name }],
      areaStyle: { color: readThemeColor('--color-chart-area', 'rgba(18, 126, 168, 0.2)') },
      lineStyle: { color: readThemeColor('--color-chart-1', '#127ea8') },
      itemStyle: { color: readThemeColor('--color-chart-1', '#127ea8') },
    }],
  })
}

function renderTimeline() {
  if (!timelineEl.value || !hasTimeline.value) return
  if (!timelineChart) timelineChart = init(timelineEl.value, undefined, { renderer: 'svg' })
  const history = (props.model.snapshot_history ?? []) as SnapshotPoint[]
  const xData = history.map((s: SnapshotPoint) => `第${s.chapter}章`)
  const yData = history.map((s: SnapshotPoint) => {
    const idx = ARC_STAGES.indexOf(s.arc_stage)
    return idx >= 0 ? idx : 0
  })
  timelineChart.setOption({
    backgroundColor: 'transparent',
    xAxis: { type: 'category', data: xData, axisLabel: { color: readThemeColor('--color-text-3', '#7a8794'), fontSize: 11 } },
    yAxis: {
      type: 'value', min: 0, max: 4,
      axisLabel: { formatter: (v: number) => ARC_STAGES[v] ?? '', color: readThemeColor('--color-text-3', '#7a8794'), fontSize: 11 },
      splitLine: { lineStyle: { color: readThemeColor('--color-border-subtle', '#dbe5ee') } },
    },
    series: [{
      type: 'line',
      data: yData,
      smooth: true,
      lineStyle: { color: readThemeColor('--color-chart-1', '#127ea8') },
      itemStyle: { color: readThemeColor('--color-chart-1', '#127ea8') },
      areaStyle: { color: readThemeColor('--color-chart-area', 'rgba(18, 126, 168, 0.2)') },
    }],
    grid: { left: 60, right: 20, top: 10, bottom: 30 },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params
        return `${p.name}<br/>弧光：${ARC_STAGES[p.value] ?? '未知'}`
      },
    },
  })
}

function renderAll() {
  nextTick(() => {
    renderRadar()
    renderTimeline()
  })
}

watch(() => props.model, renderAll, { deep: true })
watch(resolvedTheme, renderAll)

onMounted(() => {
  renderAll()
  // Handle container resize
  if (radarEl.value) {
    resizeObserver = new ResizeObserver(() => {
      radarChart?.resize()
      timelineChart?.resize()
    })
    resizeObserver.observe(radarEl.value)
  }
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  radarChart?.dispose()
  timelineChart?.dispose()
})
</script>

<style scoped>
.state-tab { padding: 4px 0; }
.state-section { margin-bottom: 16px; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.radar-chart { height: 240px; width: 100%; }
.timeline-chart { height: 180px; width: 100%; }
.timeline-empty {
  padding: 24px;
  text-align: center;
  color: var(--color-text-secondary);
  font-size: 13px;
}
</style>
