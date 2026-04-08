<template>
  <div class="view-switcher">
    <button
      v-for="v in views"
      :key="v.mode"
      class="vs-btn"
      :class="{ active: modelValue === v.mode }"
      :title="v.label"
      @click="$emit('update:modelValue', v.mode)"
    >
      <span class="vs-icon">{{ v.icon }}</span>
      <span class="vs-label">{{ v.label }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
import type { ViewMode } from '../composables/useViewMode'

defineProps<{ modelValue: ViewMode }>()
defineEmits<{ (e: 'update:modelValue', v: ViewMode): void }>()

const views = [
  { mode: 'graph' as ViewMode, label: '图谱', icon: '⬡' },
  { mode: 'map'   as ViewMode, label: '地图', icon: '🗺' },
  { mode: 'layer' as ViewMode, label: '分层', icon: '⏚' },
  { mode: 'space' as ViewMode, label: '星图', icon: '✦' },
]
</script>

<style scoped>
.view-switcher {
  display: flex;
  gap: 4px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid var(--wb-glass-border);
  border-radius: 8px;
  padding: 4px;
  backdrop-filter: blur(8px);
}

.vs-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: #888;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s ease;
}

.vs-btn:hover {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-glass-border);
}

.vs-btn.active {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-neon-cyan);
  background: rgba(46, 242, 255, 0.1);
  box-shadow: 0 0 8px rgba(46, 242, 255, 0.3);
}

.vs-icon { font-size: 14px; }
.vs-label { font-size: 11px; letter-spacing: 0.5px; }
</style>
