<template>
  <span
    class="n-breathing-light breathing"
    :style="{
      width: `${size}px`,
      height: `${size}px`,
      background: color ?? 'var(--color-ai-active)',
    }"
  />
</template>

<script setup lang="ts">
defineProps<{
  size?: number
  color?: string
}>()
</script>

<style scoped>
.n-breathing-light {
  display: inline-block;
  border-radius: 50%;
}
</style>
