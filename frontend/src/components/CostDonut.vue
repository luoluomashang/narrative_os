<template>
  <div class="cost-donut" :style="{ width: `${size}px`, height: `${size}px` }" ref="containerRef">
    <div ref="chartEl" class="chart-inner" />
    <!-- Center text -->
    <div class="donut-center">
      <div class="donut-pct" :class="pctClass">{{ pctText }}</div>
      <div class="donut-label">已用</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { PieChart } from 'echarts/charts'
import { TooltipComponent } from 'echarts/components'
import { init, use, type EChartsType } from 'echarts/core'
import { SVGRenderer } from 'echarts/renderers'
import { useToast } from '@/composables/useToast'
import { useThemeMode } from '@/composables/useThemeMode'

use([PieChart, TooltipComponent, SVGRenderer])

interface ModelUsage {
  name: string
  tokens: number
  cost: number
}

const props = withDefaults(defineProps<{
  used: number
  budget: number
  models?: ModelUsage[]
  size?: number
}>(), {
  models: () => [],
  size: 120,
})

const emit = defineEmits<{
  (e: 'budget-critical'): void
}>()

const chartEl = ref<HTMLElement | null>(null)
let chart: EChartsType | null = null
const toast = useToast()
const { resolvedTheme } = useThemeMode()
const warnedAt80 = ref(false)
const critical = ref(false)

const ratio = computed(() => props.budget > 0 ? props.used / props.budget : 0)
const pctText = computed(() => `${Math.round(ratio.value * 100)}%`)
const pctClass = computed(() => {
  if (ratio.value >= 0.95) return 'critical'
  if (ratio.value >= 0.80) return 'warning'
  return 'normal'
})

function readThemeColor(name: string, fallback: string) {
  if (typeof window === 'undefined') {
    return fallback
  }

  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback
}

const donutColor = computed(() => {
  if (ratio.value >= 0.95) return readThemeColor('--color-danger', '#ef6b64')
  if (ratio.value >= 0.80) return readThemeColor('--color-warning', '#e8a23a')
  return readThemeColor('--color-accent', '#127ea8')
})

function buildOption() {
  const trackColor = readThemeColor('--color-status-track', '#d4dee8')
  const models = props.models.length > 0
    ? props.models
    : [{ name: '已使用', tokens: props.used, cost: 0 }]
  return {
    tooltip: {
      trigger: 'item',
      formatter: (p: { name: string; value: number }) =>
        `${p.name}: ${p.value.toLocaleString()} tokens`,
    },
    series: [{
      type: 'pie',
      radius: ['48%', '70%'],
      data: [
        ...models.map(m => ({ name: m.name, value: m.tokens })),
        {
          name: '剩余',
          value: Math.max(0, props.budget - props.used),
          itemStyle: { color: trackColor },
          tooltip: { show: false },
        },
      ],
      label: { show: false },
      itemStyle: {
        color: donutColor.value,
        borderRadius: 3,
      },
    }],
  }
}

onMounted(() => {
  if (!chartEl.value) return
  chart = init(chartEl.value, undefined, { renderer: 'svg' })
  chart.setOption(buildOption())
})

onBeforeUnmount(() => {
  chart?.dispose()
})

watch([() => props.used, () => props.budget, () => props.models], () => {
  chart?.setOption(buildOption(), { replaceMerge: ['series'] })

  if (ratio.value >= 0.80 && !warnedAt80.value) {
    warnedAt80.value = true
    toast.add({ type: 'warning', message: 'Token 消耗已达预算 80%' })
  }
  if (ratio.value >= 0.95 && !critical.value) {
    critical.value = true
    emit('budget-critical')
  }
})

watch(resolvedTheme, () => {
  chart?.setOption(buildOption(), { replaceMerge: ['series'] })
})
</script>

<style scoped>
.cost-donut {
  position: relative;
  flex-shrink: 0;
}
.chart-inner {
  width: 100%;
  height: 100%;
}
.donut-center {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  pointer-events: none;
}
.donut-pct {
  font-size: 13px;
  font-weight: 700;
}
.donut-pct.normal { color: var(--color-ai-active); }
.donut-pct.warning { color: var(--color-warning); }
.donut-pct.critical { color: var(--color-error); animation: flash 0.5s ease-in-out infinite alternate; }
.donut-label {
  font-size: 10px;
  color: var(--color-text-secondary);
}
@keyframes flash {
  from { opacity: 1; }
  to   { opacity: 0.4; }
}
</style>
