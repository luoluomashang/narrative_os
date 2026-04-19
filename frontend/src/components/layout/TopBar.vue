<template>
  <header class="top-bar">
    <div class="top-bar__left">
      <el-button v-if="isMobile" text circle class="top-bar__menu-btn" @click="emit('open-navigation')">
        <el-icon><Operation /></el-icon>
      </el-button>

      <button class="logo" @click="router.push('/projects')">Narrative OS</button>

      <el-select
        v-model="selectedProjectId"
        placeholder="选择项目"
        size="small"
        class="top-bar__project-select"
        :loading="store.loading"
        clearable
        @change="onProjectChange"
      >
        <el-option
          v-for="project in store.projectList"
          :key="project.project_id"
          :label="project.title || project.project_id"
          :value="project.project_id"
        />
      </el-select>
    </div>

    <div class="top-bar__center">
      <p class="top-bar__workspace">{{ currentWorkspaceLabel }}</p>
      <div class="top-bar__context">
        <strong class="top-bar__project">{{ store.currentProject?.title || '平台导航' }}</strong>
        <span class="top-bar__context-divider">/</span>
        <span class="top-bar__page">{{ currentPageTitle }}</span>
      </div>
    </div>

    <div class="top-bar__right">
      <div class="top-bar__status-cluster">
        <span class="top-bar__status-pill" :class="statusToneClass">
          <span class="status-light" :class="statusLightClass" />
          {{ backendStatusText }}
        </span>
        <span v-if="cost" class="top-bar__status-pill">
          {{ tokenUsageLabel }}
        </span>
      </div>

      <el-button class="command-trigger" @click="commandPaletteOpen = true">
        <el-icon><Search /></el-icon>
        <span>命令面板</span>
        <kbd>{{ shortcutLabel }}</kbd>
      </el-button>

      <ThemeModeDropdown />

      <el-tooltip content="全局设置" placement="bottom">
        <el-button text circle @click="router.push('/settings')">
          <el-icon><Setting /></el-icon>
        </el-button>
      </el-tooltip>
    </div>
  </header>

  <ShellCommandPalette v-model="commandPaletteOpen" />
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Operation, Search, Setting } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/projectStore'
import { getProjectPageDescriptor, getProjectWorkspace } from '@/config/shellNavigation'
import type { CostResponse } from '@/types/api'
import ShellCommandPalette from './ShellCommandPalette.vue'
import ThemeModeDropdown from './ThemeModeDropdown.vue'

const props = defineProps<{
  backendOnline: boolean | null
  cost: CostResponse | null
  isMobile: boolean
}>()

const emit = defineEmits<{
  (event: 'open-navigation'): void
}>()

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const selectedProjectId = ref<string | null>(store.projectId)
const commandPaletteOpen = ref(false)
const shortcutLabel = ref('Ctrl K')

watch(() => store.projectId, (id) => {
  selectedProjectId.value = id
})

const currentDescriptor = computed(() =>
  getProjectPageDescriptor(route.path, (route.meta?.title as string | undefined) ?? '工作台'),
)

const currentWorkspaceLabel = computed(() => {
  const workspace = getProjectWorkspace(currentDescriptor.value.workspaceId)
  return workspace?.label ?? '全局'
})

const currentPageTitle = computed(() => currentDescriptor.value.title)

const backendStatusText = computed(() => {
  if (props.backendOnline === null) return '连接检查中'
  return props.backendOnline ? '后端在线' : '后端离线'
})

const statusLightClass = computed(() => {
  if (props.backendOnline === null) return 'status-light--pending'
  return props.backendOnline ? 'status-light--online' : 'status-light--offline'
})

const statusToneClass = computed(() => {
  if (props.backendOnline === null) return 'top-bar__status-pill--pending'
  return props.backendOnline ? 'top-bar__status-pill--healthy' : 'top-bar__status-pill--danger'
})

const tokenUsageLabel = computed(() => {
  const usageRatio = props.cost?.usage_ratio
  if (typeof usageRatio !== 'number' || !Number.isFinite(usageRatio)) {
    return 'Token --'
  }

  return `Token ${Math.round(usageRatio * 100)}%`
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

onMounted(async () => {
  if (store.projectList.length === 0) {
    store.loadProjects().catch(() => {
      ElMessage.error('加载项目列表失败')
    })
  }

  if (window.navigator.platform.toLowerCase().includes('mac')) {
    shortcutLabel.value = 'Cmd K'
  }
})
</script>

<style scoped>
.top-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-4);
  padding: 0 var(--spacing-5);
  min-height: 68px;
  background: color-mix(in srgb, var(--color-surface-1) 92%, transparent);
  border-bottom: 1px solid var(--color-border-default);
  box-shadow: var(--shadow-xs);
  flex-shrink: 0;
}

.top-bar__left,
.top-bar__right {
  display: flex;
  align-items: center;
  gap: var(--spacing-3);
}

.top-bar__left {
  flex-shrink: 0;
}

.top-bar__center {
  min-width: 0;
  flex: 1;
}

.top-bar__workspace {
  margin: 0 0 4px;
  font-size: var(--text-caption);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.top-bar__context {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  min-width: 0;
}

.top-bar__project,
.top-bar__page {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.top-bar__project {
  color: var(--color-text-1);
}

.top-bar__page,
.top-bar__context-divider {
  color: var(--color-text-2);
}

.logo {
  border: none;
  background: transparent;
  font-weight: 700;
  font-size: 16px;
  color: var(--color-accent);
  white-space: nowrap;
  user-select: none;
  cursor: pointer;
}

.top-bar__project-select {
  width: 200px;
  flex-shrink: 0;
}

.top-bar__right {
  margin-left: auto;
}

.top-bar__status-cluster {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
}

.top-bar__status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-2);
  font-size: var(--text-caption);
}

.top-bar__status-pill--healthy {
  color: var(--color-text-1);
}

.top-bar__status-pill--danger {
  color: var(--color-danger);
  border-color: color-mix(in srgb, var(--color-danger) 18%, transparent);
  background: color-mix(in srgb, var(--color-danger) 8%, var(--color-surface-2));
}

.status-light {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.status-light--online {
  background: var(--color-success);
}

.status-light--pending {
  background: var(--color-text-3);
}

.status-light--offline {
  background: var(--color-danger);
}

.command-trigger {
  display: flex;
  align-items: center;
  gap: 10px;
  border-radius: var(--radius-pill);
  padding-inline: 14px;
}

.command-trigger kbd {
  padding: 2px 6px;
  border-radius: 6px;
  border: 1px solid var(--color-border-subtle);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-caption);
  font-family: inherit;
}

.top-bar__menu-btn {
  margin-right: -4px;
}

@media (max-width: 960px) {
  .top-bar {
    gap: var(--spacing-3);
    padding: var(--spacing-3) var(--spacing-4);
    align-items: flex-start;
    flex-wrap: wrap;
  }

  .top-bar__left,
  .top-bar__right,
  .top-bar__center {
    width: 100%;
  }

  .top-bar__center {
    order: 3;
  }

  .top-bar__right {
    justify-content: space-between;
    flex-wrap: wrap;
  }

  .top-bar__status-cluster {
    order: 2;
    width: 100%;
  }

  .top-bar__project-select {
    flex: 1;
    width: auto;
  }

  .command-trigger {
    flex: 1;
    justify-content: space-between;
  }
}

@media (max-width: 680px) {
  .top-bar__status-cluster {
    flex-wrap: wrap;
  }

  .top-bar__right {
    gap: var(--spacing-2);
  }
}
</style>

