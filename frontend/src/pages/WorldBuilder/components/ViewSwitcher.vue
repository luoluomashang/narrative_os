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
  background: var(--wb-panel-solid-strong);
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
  color: var(--wb-text-soft);
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
  background: color-mix(in srgb, var(--wb-neon-cyan) 10%, transparent);
  box-shadow: var(--wb-button-glow);
}

.vs-icon { font-size: 14px; }
.vs-label { font-size: 11px; letter-spacing: 0.5px; }
</style>
