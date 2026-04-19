<template>
  <div class="chapter-manager-page">
    <SystemPageHeader
      eyebrow="Chapter Manager"
      title="章节管理"
      description="查看已生成章节、导出全集，并快速跳回写作工作台进行续写或改写。"
    >
      <template #meta>
        <span class="chapter-manager-page__pill">项目 {{ projectId }}</span>
      </template>
    </SystemPageHeader>

    <SystemSection>
      <template #actions>
        <SystemButton :loading="exporting" @click="exportNovel('txt')">
          <el-icon><Download /></el-icon>
          <span>导出 TXT</span>
        </SystemButton>
        <SystemButton :loading="exporting" @click="exportNovel('md')">
          <el-icon><Download /></el-icon>
          <span>导出 MD</span>
        </SystemButton>
        <SystemButton variant="primary" @click="goWrite">
          <el-icon><EditPen /></el-icon>
          <span>撰写新章节</span>
        </SystemButton>
      </template>

      <SystemErrorState
        v-if="loadError && !loading"
        :message="loadError"
        action-label="重新加载"
        @action="load"
      />

      <div v-if="loading" class="cm-loading">
        <SystemSkeleton v-for="index in 3" :key="index" card show-header :rows="4" />
      </div>

      <SystemEmpty
        v-else-if="chapters.length === 0"
        title="还没有已生成章节"
        description="完成一次章节生成后，这里会显示章节摘要、质量分和导出入口。"
      >
        <template #action>
          <SystemButton variant="primary" @click="goWrite">去写第一章</SystemButton>
        </template>
      </SystemEmpty>

      <div v-else class="chapter-list">
        <SystemCard
          v-for="ch in chapters"
          :key="ch.chapter"
          class="chapter-card"
          interactive
          @click="openChapter(ch)"
        >
          <div class="ch-row">
            <div class="ch-num">第 {{ ch.chapter }} 章</div>
            <div class="ch-meta">
              <el-tag v-if="ch.has_text" size="small" type="success">有正文</el-tag>
              <el-tag v-else size="small" type="warning">仅元数据</el-tag>
              <span class="ch-words">{{ ch.word_count }} 字</span>
            </div>
            <div class="ch-scores">
              <span class="score-badge">质量 {{ ch.quality_score.toFixed(1) }}</span>
              <span class="score-badge">钩子 {{ ch.hook_score.toFixed(1) }}</span>
            </div>
            <SystemButton size="sm" variant="ghost" @click.stop="openChapter(ch)">查看</SystemButton>
            <SystemButton size="sm" variant="ghost" @click.stop="goWriteChapter(ch.chapter)">改写</SystemButton>
          </div>
          <div v-if="ch.summary" class="ch-summary">{{ ch.summary }}</div>
        </SystemCard>
      </div>
    </SystemSection>

    <el-dialog
      v-model="showTextDialog"
      :title="`第 ${selectedChapter?.chapter ?? '?'} 章`"
      width="720px"
      draggable
    >
      <div v-if="textLoading" style="padding: 24px; text-align: center">
        <SystemSkeleton card :rows="8" />
      </div>
      <div v-else>
        <div class="chapter-text-meta">
          <el-tag size="small" type="info">{{ selectedChapter?.word_count }} 字</el-tag>
          <el-tag size="small">质量 {{ selectedChapter?.quality_score?.toFixed(1) }}</el-tag>
          <el-tag size="small">钩子 {{ selectedChapter?.hook_score?.toFixed(1) }}</el-tag>
          <span v-if="selectedChapter?.timestamp" class="ch-time">{{ formatDate(selectedChapter.timestamp) }}</span>
        </div>
        <pre class="chapter-text">{{ chapterText }}</pre>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElIcon, ElMessage } from 'element-plus'
import { Download, EditPen } from '@element-plus/icons-vue'
import { projects } from '@/api'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import type { ChapterListItem } from '@/types/api'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.id as string)

const loading = ref(false)
const loadError = ref('')
const chapters = ref<ChapterListItem[]>([])

const showTextDialog = ref(false)
const textLoading = ref(false)
const chapterText = ref('')
const selectedChapter = ref<ChapterListItem | null>(null)
const exporting = ref(false)

async function load() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await projects.chapterList(projectId.value)
    chapters.value = res.data
  } catch {
    chapters.value = []
    loadError.value = '加载章节列表失败，请检查项目状态后重试。'
    ElMessage.error('加载章节列表失败')
  } finally {
    loading.value = false
  }
}

async function openChapter(ch: ChapterListItem) {
  selectedChapter.value = ch
  showTextDialog.value = true
  if (!ch.has_text) {
    chapterText.value = '（该章节尚无正文）'
    return
  }
  textLoading.value = true
  try {
    const res = await projects.chapterText(projectId.value, ch.chapter)
    chapterText.value = res.data.text
    selectedChapter.value = { ...ch, word_count: res.data.word_count, summary: res.data.summary }
  } catch {
    chapterText.value = '加载失败'
    ElMessage.error('加载章节正文失败')
  } finally {
    textLoading.value = false
  }
}

function goWrite() {
  router.push(`/project/${projectId.value}/write`)
}

function goWriteChapter(n: number) {
  router.push(`/project/${projectId.value}/write?chapter=${n}`)
}

async function exportNovel(format: 'txt' | 'md') {
  if (exporting.value) return
  exporting.value = true
  try {
    const res = await projects.exportNovel(projectId.value, format)
    const content = res.data.content as string
    const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${res.data.title || projectId.value}.${format}`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出 ${res.data.chapter_count} 章，共 ${res.data.total_words} 字`)
  } catch {
    ElMessage.error('导出失败，请确认项目有已生成章节')
  } finally {
    exporting.value = false
  }
}

function formatDate(iso: string): string {
  try { return new Date(iso).toLocaleDateString('zh-CN') } catch { return iso }
}

onMounted(load)
</script>

<style scoped>
.chapter-manager-page {
  padding: 24px;
  display: grid;
  gap: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.chapter-manager-page__pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.cm-loading {
  display: grid;
  gap: 12px;
}

.chapter-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.chapter-card {
  cursor: pointer;
}

.ch-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ch-num {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  min-width: 60px;
}

.ch-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
}

.ch-words {
  font-size: 13px;
  color: var(--el-text-color-secondary);
}

.ch-scores {
  display: flex;
  gap: 8px;
}

.score-badge {
  font-size: 12px;
  padding: 2px 8px;
  background: var(--el-fill-color-light);
  border-radius: 4px;
  color: var(--el-text-color-secondary);
}

.ch-summary {
  margin-top: 8px;
  font-size: 13px;
  color: var(--el-text-color-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chapter-text-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.ch-time {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.chapter-text {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-primary);
  font-family: inherit;
  max-height: 65vh;
  overflow-y: auto;
  margin: 0;
}

@media (max-width: 900px) {
  .chapter-manager-page {
    padding: 20px 16px;
  }

  .ch-row {
    align-items: flex-start;
    flex-wrap: wrap;
  }
}
</style>
