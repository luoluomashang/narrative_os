<template>
  <main class="main-content" ref="mainRef">
    <RouterView v-slot="{ Component }">
      <Transition name="fade" mode="out-in">
        <KeepAlive :include="keepAliveIncludes">
          <component :is="Component" :key="$route.path" />
        </KeepAlive>
      </Transition>
    </RouterView>
    <!-- HITL 全局遮罩 -->
    <div v-if="hitlActive" class="hitl-overlay">
      <slot name="hitl" />
    </div>
  </main>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute } from 'vue-router'

defineProps<{
  hitlActive?: boolean
}>()

const mainRef = ref<HTMLElement | null>(null)
const route = useRoute()

// 切换路由时滚动到顶部
watch(() => route.path, () => {
  mainRef.value?.scrollTo({ top: 0, behavior: 'instant' })
})

// 缓存重型页面
const keepAliveIncludes = ['PlotCanvas', 'CharacterMatrix', 'MemorySystem']
</script>

<style scoped>
.main-content {
  flex: 1;
  overflow: auto;
  padding: var(--spacing-lg, 16px);
  position: relative;
}

.hitl-overlay {
  position: absolute;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 页面切换淡入淡出 */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 150ms ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>

