<template>
  <span class="n-tag" :style="color ? { '--tag-color': color } : {}">{{ label }}</span>
</template>

<script setup lang="ts">
defineProps<{
  label: string
  color?: string
}>()
</script>

<style scoped>
.n-tag {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: var(--text-caption);
  background: color-mix(in srgb, var(--tag-color, var(--color-ai-active)) 15%, transparent);
  color: var(--tag-color, var(--color-ai-active));
  border: 1px solid color-mix(in srgb, var(--tag-color, var(--color-ai-active)) 40%, transparent);
  white-space: nowrap;
}
</style>
