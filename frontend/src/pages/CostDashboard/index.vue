<template>
  <div class="cd-page">
    <header class="cd-header">
      <span class="cd-title">消耗统计仪表盘</span>
      <NButton variant="ghost" @click="loadAll">刷新</NButton>
    </header>

    <!-- 三张统计卡片 -->
    <div v-if="summary" class="stat-cards">
      <div class="stat-card">
        <div class="stat-val">{{ summary.today_tokens.toLocaleString() }}</div>
        <div class="stat-label">今日 Tokens</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">{{ summary.total_tokens.toLocaleString() }}</div>
        <div class="stat-label">累计 Tokens</div>
      </div>
      <div class="stat-card">
        <div class="stat-val">${{ summary.today_cost_usd.toFixed(4) }}</div>
        <div class="stat-label">今日费用 (USD)</div>
      </div>
    </div>
    <div v-else-if="loading" class="cd-loading">加载中…</div>

    <!-- 按 Agent 分组 -->
    <section v-if="summary && agentEntries.length > 0" class="cd-section">
      <div class="cd-card">
        <div class="cd-card-title">按 Agent 分组</div>
        <div class="bar-list">
          <div v-for="[agent, tokens] in agentEntries" :key="agent" class="bar-row">
            <span class="bar-label">{{ agent }}</span>
            <div class="bar-track">
              <div class="bar-fill" :style="{ width: barPct(tokens, maxAgentVal) + '%' }" />
            </div>
            <span class="bar-val">{{ tokens.toLocaleString() }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 按 Skill 分组 -->
    <section v-if="summary && skillEntries.length > 0" class="cd-section">
      <div class="cd-card">
        <div class="cd-card-title">按 Skill 分组</div>
        <table class="cd-table">
          <thead>
            <tr>
              <th @click="sortCol = 'name'; sortAsc = !sortAsc">Skill ⇅</th>
              <th @click="sortCol = 'tokens'; sortAsc = !sortAsc">Tokens ⇅</th>
              <th>占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="[skill, tokens] in sortedSkillEntries" :key="skill">
              <td>{{ skill }}</td>
              <td>{{ tokens.toLocaleString() }}</td>
              <td>{{ pct(tokens, summary!.total_tokens) }}%</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- 历史折线（简单文字展示，ECharts 可在阶段五引入） -->
    <section v-if="history.length > 0" class="cd-section">
      <div class="cd-card">
        <div class="cd-card-title">历史记录（最近 {{ history.length }} 天）</div>
        <div class="history-list">
          <div v-for="item in history" :key="item.date" class="history-row">
            <span class="history-date">{{ item.date }}</span>
            <span class="history-tokens">{{ item.tokens.toLocaleString() }} tokens</span>
            <span class="history-cost">${{ item.cost_usd.toFixed(4) }}</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import NButton from '@/components/common/NButton.vue'
import { useProjectStore } from '@/stores/projectStore'
import { cost } from '@/api'
import type { CostSummaryResponse, CostHistoryItem } from '@/types/api'

const projectStore = useProjectStore()
const filterProjectId = computed(() => projectStore.projectId || undefined)

const summary = ref<CostSummaryResponse | null>(null)
const history = ref<CostHistoryItem[]>([])
const loading = ref(false)
const sortCol = ref<'name' | 'tokens'>('tokens')
const sortAsc = ref(false)

const agentEntries = computed(() =>
  Object.entries(summary.value?.by_agent ?? {}).sort((a, b) => b[1] - a[1])
)

const skillEntries = computed(() =>
  Object.entries(summary.value?.by_skill ?? {})
)

const sortedSkillEntries = computed(() => {
  const list = [...skillEntries.value]
  list.sort((a, b) => {
    if (sortCol.value === 'name') return sortAsc.value ? a[0].localeCompare(b[0]) : b[0].localeCompare(a[0])
    return sortAsc.value ? a[1] - b[1] : b[1] - a[1]
  })
  return list
})

const maxAgentVal = computed(() =>
  agentEntries.value.reduce((m, [, v]) => Math.max(m, v), 1)
)

function barPct(val: number, max: number): number {
  return max > 0 ? Math.round((val / max) * 100) : 0
}

function pct(val: number, total: number): string {
  return total > 0 ? ((val / total) * 100).toFixed(1) : '0.0'
}

async function loadAll() {
  loading.value = true
  try {
    const [s, h] = await Promise.all([
      cost.summary(filterProjectId.value),
      cost.history(30),
    ])
    summary.value = s.data
    history.value = h.data
  } catch {
    summary.value = null
  } finally {
    loading.value = false
  }
}

onMounted(loadAll)
</script>

<style scoped>
.cd-page {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 900px;
  margin: 0 auto;
}
.cd-header { display: flex; align-items: center; justify-content: space-between; }
.cd-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.cd-loading { color: var(--color-text-secondary); font-size: 14px; }
.stat-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.stat-card {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
}
.stat-val { font-size: 28px; font-weight: 700; color: var(--color-accent); }
.stat-label { font-size: 13px; color: var(--color-text-secondary); margin-top: 4px; }
.cd-section {}
.cd-card { background: var(--color-surface-l1); border: 1px solid var(--color-surface-l2); border-radius: 8px; padding: 20px; }
.cd-card-title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 14px; }
.bar-list { display: flex; flex-direction: column; gap: 8px; }
.bar-row { display: flex; align-items: center; gap: 10px; font-size: 13px; }
.bar-label { min-width: 120px; color: var(--color-text-secondary); text-overflow: ellipsis; overflow: hidden; white-space: nowrap; }
.bar-track { flex: 1; height: 8px; background: var(--color-surface-l2); border-radius: 4px; overflow: hidden; }
.bar-fill { height: 100%; background: var(--color-accent); border-radius: 4px; transition: width 300ms ease; }
.bar-val { min-width: 70px; text-align: right; color: var(--color-text-primary); }
.cd-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.cd-table th {
  text-align: left;
  padding: 6px 10px;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-surface-l2);
  cursor: pointer;
  user-select: none;
}
.cd-table th:hover { color: var(--color-text-primary); }
.cd-table td {
  padding: 8px 10px;
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-surface-l2);
}
.cd-table tr:last-child td { border-bottom: none; }
.history-list { display: flex; flex-direction: column; gap: 6px; }
.history-row {
  display: flex;
  gap: 16px;
  font-size: 13px;
  padding: 6px 0;
  border-bottom: 1px solid var(--color-surface-l2);
}
.history-row:last-child { border-bottom: none; }
.history-date { color: var(--color-text-secondary); min-width: 100px; }
.history-tokens { color: var(--color-text-primary); flex: 1; }
.history-cost { color: var(--color-accent); }
</style>
