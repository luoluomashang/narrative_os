<template>
  <div
    class="faction-group-node"
    :style="{
      '--group-color': data.color || '#4d7cff',
      '--group-color-alpha': (data.color || '#4d7cff') + '18',
      '--group-color-border': (data.color || '#4d7cff') + '40',
    }"
  >
    <div class="group-header">
      <span class="group-icon">⚑</span>
      <span class="group-label">{{ data.label }}</span>
      <span class="group-count">{{ data.regionCount || 0 }} 地区</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  data: {
    label: string
    color?: string
    regionCount?: number
    scope?: string
  }
}>()
</script>

<style scoped>
.faction-group-node {
  width: 100%;
  height: 100%;
  min-width: 200px;
  min-height: 120px;
  background: var(--group-color-alpha);
  border: 2px dashed var(--group-color-border);
  border-radius: 16px;
  padding: 8px 0 0 0;
  pointer-events: none;
}

.group-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 12px 6px;
  border-bottom: 1px solid var(--group-color-border);
  pointer-events: auto;
  cursor: pointer;
}

.group-icon {
  font-size: 14px;
  color: var(--group-color);
}

.group-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--group-color);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.group-count {
  font-size: 10px;
  color: var(--group-color);
  opacity: 0.6;
  margin-left: auto;
  white-space: nowrap;
}
</style>
