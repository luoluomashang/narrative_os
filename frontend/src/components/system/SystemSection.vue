<template>
  <section class="system-section" :class="{ 'system-section--dense': dense }">
    <header v-if="title || description || $slots.actions" class="system-section__header">
      <div class="system-section__copy">
        <h2 v-if="title" class="system-section__title">{{ title }}</h2>
        <p v-if="description" class="system-section__description">{{ description }}</p>
      </div>
      <div v-if="$slots.actions" class="system-section__actions">
        <slot name="actions" />
      </div>
    </header>
    <div class="system-section__body">
      <slot />
    </div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    title?: string
    description?: string
    dense?: boolean
  }>(),
  {
    title: '',
    description: '',
    dense: false,
  },
)
</script>

<style scoped>
.system-section {
  display: grid;
  gap: var(--spacing-4);
}

.system-section--dense {
  gap: var(--spacing-3);
}

.system-section__header {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--spacing-4);
}

.system-section__title {
  margin: 0;
  font-size: 1.05rem;
  color: var(--color-text-1);
}

.system-section__description {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-section__actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

.system-section__body {
  min-width: 0;
}

@media (max-width: 840px) {
  .system-section__header {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
