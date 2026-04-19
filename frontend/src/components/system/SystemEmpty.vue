<template>
  <div class="system-empty">
    <div class="system-empty__icon" aria-hidden="true">
      <slot name="icon">○</slot>
    </div>
    <h3 class="system-empty__title">{{ title }}</h3>
    <p class="system-empty__description">{{ description }}</p>
    <div v-if="$slots.action" class="system-empty__action">
      <slot name="action" />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
  }>(),
  {
    title: '暂无内容',
    description: '当前还没有可展示的数据。',
  },
)
</script>

<style scoped>
.system-empty {
  display: grid;
  justify-items: center;
  gap: var(--spacing-3);
  padding: var(--spacing-12) var(--spacing-5);
  border-radius: var(--radius-xl);
  border: 1px dashed var(--color-border-default);
  background: color-mix(in srgb, var(--color-surface-1) 86%, transparent);
  text-align: center;
}

.system-empty__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-size: 1.4rem;
}

.system-empty__title {
  margin: 0;
  color: var(--color-text-1);
}

.system-empty__description {
  margin: 0;
  max-width: 48ch;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-empty__action {
  margin-top: var(--spacing-1);
}
</style>
