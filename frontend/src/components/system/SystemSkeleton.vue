<template>
  <div class="system-skeleton" :class="{ 'system-skeleton--card': card }" aria-hidden="true">
    <div v-if="showHeader" class="system-skeleton__title shimmer"></div>
    <div class="system-skeleton__lines">
      <span
        v-for="row in rows"
        :key="row"
        class="system-skeleton__line shimmer"
        :style="{ width: rowWidths[(row - 1) % rowWidths.length] }"
      ></span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

withDefaults(
  defineProps<{
    rows?: number
    showHeader?: boolean
    card?: boolean
  }>(),
  {
    rows: 3,
    showHeader: false,
    card: false,
  },
)

const rowWidths = computed(() => ['100%', '94%', '86%', '72%'])
</script>

<style scoped>
.system-skeleton {
  display: grid;
  gap: var(--spacing-3);
}

.system-skeleton--card {
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 92%, transparent);
}

.system-skeleton__title,
.system-skeleton__line {
  display: block;
  border-radius: 999px;
  background: linear-gradient(
    90deg,
    color-mix(in srgb, var(--color-surface-3) 88%, transparent) 20%,
    color-mix(in srgb, var(--color-surface-4) 82%, transparent) 50%,
    color-mix(in srgb, var(--color-surface-3) 88%, transparent) 80%
  );
  background-size: 240% 100%;
}

.system-skeleton__title {
  width: 28%;
  height: 14px;
}

.system-skeleton__lines {
  display: grid;
  gap: 10px;
}

.system-skeleton__line {
  height: 12px;
}

.shimmer {
  animation: system-skeleton-shimmer 1.25s linear infinite;
}

@keyframes system-skeleton-shimmer {
  0% { background-position: 100% 0; }
  100% { background-position: -100% 0; }
}
</style>
