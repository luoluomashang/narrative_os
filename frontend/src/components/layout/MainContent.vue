<template>
  <main class="main-content" ref="mainRef">
    <ShellPageHeader />
    <ShellBannerStack :banners="allBanners" />

    <RouterView v-slot="{ Component }">
      <Transition name="fade" mode="out-in">
        <KeepAlive :include="keepAliveIncludes">
          <component :is="Component" :key="$route.path" />
        </KeepAlive>
      </Transition>
    </RouterView>

    <div v-if="hitlActive" class="hitl-overlay">
      <slot name="hitl" />
    </div>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/projectStore'
import { useShellBanners } from '@/composables/useShellBanners'
import ShellBannerStack from './ShellBannerStack.vue'
import ShellPageHeader from './ShellPageHeader.vue'

const props = defineProps<{
  backendOnline?: boolean | null
  hitlActive?: boolean
}>()

const mainRef = ref<HTMLElement | null>(null)
const route = useRoute()
const projectStore = useProjectStore()
const { shellBanners } = useShellBanners()

const allBanners = computed(() => {
  const banners = [...shellBanners.value]

  if (props.backendOnline === false) {
    banners.unshift({
      id: 'backend-offline',
      tone: 'danger',
      title: '后端连接不可用',
      message: '当前系统处于离线状态。你仍可浏览页面，但生成、评测和会话流程可能无法执行。',
      action: { label: '前往项目列表', to: '/projects' },
    })
  }

  if (projectStore.error && route.path.startsWith('/project/')) {
    banners.push({
      id: 'project-context-error',
      tone: 'warning',
      title: '项目上下文加载异常',
      message: projectStore.error,
      action: { label: '返回项目列表', to: '/projects' },
    })
  }

  return banners
})

watch(() => route.path, () => {
  mainRef.value?.scrollTo({ top: 0, behavior: 'instant' })
})

const keepAliveIncludes = ['PlotCanvas', 'CharacterMatrix', 'MemorySystem']
</script>

<style scoped>
.main-content {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-lg);
  position: relative;
  background: var(--color-bg-canvas);
}

.hitl-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease;
}

.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

