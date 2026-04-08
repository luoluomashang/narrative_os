<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="hitl-overlay" @click.self="handleBackdropClick">
        <div class="hitl-modal">
          <div class="hitl-header">
            <span class="hitl-badge">HITL 审批</span>
            <h2 class="hitl-title">AI 意图确认</h2>
          </div>

          <div class="hitl-body">
            <div class="hitl-intent">
              <div class="intent-label">AI 意图</div>
              <div class="intent-text">{{ intent }}</div>
            </div>

            <p class="hitl-hint">请审阅 AI 的行动意图，选择如何处理：</p>
          </div>

          <div class="hitl-actions">
            <button class="hitl-btn approve" @click="$emit('approve')">✓ 批准</button>
            <button class="hitl-btn regenerate" @click="$emit('regenerate')">↺ 重新生成</button>
            <button class="hitl-btn cancel" @click="$emit('cancel')">✗ 取消</button>
            <button class="hitl-btn takeover" @click="$emit('takeover')">✋ 手动接管</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { watch } from 'vue'

const props = defineProps<{
  modelValue: boolean
  intent: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'approve'): void
  (e: 'regenerate'): void
  (e: 'cancel'): void
  (e: 'takeover'): void
}>()

// Lock body scroll when visible
watch(() => props.modelValue, (val) => {
  document.body.style.overflow = val ? 'hidden' : ''
})

function handleBackdropClick() {
  // Do not close on backdrop click — HITL requires explicit action
}
</script>

<style scoped>
.hitl-overlay {
  position: fixed;
  inset: 0;
  background: rgba(10, 10, 11, 0.80);
  z-index: 300;
  display: flex;
  align-items: center;
  justify-content: center;
}
.hitl-modal {
  width: min(480px, 90vw);
  background: var(--color-surface-l1);
  border-radius: var(--radius-modal);
  border: 2px solid var(--color-hitl);
  box-shadow: 0 0 32px color-mix(in srgb, var(--color-hitl) 30%, transparent);
  overflow: hidden;
}
.hitl-header {
  padding: var(--spacing-md) var(--spacing-lg);
  border-bottom: 1px solid var(--color-surface-l2);
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
.hitl-badge {
  background: var(--color-hitl);
  color: var(--color-base);
  font-size: var(--text-caption);
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 4px;
  letter-spacing: 0.04em;
}
.hitl-title {
  font-size: var(--text-h2);
  font-weight: var(--weight-h2);
  margin: 0;
}

.hitl-body { padding: var(--spacing-lg); }
.intent-label {
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: var(--spacing-xs);
}
.intent-text {
  font-size: var(--text-body);
  line-height: var(--lh-body);
  background: var(--color-surface-l2);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm) var(--spacing-md);
  border-left: 3px solid var(--color-hitl);
}
.hitl-hint {
  margin-top: var(--spacing-md);
  font-size: 13px;
  color: var(--color-text-secondary);
}

.hitl-actions {
  display: flex;
  padding: var(--spacing-md) var(--spacing-lg) var(--spacing-lg);
  gap: var(--spacing-sm);
  flex-wrap: wrap;
}
.hitl-btn {
  flex: 1;
  min-width: 100px;
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-btn);
  border: none;
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: opacity 150ms, transform 80ms;
}
.hitl-btn:active { transform: scale(0.97); }
.hitl-btn.approve { background: var(--color-success); color: var(--color-text-primary); }
.hitl-btn.regenerate { background: var(--color-surface-l2); color: var(--color-text-primary); }
.hitl-btn.cancel { background: var(--color-error); color: var(--color-text-primary); }
.hitl-btn.takeover { background: var(--color-warning); color: var(--color-base); }

/* Transition */
.modal-enter-active, .modal-leave-active { transition: all 180ms ease; }
.modal-enter-from, .modal-leave-to { opacity: 0; transform: scale(0.96); }
</style>
