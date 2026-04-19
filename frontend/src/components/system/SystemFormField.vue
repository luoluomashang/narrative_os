<template>
  <div class="system-form-field" :class="{ 'system-form-field--inline': inline }">
    <div v-if="label || hint || $slots.label" class="system-form-field__header">
      <label v-if="label || $slots.label" class="system-form-field__label" :for="forId">
        <slot name="label">{{ label }}</slot>
        <span v-if="required" class="system-form-field__required">*</span>
      </label>
      <p v-if="hint" class="system-form-field__hint">{{ hint }}</p>
    </div>

    <div class="system-form-field__control">
      <slot />
    </div>

    <p v-if="error" class="system-form-field__error">{{ error }}</p>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label?: string
    hint?: string
    error?: string
    required?: boolean
    inline?: boolean
    forId?: string
  }>(),
  {
    label: '',
    hint: '',
    error: '',
    required: false,
    inline: false,
    forId: '',
  },
)
</script>

<style scoped>
.system-form-field {
  display: grid;
  gap: var(--spacing-2);
}

.system-form-field--inline {
  grid-template-columns: minmax(120px, 180px) minmax(0, 1fr);
  align-items: start;
}

.system-form-field__header {
  display: grid;
  gap: 6px;
}

.system-form-field__label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--color-text-1);
}

.system-form-field__required {
  color: var(--color-danger);
}

.system-form-field__hint {
  margin: 0;
  color: var(--color-text-3);
  font-size: var(--text-caption);
  line-height: 1.5;
}

.system-form-field__error {
  margin: 0;
  color: var(--color-danger);
  font-size: var(--text-caption);
}

@media (max-width: 720px) {
  .system-form-field--inline {
    grid-template-columns: 1fr;
  }
}
</style>