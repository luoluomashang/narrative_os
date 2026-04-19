<template>
  <component
    :is="tag"
    class="system-card"
    :class="[
      `system-card--${tone}`,
      `system-card--${padding}`,
      { 'system-card--interactive': interactive },
    ]"
    v-bind="$attrs"
  >
    <header v-if="title || description || $slots.header || $slots.actions" class="system-card__header">
      <div class="system-card__heading">
        <slot name="header">
          <h3 v-if="title" class="system-card__title">{{ title }}</h3>
          <p v-if="description" class="system-card__description">{{ description }}</p>
        </slot>
      </div>
      <div v-if="$slots.actions" class="system-card__actions">
        <slot name="actions" />
      </div>
    </header>

    <div class="system-card__body">
      <slot />
    </div>

    <footer v-if="$slots.footer" class="system-card__footer">
      <slot name="footer" />
    </footer>
  </component>
</template>

<script setup lang="ts">
defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    tag?: string
    title?: string
    description?: string
    tone?: 'default' | 'subtle' | 'accent' | 'warning' | 'danger'
    padding?: 'none' | 'md' | 'lg'
    interactive?: boolean
  }>(),
  {
    tag: 'section',
    title: '',
    description: '',
    tone: 'default',
    padding: 'md',
    interactive: false,
  },
)
</script>

<style scoped>
.system-card {
  border-radius: var(--radius-xl);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  box-shadow: var(--shadow-xs);
  color: inherit;
}

.system-card--subtle {
  background: color-mix(in srgb, var(--color-surface-2) 86%, transparent);
}

.system-card--accent {
  border-color: color-mix(in srgb, var(--color-accent) 18%, transparent);
  background: color-mix(in srgb, var(--color-accent-soft) 58%, var(--color-surface-1));
}

.system-card--warning {
  border-color: color-mix(in srgb, var(--color-warning) 22%, transparent);
  background: color-mix(in srgb, var(--color-warning-soft) 62%, var(--color-surface-1));
}

.system-card--danger {
  border-color: color-mix(in srgb, var(--color-danger) 22%, transparent);
  background: color-mix(in srgb, var(--color-danger-soft) 62%, var(--color-surface-1));
}

.system-card--interactive {
  cursor: pointer;
  transition:
    transform 150ms ease,
    border-color 150ms ease,
    box-shadow 150ms ease;
}

.system-card--interactive:hover {
  transform: translateY(-2px);
  border-color: color-mix(in srgb, var(--color-accent) 24%, transparent);
  box-shadow: var(--shadow-sm);
}

.system-card--none .system-card__body,
.system-card--none .system-card__header,
.system-card--none .system-card__footer {
  padding: 0;
}

.system-card--md .system-card__header,
.system-card--md .system-card__body,
.system-card--md .system-card__footer {
  padding: var(--spacing-5);
}

.system-card--lg .system-card__header,
.system-card--lg .system-card__body,
.system-card--lg .system-card__footer {
  padding: var(--spacing-6);
}

.system-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-4);
}

.system-card__header + .system-card__body {
  padding-top: 0;
}

.system-card__title {
  margin: 0;
  font-size: 1rem;
  color: var(--color-text-1);
}

.system-card__description {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-card__actions,
.system-card__footer {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.system-card__footer {
  border-top: 1px solid var(--color-border-subtle);
}
</style>
