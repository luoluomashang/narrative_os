<template>
  <header class="top-bar">
    <!-- 左侧：Logo + 项目选择器 -->
    <span class="logo" @click="router.push('/projects')" style="cursor:pointer">Narrative OS</span>

    <el-select
      v-model="selectedProjectId"
      placeholder="选择项目"
      size="small"
      style="width:180px; flex-shrink:0"
      :loading="store.loading"
      clearable
      @change="onProjectChange"
    >
      <el-option
        v-for="p in store.projectList"
        :key="p.project_id"
        :label="p.title || p.project_id"
        :value="p.project_id"
      />
    </el-select>

    <!-- 中部：面包屑 -->
    <el-breadcrumb separator="/" class="top-bar-breadcrumb">
      <el-breadcrumb-item :to="{ path: '/projects' }">项目</el-breadcrumb-item>
      <el-breadcrumb-item v-if="store.projectId" :to="{ path: `/project/${store.projectId}` }">
        {{ store.currentProject?.title || store.projectId }}
      </el-breadcrumb-item>
      <el-breadcrumb-item v-if="currentPageTitle">{{ currentPageTitle }}</el-breadcrumb-item>
    </el-breadcrumb>

    <!-- 右侧：状态 + Token + 设置 -->
    <div class="top-bar-right">
      <el-tooltip :content="backendOnline ? '后端在线' : '后端离线'" placement="bottom">
        <span
          class="status-light"
          :class="backendOnline ? 'status-light--online' : 'status-light--offline'"
        />
      </el-tooltip>

      <el-tooltip v-if="cost" :content="`Token 使用率 ${Math.round(cost.usage_ratio * 100)}%`" placement="bottom">
        <div class="token-ring">
          <svg width="24" height="24" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="9" fill="none" stroke="var(--color-surface-l2)" stroke-width="3" />
            <circle
              cx="12" cy="12" r="9"
              fill="none"
              stroke="var(--color-ai-active)"
              stroke-width="3"
              stroke-dasharray="56.55"
              :stroke-dashoffset="56.55 * (1 - cost.usage_ratio)"
              stroke-linecap="round"
              transform="rotate(-90 12 12)"
            />
          </svg>
        </div>
      </el-tooltip>

      <el-tooltip content="全局设置" placement="bottom">
        <el-button text circle @click="router.push('/settings')">
          <el-icon><Setting /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </header>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import client from '@/api/client'
import { useProjectStore } from '@/stores/projectStore'
import type { CostResponse } from '@/types/api'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const backendOnline = ref(false)
const cost = ref<CostResponse | null>(null)
const selectedProjectId = ref<string | null>(store.projectId)

// 与 store 保持同步
watch(() => store.projectId, (id) => {
  selectedProjectId.value = id
})

const currentPageTitle = computed(() => {
  const title = route.meta?.title as string | undefined
  const projectTitle = store.currentProject?.title || store.projectId
  if (title && title !== '项目主页' && title !== projectTitle) return title
  return null
})

function onProjectChange(id: string | null) {
  if (id) {
    store.selectProject(id).catch(() => {
      ElMessage.error('切换项目失败')
    })
    router.push(`/project/${id}`)
  } else {
    store.projectId = null
    router.push('/projects')
  }
}

async function checkHealth() {
  try {
    await client.get('/health')
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  }
}

async function fetchCost() {
  try {
    const res = await client.get<CostResponse>('/cost/summary')
    cost.value = res.data
  } catch {
    cost.value = null
  }
}

// 初始加载项目列表（如果 store 为空）
onMounted(async () => {
  if (store.projectList.length === 0) {
    store.loadProjects().catch(() => {
      ElMessage.error('加载项目列表失败')
    })
  }
  checkHealth()
  fetchCost()
  healthTimer = setInterval(checkHealth, 15_000)
  costTimer = setInterval(fetchCost, 30_000)
})

let healthTimer: ReturnType<typeof setInterval>
let costTimer: ReturnType<typeof setInterval>

onUnmounted(() => {
  clearInterval(healthTimer)
  clearInterval(costTimer)
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  height: 48px;
  background: var(--color-surface-l1);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}

.logo {
  font-weight: 700;
  font-size: 16px;
  color: var(--color-ai-active);
  white-space: nowrap;
  user-select: none;
}

.top-bar-breadcrumb {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.top-bar-right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-light {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.status-light--online { background: var(--color-success, #4ade80); }
.status-light--offline { background: var(--color-error, #ef4444); }

.token-ring {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>

