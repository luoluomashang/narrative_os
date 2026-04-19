<template>
  <section class="system-page-header" :class="{ 'system-page-header--compact': compact }">
    <div class="system-page-header__main">
      <div class="system-page-header__copy">
        <p v-if="eyebrow" class="system-page-header__eyebrow">{{ eyebrow }}</p>
        <h1 class="system-page-header__title">{{ title }}</h1>
        <p v-if="description" class="system-page-header__description">{{ description }}</p>
      </div>

      <div v-if="$slots.meta || $slots.actions" class="system-page-header__aside">
        <div v-if="$slots.meta" class="system-page-header__meta">
          <slot name="meta" />
        </div>
        <div v-if="$slots.actions" class="system-page-header__actions">
          <slot name="actions" />
        </div>
      </div>
    </div>

    <div v-if="$slots.navigation" class="system-page-header__navigation">
      <slot name="navigation" />
    </div>
  </section>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    eyebrow?: string
    title: string
    description?: string
    compact?: boolean
  }>(),
  {
    eyebrow: '',
    description: '',
    compact: false,
  },
)
</script>

<style scoped>
.system-page-header {
  display: grid;
  gap: var(--spacing-3);
}

.system-page-header--compact {
  gap: var(--spacing-2);
}

.system-page-header__main {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--spacing-5);
}

.system-page-header__eyebrow {
  margin: 0 0 var(--spacing-2);
  font-size: var(--text-caption);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.system-page-header__title {
  margin: 0;
  font-size: 1.9rem;
  line-height: 1.1;
  color: var(--color-text-1);
}

.system-page-header__description {
  margin: var(--spacing-2) 0 0;
  max-width: 68ch;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-page-header__aside,
.system-page-header__actions,
.system-page-header__meta,
.system-page-header__navigation {
  display: flex;
  gap: var(--spacing-2);
  align-items: center;
  flex-wrap: wrap;
}

.system-page-header__aside {
  flex-direction: column;
  align-items: flex-end;
}

@media (max-width: 960px) {
  .system-page-header__main,
  .system-page-header__aside {
    flex-direction: column;
    align-items: flex-start;
  }

  .system-page-header__title {
    font-size: 1.55rem;
  }
}
</style>
