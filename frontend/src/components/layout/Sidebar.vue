<template>
  <transition name="sidebar-overlay-fade">
    <div v-if="isMobile && isOpen" class="sidebar-overlay" @click="emit('close')" />
  </transition>

  <aside class="sidebar" :class="sidebarClasses">
    <div class="sidebar__header">
      <div>
        <p class="sidebar__eyebrow">{{ store.projectId ? '一级工作区' : '全局入口' }}</p>
        <strong class="sidebar__title">{{ store.currentProject?.title || 'Narrative OS' }}</strong>
      </div>

      <el-button v-if="isMobile" text circle @click="emit('close')">×</el-button>
    </div>

    <nav class="sidebar__nav" aria-label="壳层导航">
      <button
        v-for="item in primaryItems"
        :key="item.id"
        class="sidebar__nav-item"
        :class="{ 'sidebar__nav-item--active': item.active, 'sidebar__nav-item--compact': !showLabels }"
        @click="navigate(item.to)"
      >
        <span class="sidebar__nav-icon">
          <el-icon>
            <component :is="item.icon" />
          </el-icon>
        </span>
        <span v-if="showLabels" class="sidebar__nav-copy">
          <strong>{{ item.label }}</strong>
          <small>{{ item.description }}</small>
        </span>
      </button>
    </nav>

    <div class="sidebar__footer">
      <button class="sidebar__utility" @click="navigate('/projects')">
        <el-icon><ArrowLeft /></el-icon>
        <span v-if="showLabels">全部项目</span>
      </button>

      <button v-if="store.projectId" class="sidebar__utility" @click="navigate(`/project/${store.projectId}/settings`)">
        <el-icon><Setting /></el-icon>
        <span v-if="showLabels">项目设置</span>
      </button>

      <button v-if="!isMobile" class="sidebar__utility" @click="toggleCollapse">
        <el-icon><component :is="isCollapsed ? Expand : Fold" /></el-icon>
        <span v-if="showLabels">{{ isCollapsed ? '展开导航' : '收起导航' }}</span>
      </button>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  ArrowLeft,
  Collection,
  DataAnalysis,
  EditPen,
  Expand,
  Fold,
  House,
  Setting,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/projectStore'
import {
  getGlobalPath,
  getProjectPageDescriptor,
  getProjectWorkspace,
  globalNavigation,
  projectWorkspaces,
} from '@/config/shellNavigation'

const props = defineProps<{
  isMobile: boolean
  isOpen: boolean
}>()

const emit = defineEmits<{
  (event: 'close'): void
}>()

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const _storedCollapsed = localStorage.getItem('sidebar_collapsed')
const isCollapsed = ref(_storedCollapsed === 'true')

const workspaceDescriptor = computed(() =>
  getProjectPageDescriptor(route.path, (route.meta?.title as string | undefined) ?? '工作台'),
)
const activeWorkspace = computed(() => getProjectWorkspace(workspaceDescriptor.value.workspaceId))

const workspaceIcons = {
  House,
  EditPen,
  Collection,
  DataAnalysis,
}

const primaryItems = computed(() => {
  if (!store.projectId) {
    return globalNavigation.map((item) => ({
      id: item.id,
      label: item.label,
      description: item.description,
      to: getGlobalPath(item),
      icon: item.id === 'projects' ? House : item.id === 'settings' ? Setting : item.id === 'plugins' ? Collection : DataAnalysis,
      active: route.path === getGlobalPath(item),
    }))
  }

  return projectWorkspaces.map((workspace) => ({
    id: workspace.id,
    label: workspace.label,
    description: workspace.description,
    to: workspace.items[0]?.segment ? `/project/${store.projectId}/${workspace.items[0].segment}` : `/project/${store.projectId}`,
    icon: workspaceIcons[workspace.icon],
    active: activeWorkspace.value?.id === workspace.id,
  }))
})

const showLabels = computed(() => props.isMobile || !isCollapsed.value)
const sidebarClasses = computed(() => ({
  'sidebar--collapsed': !props.isMobile && isCollapsed.value,
  'sidebar--mobile': props.isMobile,
  'sidebar--mobile-open': props.isMobile && props.isOpen,
  'sidebar--mobile-hidden': props.isMobile && !props.isOpen,
}))

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar_collapsed', String(isCollapsed.value))
}

function navigate(target: string) {
  router.push(target)
  if (props.isMobile) {
    emit('close')
  }
}
</script>

<style scoped>
.sidebar {
  position: relative;
  display: flex;
  flex-direction: column;
  width: 260px;
  min-width: 260px;
  height: 100%;
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  border-right: 1px solid var(--color-border-default);
  transition:
    width 150ms ease,
    min-width 150ms ease,
    transform 180ms ease;
  z-index: 40;
}

.sidebar--collapsed {
  width: 92px;
  min-width: 92px;
}

.sidebar__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-3);
  padding: var(--spacing-5) var(--spacing-4) var(--spacing-3);
}

.sidebar__eyebrow {
  margin: 0 0 6px;
  font-size: var(--text-caption);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.sidebar__title {
  color: var(--color-text-1);
}

.sidebar__nav {
  flex: 1;
  display: grid;
  gap: var(--spacing-2);
  padding: var(--spacing-2) var(--spacing-3) var(--spacing-4);
}

.sidebar__nav-item {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-3);
  width: 100%;
  padding: var(--spacing-4);
  border: 1px solid transparent;
  border-radius: var(--radius-lg);
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background 150ms ease,
    border-color 150ms ease,
    transform 150ms ease;
}

.sidebar__nav-item:hover {
  transform: translateY(-1px);
  background: var(--color-surface-2);
}

.sidebar__nav-item--active {
  border-color: color-mix(in srgb, var(--color-accent) 18%, transparent);
  background: var(--color-accent-soft);
}

.sidebar__nav-item--compact {
  justify-content: center;
  padding-inline: 0;
}

.sidebar__nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-surface-2) 88%, transparent);
  color: var(--color-text-1);
}

.sidebar__nav-copy {
  display: grid;
  gap: 6px;
}

.sidebar__nav-copy strong {
  color: var(--color-text-1);
}

.sidebar__nav-copy small {
  color: var(--color-text-2);
  line-height: 1.5;
}

.sidebar__footer {
  display: grid;
  gap: var(--spacing-2);
  padding: var(--spacing-3);
  border-top: 1px solid var(--color-border-subtle);
}

.sidebar__utility {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-2);
  width: 100%;
  background: transparent;
  border: none;
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  padding: 10px 12px;
  cursor: pointer;
  transition:
    color 150ms ease,
    background 150ms ease;
}

.sidebar__utility:hover {
  background: var(--color-surface-2);
  color: var(--color-text-primary);
}

.sidebar-overlay {
  position: fixed;
  inset: 0;
  z-index: 35;
  background: rgba(15, 23, 42, 0.24);
}

.sidebar--mobile {
  position: fixed;
  inset: 0 auto 0 0;
  max-width: min(82vw, 320px);
  width: min(82vw, 320px);
  min-width: min(82vw, 320px);
  box-shadow: var(--shadow-md);
}

.sidebar--mobile-hidden {
  transform: translateX(-100%);
}

.sidebar--mobile-open {
  transform: translateX(0);
}

@media (max-width: 960px) {
  .sidebar {
    height: calc(100vh - 16px);
    margin: 8px 0 8px 8px;
    border-radius: var(--radius-xl);
    border: 1px solid var(--color-border-subtle);
  }
}

.sidebar-overlay-fade-enter-active,
.sidebar-overlay-fade-leave-active {
  transition: opacity 180ms ease;
}

.sidebar-overlay-fade-enter-from,
.sidebar-overlay-fade-leave-to {
  opacity: 0;
}
</style>

