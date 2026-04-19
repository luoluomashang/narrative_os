<template>
  <el-button
    class="system-button"
    :class="[
      `system-button--${variant}`,
      `system-button--${size}`,
      { 'system-button--block': block, 'system-button--icon-only': iconOnly },
    ]"
    :loading="loading"
    :disabled="disabled"
    v-bind="$attrs"
  >
    <slot />
  </el-button>
</template>

<script setup lang="ts">
defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'quiet'
    size?: 'sm' | 'md' | 'lg'
    block?: boolean
    iconOnly?: boolean
    loading?: boolean
    disabled?: boolean
  }>(),
  {
    variant: 'secondary',
    size: 'md',
    block: false,
    iconOnly: false,
    loading: false,
    disabled: false,
  },
)
</script>

<style scoped>
.system-button {
  --system-button-bg: var(--color-surface-2);
  --system-button-border: var(--color-border-subtle);
  --system-button-text: var(--color-text-1);
  --system-button-hover-bg: var(--color-surface-3);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: var(--radius-pill);
  border-color: var(--system-button-border);
  background: var(--system-button-bg);
  color: var(--system-button-text);
  box-shadow: none;
  transition:
    border-color 150ms ease,
    background 150ms ease,
    color 150ms ease,
    transform 150ms ease;
}

.system-button:hover:not(:disabled) {
  background: var(--system-button-hover-bg);
  border-color: color-mix(in srgb, var(--system-button-border) 88%, var(--color-border-strong));
  transform: translateY(-1px);
}

.system-button--sm {
  min-height: 32px;
  padding-inline: 12px;
}

.system-button--md {
  min-height: 38px;
  padding-inline: 14px;
}

.system-button--lg {
  min-height: 44px;
  padding-inline: 18px;
}

.system-button--primary {
  --system-button-bg: var(--color-accent);
  --system-button-border: var(--color-accent);
  --system-button-text: var(--color-text-inverse);
  --system-button-hover-bg: var(--color-accent-hover);
}

.system-button--secondary {
  --system-button-bg: var(--color-surface-1);
  --system-button-border: var(--color-border-default);
  --system-button-text: var(--color-text-1);
  --system-button-hover-bg: var(--color-surface-2);
}

.system-button--ghost {
  --system-button-bg: transparent;
  --system-button-border: transparent;
  --system-button-text: var(--color-text-2);
  --system-button-hover-bg: var(--color-surface-2);
}

.system-button--danger {
  --system-button-bg: var(--color-danger-soft);
  --system-button-border: color-mix(in srgb, var(--color-danger) 28%, transparent);
  --system-button-text: var(--color-danger);
  --system-button-hover-bg: color-mix(in srgb, var(--color-danger) 14%, transparent);
}

.system-button--quiet {
  --system-button-bg: transparent;
  --system-button-border: var(--color-border-subtle);
  --system-button-text: var(--color-text-2);
  --system-button-hover-bg: var(--color-surface-2);
}

.system-button--block {
  width: 100%;
}

.system-button--icon-only {
  padding-inline: 0;
  width: 38px;
}

.system-button--icon-only.system-button--sm {
  width: 32px;
}

.system-button--icon-only.system-button--lg {
  width: 44px;
}

:deep(.system-button span) {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
</style>
