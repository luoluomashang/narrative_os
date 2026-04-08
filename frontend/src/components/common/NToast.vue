<template>
  <Teleport to="body">
    <div class="n-toast-container">
      <TransitionGroup name="modal">
        <div
          v-for="t in toasts"
          :key="t.id"
          class="n-toast"
          :class="`n-toast--${t.type}`"
        >
          {{ t.message }}
        </div>
      </TransitionGroup>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface Toast {
  id: number
  type: 'info' | 'warning' | 'error' | 'success'
  message: string
}

const toasts = ref<Toast[]>([])
let counter = 0

function add(message: string, type: Toast['type'] = 'info', duration = 3000) {
  const id = ++counter
  toasts.value.push({ id, type, message })
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id)
  }, duration)
}

defineExpose({ add })
</script>

<style scoped>
.n-toast-container {
  position: fixed;
  bottom: 24px;
  right: 24px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 200;
}

.n-toast {
  padding: 10px 16px;
  border-radius: var(--radius-btn);
  font-size: var(--text-body);
  max-width: 320px;
  color: var(--color-text-primary);
  background: var(--color-surface-l1);
  border-left: 3px solid var(--color-ai-active);
}

.n-toast--info {
  border-left-color: var(--color-ai-active);
}
.n-toast--success {
  border-left-color: var(--color-success);
}
.n-toast--warning {
  border-left-color: var(--color-warning);
}
.n-toast--error {
  border-left-color: var(--color-error);
}
</style>
