<template>
  <button
    class="n-button"
    :class="[`n-button--${variant}`, { 'n-button--loading': loading }]"
    :disabled="loading || disabled"
    v-bind="$attrs"
  >
    <span v-if="loading" class="n-button__light breathing"></span>
    <slot v-else />
  </button>
</template>

<script setup lang="ts">
defineProps<{
  variant?: 'primary' | 'ghost' | 'danger'
  loading?: boolean
  disabled?: boolean
}>()
</script>

<style scoped>
.n-button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 6px 16px;
  border-radius: var(--radius-btn);
  font-size: var(--text-body);
  cursor: pointer;
  border: 1px solid transparent;
  transition: background 150ms, opacity 150ms;
  min-height: 32px;
  min-width: 60px;
}

.n-button:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.n-button--primary {
  background: var(--color-ai-active);
  color: var(--color-text-inverse);
  font-weight: 600;
}
.n-button--primary:hover:not(:disabled) {
  background: var(--color-accent-hover);
}

.n-button--ghost {
  background: transparent;
  color: var(--color-text-primary);
  border-color: var(--color-surface-l2);
}
.n-button--ghost:hover:not(:disabled) {
  background: var(--color-surface-l2);
}

.n-button--danger {
  background: transparent;
  color: var(--color-error);
  border-color: var(--color-error);
}
.n-button--danger:hover:not(:disabled) {
  background: var(--color-error);
  color: var(--color-text-inverse);
}

.n-button__light {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
</style>
