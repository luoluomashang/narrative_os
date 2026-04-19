<template>
  <div class="trace-page">
    <SystemPageHeader
      eyebrow="Trace Inspector"
      title="执行链路检视器"
      description="查看项目内 Run 的五步 Agent 回放、评分、耗时与审批状态。"
    >
      <template #meta>
        <span class="trace-meta-pill">项目 {{ projectId }}</span>
      </template>
      <template #actions>
        <el-select v-model="selectedRunId" style="width: 260px" :disabled="loadingRuns" @change="loadRunTrace">
          <el-option
            v-for="run in runs"
            :key="run.run_id"
            :label="formatRunLabel(run)"
            :value="run.run_id"
          />
        </el-select>
        <SystemButton :loading="loadingTrace || loadingRuns" @click="refreshAll">刷新</SystemButton>
      </template>
    </SystemPageHeader>

    <el-alert
      v-if="error"
      type="warning"
      :closable="false"
      show-icon
      :title="error"
      class="trace-alert"
    />

    <SystemCard class="trace-panel" padding="none">
      <TraceInspector
        :data="traceData"
        @approve="submitApproval('approve')"
        @reject="submitApproval('reject')"
        @retry="submitApproval('retry')"
      />
    </SystemCard>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import TraceInspector from '@/components/TraceInspector.vue'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

interface RunListItem {
  run_id: string
  run_type: string
  status: string
  chapter_num?: number | null
  started_at: string
}

const runs = ref<RunListItem[]>([])
const selectedRunId = ref('')
const traceData = ref<Record<string, unknown> | null>(null)
const loadingRuns = ref(false)
const loadingTrace = ref(false)
const error = ref('')

async function loadRuns() {
  loadingRuns.value = true
  try {
    const res = await axios.get(`/api/projects/${projectId.value}/runs`)
    runs.value = res.data.items ?? []
    selectedRunId.value = runs.value[0]?.run_id ?? ''
  } catch {
    runs.value = []
    selectedRunId.value = ''
  } finally {
    loadingRuns.value = false
  }
}

async function loadRunTrace() {
  loadingTrace.value = true
  error.value = ''
  try {
    if (!selectedRunId.value) {
      traceData.value = null
      error.value = '当前项目暂无可回放的 Run。'
      return
    }
    const res = await axios.get(`/api/runs/${selectedRunId.value}/steps`)
    traceData.value = res.data
  } catch {
    traceData.value = null
    error.value = '无法加载执行链路，请稍后重试。'
  } finally {
    loadingTrace.value = false
  }
}

async function refreshAll() {
  await loadRuns()
  await loadRunTrace()
}

async function submitApproval(decision: 'approve' | 'reject' | 'retry') {
  if (!selectedRunId.value) return
  loadingTrace.value = true
  error.value = ''
  try {
    await axios.post(`/api/runs/${selectedRunId.value}/approve`, { decision })
    await refreshAll()
  } catch {
    error.value = '审批提交失败，请稍后重试。'
  } finally {
    loadingTrace.value = false
  }
}

function runTypeLabel(runType: string) {
  return {
    chapter_generation: '章节生成',
    benchmark_analysis: '对标分析',
    author_distillation: '作者蒸馏',
    worldbuilding: '世界构建',
  }[runType] ?? runType
}

function formatRunLabel(run: RunListItem) {
  const chapter = run.chapter_num ? `第 ${run.chapter_num} 章` : '非章节运行'
  const status = {
    running: '运行中',
    completed: '已完成',
    failed: '失败',
    paused: '已暂停',
  }[run.status] ?? run.status
  return `${chapter} · ${runTypeLabel(run.run_type)} · ${status}`
}

onMounted(async () => {
  await refreshAll()
})
</script>

<style scoped>
.trace-page {
  height: 100%;
  display: grid;
  gap: 12px;
}

.trace-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.trace-alert {
  margin-bottom: 2px;
}

.trace-panel {
  min-height: 0;
  flex: 1;
  overflow: hidden;
}
</style>
