<template>
  <div class="memory-search-page">
    <SystemPageHeader
      eyebrow="Memory Search"
      title="记忆检索"
      description="按语义检索项目记忆，快速定位关键锚点与历史上下文。"
    >
      <template #meta>
        <span class="memory-search-page__pill">项目 {{ projectId }}</span>
      </template>
    </SystemPageHeader>

    <SystemSection dense>
      <SystemCard tone="subtle">
        <div class="search-row">
          <SystemFormField class="search-field" label="检索关键词" hint="支持 200 字以内语义查询。" for-id="memory-search-query">
            <el-input
              id="memory-search-query"
              v-model="query"
              maxlength="200"
              show-word-limit
              placeholder="输入检索关键词，例如：主角与导师冲突"
              @keyup.enter="runSearch"
            />
          </SystemFormField>
          <SystemButton variant="primary" :loading="searching" :disabled="!query.trim()" @click="runSearch">
            检索
          </SystemButton>
        </div>
        <div class="search-meta">
          <span>结果 {{ results.length }} 条</span>
          <span v-if="lastQuery">最近查询：{{ lastQuery }}</span>
        </div>
      </SystemCard>

      <SystemErrorState
        v-if="error"
        class="search-alert"
        :message="error"
        tone="warning"
        action-label="重试"
        @action="runSearch"
      />

      <section class="result-list">
        <div v-if="searching" class="result-loading">
          <SystemSkeleton v-for="index in 3" :key="index" card show-header :rows="3" />
        </div>
        <SystemEmpty
          v-else-if="!results.length"
          title="暂无检索结果"
          description="尝试换一个人物、事件或关系关键词，系统会按语义相似度重新匹配。"
        />
        <SystemCard
          v-for="item in results"
          v-else
          :key="item.record_id"
          class="result-card"
          interactive
          @click="openRecordDetail(item)"
        >
          <div class="result-top">
            <span class="result-id">{{ item.record_id }}</span>
            <span class="result-score">相似度 {{ formatScore(item.similarity) }}</span>
          </div>
          <p class="result-content">{{ item.content }}</p>
          <div class="result-meta">
            <span v-for="entry in formatMetadata(item.metadata)" :key="entry" class="meta-chip">{{ entry }}</span>
          </div>
          <div class="result-actions">
            <SystemButton size="sm" variant="secondary" @click.stop="openRecordDetail(item)">查看详情</SystemButton>
            <SystemButton
              v-if="getSourceLink(item)"
              size="sm"
              variant="ghost"
              @click.stop="openRecordSource(item)"
            >
              打开来源
            </SystemButton>
          </div>
        </SystemCard>
      </section>
    </SystemSection>

    <SystemDrawer
      v-model="detailDrawerOpen"
      title="记忆详情"
      description="详情与来源定位统一放进抽屉，避免检索列表同时承载浏览和编辑。"
      size="420px"
    >
      <div v-if="selectedRecord" class="memory-search-drawer">
        <SystemCard tone="subtle" title="记忆正文" :description="`来源：${describeMemorySource(selectedRecord)}`">
          <p class="memory-search-drawer__content">{{ selectedRecord.content }}</p>
        </SystemCard>

        <SystemCard title="来源定位" tone="subtle">
          <p class="memory-search-drawer__source-copy">
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
          <div class="memory-search-drawer__meta">
            <div v-for="entry in selectedRecordMetadata" :key="entry.label" class="memory-search-drawer__meta-row">
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
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { projects } from '@/api/projects'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemFormField from '@/components/system/SystemFormField.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import type { MemoryRecord } from '@/types/api'
import {
  buildMemoryMetadataItems,
  describeMemorySource,
  formatMemoryMetadata,
  resolveMemorySourceLink,
} from '@/utils/memoryRecords'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => (route.params.id as string) || 'default')

const query = ref('')
const lastQuery = ref('')
const searching = ref(false)
const error = ref('')
const results = ref<MemoryRecord[]>([])
const detailDrawerOpen = ref(false)
const selectedRecord = ref<MemoryRecord | null>(null)

const selectedRecordMetadata = computed(() => buildMemoryMetadataItems(selectedRecord.value, 16))
const selectedRecordSource = computed(() => (
  selectedRecord.value ? resolveMemorySourceLink(projectId.value, selectedRecord.value) : null
))

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

function formatScore(v?: number | null): string {
  if (typeof v !== 'number') return '0.00'
  return v.toFixed(2)
}

function formatMetadata(meta: Record<string, unknown>): string[] {
  return formatMemoryMetadata(meta, 4)
}

function getSourceLink(record: MemoryRecord) {
  return resolveMemorySourceLink(projectId.value, record)
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

watch(detailDrawerOpen, (open) => {
  if (!open) {
    selectedRecord.value = null
  }
})
</script>

<style scoped>
.memory-search-page {
  min-height: 100%;
  display: grid;
  gap: var(--spacing-5);
  align-content: start;
}

.memory-search-page__pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
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

.search-field {
  min-width: 0;
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

.result-loading {
  display: grid;
  gap: 10px;
}

.result-card {
  cursor: pointer;
}

.result-card :deep(.system-card__body) {
  display: grid;
  gap: 10px;
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

.result-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.meta-chip {
  font-size: 11px;
  color: var(--color-text-secondary);
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: 999px;
  padding: 2px 8px;
}

.memory-search-drawer {
  display: grid;
  gap: 14px;
}

.memory-search-drawer__content {
  margin: 0;
  color: var(--color-text-1);
  line-height: 1.7;
  white-space: pre-wrap;
  word-break: break-word;
}

.memory-search-drawer__meta {
  display: grid;
  gap: 10px;
}

.memory-search-drawer__meta-row {
  display: grid;
  gap: 4px;
}

.memory-search-drawer__meta-row span {
  color: var(--color-text-3);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.memory-search-drawer__meta-row strong,
.memory-search-drawer__source-copy {
  color: var(--color-text-1);
  line-height: 1.6;
}

.memory-search-drawer__source-copy {
  margin: 0;
}

@media (max-width: 720px) {
  .search-row {
    grid-template-columns: 1fr;
  }

  .search-meta {
    flex-direction: column;
    gap: 6px;
  }

  .result-actions {
    flex-direction: column;
  }
}
</style>
