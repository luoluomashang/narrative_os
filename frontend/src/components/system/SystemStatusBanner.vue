<template>
  <section class="system-status-banner" :class="[`system-status-banner--${status}`, { 'system-status-banner--compact': compact }]">
    <div class="system-status-banner__main">
      <p class="system-status-banner__eyebrow">{{ statusLabel }}</p>
      <strong class="system-status-banner__title">{{ title }}</strong>
      <p class="system-status-banner__message">{{ message }}</p>
      <p v-if="description" class="system-status-banner__description">{{ description }}</p>
    </div>

    <div v-if="$slots.actions" class="system-status-banner__actions">
      <slot name="actions" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AsyncViewState } from '@/composables/useAsyncViewState'

const props = withDefaults(
  defineProps<{
    status?: Exclude<AsyncViewState, 'loading'>
    title: string
    message: string
    description?: string
    compact?: boolean
  }>(),
  {
    status: 'success',
    description: '',
    compact: false,
  },
)

const statusLabel = computed(() => {
  switch (props.status) {
    case 'blocking':
      return '流程阻塞'
    case 'offline':
      return '系统离线'
    case 'partial-failure':
      return '局部异常'
    case 'empty':
      return '暂无数据'
    default:
      return '状态反馈'
  }
})
</script>

<style scoped>
.system-status-banner {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  box-shadow: var(--shadow-xs);
}

.system-status-banner--compact {
  padding: var(--spacing-3) var(--spacing-4);
}

.system-status-banner--blocking {
  border-color: color-mix(in srgb, var(--color-warning) 22%, var(--color-border-subtle));
  background: color-mix(in srgb, var(--color-warning-soft) 78%, var(--color-surface-1));
}

.system-status-banner--offline,
.system-status-banner--partial-failure {
  border-color: color-mix(in srgb, var(--color-danger) 22%, var(--color-border-subtle));
  background: color-mix(in srgb, var(--color-danger-soft) 78%, var(--color-surface-1));
}

.system-status-banner--empty {
  border-style: dashed;
  background: color-mix(in srgb, var(--color-surface-2) 88%, transparent);
}

.system-status-banner--success {
  border-color: color-mix(in srgb, var(--color-success) 18%, var(--color-border-subtle));
  background: color-mix(in srgb, var(--color-success-soft) 72%, var(--color-surface-1));
}

.system-status-banner__main {
  min-width: 0;
}

.system-status-banner__eyebrow {
  margin: 0 0 var(--spacing-2);
  color: var(--color-text-3);
  font-size: var(--text-caption);
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.system-status-banner__title {
  display: block;
  color: var(--color-text-1);
}

.system-status-banner__message,
.system-status-banner__description {
  margin: 6px 0 0;
  line-height: 1.6;
}

.system-status-banner__message {
  color: var(--color-text-2);
}

.system-status-banner__description {
  color: var(--color-text-3);
}

.system-status-banner__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-wrap: wrap;
  flex-shrink: 0;
}

@media (max-width: 840px) {
  .system-status-banner {
    flex-direction: column;
  }

  .system-status-banner__actions {
    width: 100%;
  }
}
</style>