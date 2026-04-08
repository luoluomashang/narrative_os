<template>
  <div class="char-matrix">
    <!-- Error -->
    <div v-if="error" style="padding:16px">
      <NCard><p style="color:var(--color-error)">加载失败：{{ error }}</p><NButton variant="ghost" @click="load">重试</NButton></NCard>
    </div>
    <template v-else>
      <!-- Left: character list -->
      <aside class="char-list">
        <div
          v-for="c in characters"
          :key="c.name"
          class="char-item"
          :class="{ active: selected?.name === c.name }"
          :style="{ background: emotionBg(c.emotion) }"
          @click="select(c)"
        >
          <span class="char-name">{{ c.name }}</span>
          <NTag :label="c.emotion" :color="c.is_alive ? 'var(--color-ai-active)' : 'var(--color-error)'" />
        </div>
        <div v-if="loading" style="padding:12px; color:var(--color-text-secondary)">
          <NBreathingLight :size="8" /> 加载中…
        </div>
        <div v-if="!loading && characters.length === 0" style="padding:12px; color:var(--color-text-secondary)">
          暂无角色数据
        </div>
      </aside>

      <!-- Right: detail panel -->
      <div class="char-detail">
        <div v-if="selected">
          <div class="tabs">
            <button v-for="tab in tabs" :key="tab" class="tab-btn" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ tab }}</button>
          </div>

          <!-- 档案 -->
          <NCard v-if="activeTab === '档案'" style="margin-top:12px">
            <p><strong>目标：</strong>{{ detail?.goal ?? '—' }}</p>
            <p style="margin-top:8px"><strong>背景：</strong>{{ detail?.backstory ?? '—' }}</p>
            <p style="margin-top:8px"><strong>特质：</strong>{{ (detail?.traits ?? []).join('、') }}</p>
          </NCard>

          <!-- 状态 -->
          <NCard v-if="activeTab === '状态'" style="margin-top:12px">
            <div ref="radarEl" class="radar-chart"></div>
          </NCard>

          <!-- 限制 -->
          <NCard v-if="activeTab === '限制'" style="margin-top:12px">
            <div v-if="(detail?.behavior_constraints ?? []).length">
              <div v-for="(rule, i) in detail?.behavior_constraints" :key="i" class="rule-row">
                <span class="lock-icon">🔒</span>
                <span>{{ rule }}</span>
              </div>
            </div>
            <p v-else style="color:var(--color-text-secondary)">无行为限制规则</p>
          </NCard>

          <!-- 关系 -->
          <NCard v-if="activeTab === '关系'" style="margin-top:12px">
            <div ref="relGraphEl" class="rel-graph"></div>
          </NCard>
        </div>
        <div v-else style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-text-secondary)">
          从左侧选择角色
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, nextTick, computed } from 'vue'
import { useRoute } from 'vue-router'
import * as echarts from 'echarts'
import * as d3 from 'd3'
import NCard from '@/components/common/NCard.vue'
import NButton from '@/components/common/NButton.vue'
import NTag from '@/components/common/NTag.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import { projects } from '@/api/projects'
import type { CharacterSummary, CharacterDetail } from '@/types/api'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const loading = ref(false)
const error = ref<string | null>(null)
const characters = ref<CharacterSummary[]>([])
const selected = ref<CharacterSummary | null>(null)
const detail = ref<CharacterDetail | null>(null)
const activeTab = ref('档案')
const tabs = ['档案', '状态', '限制', '关系']
const radarEl = ref<HTMLElement | null>(null)
const relGraphEl = ref<HTMLElement | null>(null)
let radarChart: echarts.ECharts | null = null

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await projects.characters(projectId.value)
    characters.value = res.data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

async function select(c: CharacterSummary) {
  selected.value = c
  activeTab.value = '档案'
  try {
    const res = await projects.character(projectId.value, c.name)
    detail.value = res.data
  } catch {
    detail.value = null
  }
}

function renderRadar() {
  if (!radarEl.value || !detail.value) return
  if (!radarChart) radarChart = echarts.init(radarEl.value, 'dark')
  radarChart.setOption({
    backgroundColor: 'transparent',
    radar: {
      indicator: [
        { name: '心理韧性', max: 10 }, { name: '道德倾向', max: 10 },
        { name: '疲劳', max: 10 }, { name: '理智', max: 10 },
        { name: '意志力', max: 10 }, { name: '情绪稳定', max: 10 },
      ],
      axisName: { color: '#999' },
      splitArea: { areaStyle: { color: ['rgba(255,255,255,0.02)', 'rgba(255,255,255,0.05)'] } },
    },
    series: [{ type: 'radar', data: [{ value: [7, 6, 4, 8, 7, 6], name: detail.value.name }],
      areaStyle: { color: 'rgba(46,242,255,0.2)' },
      lineStyle: { color: '#2ef2ff' }, itemStyle: { color: '#2ef2ff' },
    }],
  })
}

function renderRelGraph() {
  if (!relGraphEl.value || !detail.value) return
  const el = relGraphEl.value
  const width = el.clientWidth || 260
  const height = 200
  d3.select(el).selectAll('*').remove()
  const svg = d3.select(el).append('svg').attr('width', width).attr('height', height)
  const rels = Object.entries(detail.value.relationships)
  if (rels.length === 0) {
    svg.append('text').attr('x', width / 2).attr('y', height / 2)
      .attr('text-anchor', 'middle').attr('fill', '#999').text('无关系数据')
    return
  }
  const cx = width / 2, cy = height / 2
  svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 20)
    .attr('fill', '#2ef2ff').attr('opacity', 0.8)
  svg.append('text').attr('x', cx).attr('y', cy + 4)
    .attr('text-anchor', 'middle').attr('fill', '#0a0a0b').attr('font-size', 11)
    .text(detail.value.name.slice(0, 4))
  rels.forEach(([name, rel], i) => {
    const angle = (i / rels.length) * 2 * Math.PI - Math.PI / 2
    const tx = cx + 90 * Math.cos(angle), ty = cy + 70 * Math.sin(angle)
    const color = relColor(rel)
    svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', tx).attr('y2', ty)
      .attr('stroke', color).attr('stroke-width', 1.5).attr('opacity', 0.7)
    svg.append('circle').attr('cx', tx).attr('cy', ty).attr('r', 16).attr('fill', '#1b1c22').attr('stroke', color).attr('stroke-width', 1)
    svg.append('text').attr('x', tx).attr('y', ty + 4).attr('text-anchor', 'middle').attr('fill', '#f2efe9').attr('font-size', 10).text(name.slice(0, 4))
  })
}

watch(activeTab, async (tab) => {
  await nextTick()
  if (tab === '状态') renderRadar()
  if (tab === '关系') renderRelGraph()
})

function relColor(rel: string): string {
  const r = rel.toLowerCase()
  if (r.includes('友') || r.includes('盟') || r.includes('ally') || r.includes('friend')) return '#2ef2ff'
  if (r.includes('敌') || r.includes('仇') || r.includes('enemy') || r.includes('rival')) return '#ff4040'
  if (r.includes('爱') || r.includes('恋') || r.includes('romantic') || r.includes('lover')) return '#ff2e88'
  return '#666'
}

function emotionBg(emotion: string): string {
  const e = (emotion ?? '').toLowerCase()
  if (e === 'happy' || e === '愉快' || e === '兴奋' || e === '开心') return 'rgba(63,190,138,0.10)'
  if (e === 'anxious' || e === '焦虑' || e === 'angry' || e === '愤怒' || e === '恐惧') return 'rgba(255,180,0,0.10)'
  return ''
}

onMounted(load)
</script>

<style scoped>
.char-matrix { display: flex; height: 100%; gap: 16px; }
.char-list { width: 200px; flex-shrink: 0; background: var(--color-surface-l1); border-radius: var(--radius-card); border: 1px solid var(--color-surface-l2); overflow-y: auto; }
.char-item { padding: 10px 12px; cursor: pointer; display: flex; justify-content: space-between; align-items: center; border-left: 2px solid transparent; transition: all 150ms; }
.char-item:hover, .char-item.active { background: var(--color-surface-l2); }
.char-item.active { border-left-color: var(--color-ai-active); }
.char-name { font-size: 14px; color: var(--color-text-primary); }
.char-detail { flex: 1; overflow-y: auto; }
.tabs { display: flex; gap: 4px; }
.tab-btn { background: transparent; border: 1px solid var(--color-surface-l2); color: var(--color-text-secondary); padding: 4px 12px; border-radius: var(--radius-btn); cursor: pointer; font-size: 13px; transition: all 150ms; }
.tab-btn.active { background: var(--color-surface-l2); color: var(--color-ai-active); border-color: var(--color-ai-active); }
.radar-chart { height: 220px; width: 100%; }
.rel-graph { min-height: 200px; width: 100%; }
.rule-row { display: flex; align-items: flex-start; gap: 8px; padding: 6px 0; border-bottom: 1px solid var(--color-surface-l2); font-size: 13px; }
.lock-icon { flex-shrink: 0; }
</style>
