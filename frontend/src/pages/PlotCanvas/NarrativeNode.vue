<template>
  <div class="narrative-node" :style="nodeStyle">
    <div class="node-header">
      <span class="node-id">{{ data.label }}</span>
      <span class="status-dot" :style="dotStyle"></span>
    </div>
    <div class="node-tension">张力 {{ data.tension ?? 0 }}/10</div>
    <Handle type="target" :position="Position.Left" />
    <Handle type="source" :position="Position.Right" />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{
  data: Record<string, unknown>
}>()

const nodeStyle = computed(() => ({
  borderColor: (props.data.borderColor as string) ?? '#2d2f3a',
}))
const dotStyle = computed(() => ({
  background: (props.data.borderColor as string) ?? '#2d2f3a',
}))
</script>

<style scoped>
.narrative-node {
  background: var(--color-surface-l1);
  border: 2px solid #2d2f3a;
  border-radius: var(--radius-card);
  padding: 10px 14px;
  width: 220px;
  font-size: 13px;
}
.node-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.node-id {
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 160px;
}
.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.node-tension {
  color: var(--color-text-secondary);
  font-size: 12px;
}
</style>
