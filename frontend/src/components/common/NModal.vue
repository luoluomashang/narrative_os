<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="n-modal-overlay" @click.self="emit('update:modelValue', false)">
        <div class="n-modal" :class="{ 'n-modal--hitl': hitl }">
          <slot />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: boolean
  hitl?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: boolean): void
}>()
</script>

<style scoped>
.n-modal-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-overlay);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.n-modal {
  background: var(--color-surface-l1);
  border-radius: var(--radius-modal);
  border: 1px solid var(--color-surface-l2);
  padding: var(--spacing-lg);
  min-width: 360px;
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
}

.n-modal--hitl {
  border: 2px solid var(--color-hitl);
}
</style>
