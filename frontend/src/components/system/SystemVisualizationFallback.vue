<template>
  <div class="system-visualization-fallback">
    <div class="system-visualization-fallback__copy">
      <p class="system-visualization-fallback__eyebrow">可视化回退</p>
      <h3 class="system-visualization-fallback__title">{{ title }}</h3>
      <p class="system-visualization-fallback__description">{{ description }}</p>
    </div>

    <div v-if="items.length" class="system-visualization-fallback__summary">
      <div v-for="item in items" :key="item.label" class="system-visualization-fallback__item">
        <span class="system-visualization-fallback__item-label">{{ item.label }}</span>
        <strong class="system-visualization-fallback__item-value">{{ item.value }}</strong>
      </div>
    </div>

    <div v-if="$slots.default" class="system-visualization-fallback__detail">
      <slot />
    </div>

    <div v-if="$slots.actions" class="system-visualization-fallback__actions">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title: string
    description: string
    items?: Array<{
      label: string
      value: string | number
    }>
  }>(),
  {
    items: () => [],
  },
)
</script>

<style scoped>
.system-visualization-fallback {
  display: grid;
  gap: var(--spacing-4);
  padding: var(--spacing-5);
  border-radius: var(--radius-xl);
  border: 1px dashed var(--color-border-default);
  background: color-mix(in srgb, var(--color-surface-2) 86%, transparent);
}

.system-visualization-fallback__eyebrow {
  margin: 0 0 var(--spacing-2);
  color: var(--color-text-3);
  font-size: var(--text-caption);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.system-visualization-fallback__title {
  margin: 0;
  color: var(--color-text-1);
  font-size: 1rem;
}

.system-visualization-fallback__description {
  margin: var(--spacing-2) 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-visualization-fallback__summary {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--spacing-3);
}

.system-visualization-fallback__item {
  display: grid;
  gap: 4px;
  padding: var(--spacing-3);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
}

.system-visualization-fallback__item-label {
  color: var(--color-text-3);
  font-size: var(--text-caption);
}

.system-visualization-fallback__item-value {
  color: var(--color-text-1);
}

.system-visualization-fallback__detail {
  display: grid;
  gap: var(--spacing-2);
}

.system-visualization-fallback__actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}
</style>