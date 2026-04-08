<template>
  <div class="n-card" :class="{ 'n-card--hoverable': hoverable }" :style="{ padding: paddingVal }">
    <slot />
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  padding?: string | number
  hoverable?: boolean
}>()

const paddingVal = computed(() =>
  props.padding == null
    ? 'var(--spacing-md)'
    : typeof props.padding === 'number'
      ? `${props.padding}px`
      : props.padding
)
</script>

<style scoped>
.n-card {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-surface-l2);
}
.n-card--hoverable {
  cursor: pointer;
  transition: background 150ms;
}
.n-card--hoverable:hover {
  background: var(--color-surface-l2);
}
</style>
