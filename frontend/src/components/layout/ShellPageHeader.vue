<template>
  <section v-if="showHeader" class="shell-page-header">
    <div class="shell-page-header__top">
      <div class="shell-page-header__trail">
        <span class="shell-page-header__workspace">{{ eyebrow }}</span>
        <span class="shell-page-header__divider">/</span>
        <span class="shell-page-header__page">{{ pageTitle }}</span>
      </div>
      <span v-if="projectLabel" class="shell-page-header__project-chip">{{ projectLabel }}</span>
    </div>

    <nav class="shell-page-header__nav" aria-label="页面二级导航">
      <SystemButton
        v-for="item in secondaryItems"
        :key="item.id"
        :variant="route.path === item.to ? 'secondary' : 'ghost'"
        size="sm"
        @click="router.push(item.to)"
      >
        {{ item.label }}
      </SystemButton>
    </nav>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SystemButton from '@/components/system/SystemButton.vue'
import { useProjectStore } from '@/stores/projectStore'
import {
  getProjectPageDescriptor,
  getProjectWorkspace,
  getSecondaryNavigation,
} from '@/config/shellNavigation'

const route = useRoute()
const router = useRouter()
const projectStore = useProjectStore()

const routeTitle = computed(() => (route.meta?.title as string | undefined) ?? '工作台')
const descriptor = computed(() => getProjectPageDescriptor(route.path, routeTitle.value))
const workspace = computed(() => getProjectWorkspace(descriptor.value.workspaceId))

const eyebrow = computed(() => workspace.value?.label ?? '全局')
const pageTitle = computed(() => descriptor.value.title)
const projectLabel = computed(() => projectStore.currentProject?.title ?? projectStore.projectId)
const secondaryItems = computed(() => {
  if (!projectStore.projectId || !descriptor.value.workspaceId) return []
  return getSecondaryNavigation(projectStore.projectId, descriptor.value.workspaceId)
})
const showHeader = computed(() => secondaryItems.value.length > 1)
</script>

<style scoped>
.shell-page-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: grid;
  gap: var(--spacing-2);
  padding: var(--spacing-3) var(--spacing-6);
  margin: calc(var(--spacing-6) * -1) calc(var(--spacing-6) * -1) var(--spacing-4);
  border-bottom: 1px solid var(--color-border-subtle);
  backdrop-filter: blur(14px);
  background: color-mix(in srgb, var(--color-bg-canvas) 86%, transparent);
}

.shell-page-header__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
  flex-wrap: wrap;
}

.shell-page-header__trail {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--color-text-3);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.shell-page-header__page,
.shell-page-header__workspace {
  white-space: nowrap;
}

.shell-page-header__page {
  color: var(--color-text-2);
}

.shell-page-header__project-chip {
  display: flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 12px;
}

.shell-page-header__nav {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .shell-page-header {
    padding: var(--spacing-3) var(--spacing-4);
    margin: calc(var(--spacing-4) * -1) calc(var(--spacing-4) * -1) var(--spacing-3);
  }
}
</style>
