<template>
  <div class="trace-page">
    <header class="trace-header">
      <div>
        <h2 class="trace-title">执行链路检视器</h2>
        <p class="trace-subtitle">查看章节级 Agent 执行节点与输入输出详情</p>
      </div>
      <div class="trace-actions">
        <el-select v-model="selectedChapter" style="width: 140px" :disabled="loadingChapter" @change="loadTrace">
          <el-option v-for="n in chapterOptions" :key="n" :label="`第 ${n} 章`" :value="n" />
        </el-select>
        <el-button :loading="loadingTrace" @click="loadTrace">刷新</el-button>
      </div>
    </header>

    <el-alert
      v-if="error"
      type="warning"
      :closable="false"
      show-icon
      :title="error"
      class="trace-alert"
    />

    <section class="trace-panel">
      <TraceInspector :data="traceData" />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import TraceInspector from '@/components/TraceInspector.vue'
import { projects } from '@/api/projects'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const chapterOptions = ref<number[]>([1])
const selectedChapter = ref(1)
const traceData = ref<Record<string, unknown> | null>(null)
const loadingChapter = ref(false)
const loadingTrace = ref(false)
const error = ref('')

async function loadChapterOptions() {
  loadingChapter.value = true
  try {
    const res = await projects.chapterList(projectId.value)
    const nums = (res.data ?? []).map(c => c.chapter).filter(n => Number.isFinite(n))
    chapterOptions.value = nums.length > 0 ? nums : [1]
    selectedChapter.value = chapterOptions.value[0]
  } catch {
    chapterOptions.value = [1]
    selectedChapter.value = 1
  } finally {
    loadingChapter.value = false
  }
}

async function loadTrace() {
  loadingTrace.value = true
  error.value = ''
  try {
    const res = await axios.get(`/api/traces/${selectedChapter.value}`)
    traceData.value = res.data
  } catch {
    traceData.value = null
    error.value = '无法加载执行链路，请稍后重试。'
  } finally {
    loadingTrace.value = false
  }
}

onMounted(async () => {
  await loadChapterOptions()
  await loadTrace()
})
</script>

<style scoped>
.trace-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.trace-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 2px 2px 0;
}

.trace-title {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text-primary);
}

.trace-subtitle {
  margin: 4px 0 0;
  color: var(--color-text-secondary);
  font-size: 13px;
}

.trace-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.trace-alert {
  margin-bottom: 2px;
}

.trace-panel {
  min-height: 0;
  flex: 1;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  overflow: hidden;
  background: var(--color-base);
}
</style>
