<template>
  <div class="system-error-state" :class="`system-error-state--${tone}`">
    <div class="system-error-state__body">
      <strong class="system-error-state__title">{{ title }}</strong>
      <p class="system-error-state__message">{{ message }}</p>
    </div>
    <div v-if="actionLabel || $slots.action" class="system-error-state__action">
      <slot name="action">
        <SystemButton variant="danger" size="sm" @click="emit('action')">{{ actionLabel }}</SystemButton>
      </slot>
    </div>
  </div>
</template>

<script setup lang="ts">
import SystemButton from './SystemButton.vue'

withDefaults(
  defineProps<{
    title?: string
    message: string
    tone?: 'danger' | 'warning'
    actionLabel?: string
  }>(),
  {
    title: '出现异常',
    tone: 'danger',
    actionLabel: '',
  },
)

const emit = defineEmits<{
  (event: 'action'): void
}>()
</script>

<style scoped>
.system-error-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-4);
  padding: var(--spacing-4) var(--spacing-5);
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
}

.system-error-state--danger {
  background: color-mix(in srgb, var(--color-danger-soft) 72%, var(--color-surface-1));
  border-color: color-mix(in srgb, var(--color-danger) 22%, transparent);
}

.system-error-state--warning {
  background: color-mix(in srgb, var(--color-warning-soft) 72%, var(--color-surface-1));
  border-color: color-mix(in srgb, var(--color-warning) 22%, transparent);
}

.system-error-state__title {
  display: block;
  color: var(--color-text-1);
}

.system-error-state__message {
  margin: 6px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

@media (max-width: 840px) {
  .system-error-state {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
