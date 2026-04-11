<template>
  <div class="memory-search-page">
    <header class="memory-search-header">
      <h2 class="memory-search-title">记忆检索</h2>
      <p class="memory-search-subtitle">按语义检索项目记忆，快速定位关键锚点</p>
    </header>

    <section class="search-card">
      <div class="search-row">
        <el-input
          v-model="query"
          maxlength="200"
          show-word-limit
          placeholder="输入检索关键词，例如：主角与导师冲突"
          @keyup.enter="runSearch"
        />
        <el-button type="primary" :loading="searching" :disabled="!query.trim()" @click="runSearch">
          检索
        </el-button>
      </div>
      <div class="search-meta">
        <span>结果 {{ results.length }} 条</span>
        <span v-if="lastQuery">最近查询：{{ lastQuery }}</span>
      </div>
    </section>

    <el-alert
      v-if="error"
      class="search-alert"
      type="warning"
      show-icon
      :closable="false"
      :title="error"
    />

    <section class="result-list">
      <el-empty v-if="!searching && !results.length" description="暂无检索结果" :image-size="64" />
      <el-card v-for="item in results" :key="item.record_id" class="result-card" shadow="hover">
        <div class="result-top">
          <span class="result-id">{{ item.record_id }}</span>
          <span class="result-score">相似度 {{ formatScore(item.similarity) }}</span>
        </div>
        <p class="result-content">{{ item.content }}</p>
        <div class="result-meta">
          <span v-for="entry in formatMetadata(item.metadata)" :key="entry" class="meta-chip">{{ entry }}</span>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { projects } from '@/api/projects'
import type { MemoryRecord } from '@/types/api'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const query = ref('')
const lastQuery = ref('')
const searching = ref(false)
const error = ref('')
const results = ref<MemoryRecord[]>([])

async function runSearch() {
  const q = query.value.trim().slice(0, 200)
  if (!q) return

  searching.value = true
  error.value = ''
  try {
    const res = await projects.memorySearch(projectId.value, q)
    results.value = res.data.results ?? []
    lastQuery.value = q
  } catch {
    results.value = []
    error.value = '检索失败，请检查服务状态后重试。'
  } finally {
    searching.value = false
  }
}

function formatScore(v?: number): string {
  if (typeof v !== 'number') return '0.00'
  return v.toFixed(2)
}

function formatMetadata(meta: Record<string, unknown>): string[] {
  return Object.entries(meta ?? {})
    .slice(0, 4)
    .map(([k, v]) => `${k}: ${String(v)}`)
}
</script>

<style scoped>
.memory-search-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.memory-search-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.memory-search-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.memory-search-subtitle {
  margin: 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.search-card {
  padding: 12px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  background: var(--color-surface-l1);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.search-row {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.search-meta {
  display: flex;
  gap: 16px;
  color: var(--color-text-secondary);
  font-size: 12px;
}

.search-alert {
  margin-bottom: 2px;
}

.result-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-right: 2px;
}

.result-card {
  border: 1px solid var(--color-surface-l2);
}

.result-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.result-id {
  font-size: 12px;
  color: var(--color-text-secondary);
}

.result-score {
  font-size: 12px;
  color: var(--color-ai-active);
  font-weight: 600;
}

.result-content {
  margin: 10px 0;
  color: var(--color-text-primary);
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.result-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.meta-chip {
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: 999px;
  padding: 2px 8px;
}
</style>
