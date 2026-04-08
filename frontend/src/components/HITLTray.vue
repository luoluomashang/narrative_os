<template>
  <!-- Tray toggle button (top-right corner) -->
  <div class="hitl-tray-anchor">
    <button class="tray-toggle" @click="open = !open" :class="{ active: open }">
      🔒
      <span v-if="items.length > 0" class="tray-badge">{{ items.length }}</span>
    </button>

    <!-- Slide-in drawer -->
    <Transition name="slide-in-right">
      <div v-if="open" class="tray-drawer">
        <div class="tray-header">
          <span class="tray-title">待审批 ({{ items.length }})</span>
          <div class="tray-bulk">
            <button class="bulk-btn approve" @click="approveAll">全部批准</button>
            <button class="bulk-btn reject" @click="rejectAll">全部拒绝</button>
          </div>
        </div>

        <div v-if="items.length === 0" class="tray-empty">暂无待审批项</div>

        <div v-for="item in items" :key="item.id" class="tray-item">
          <div class="tray-item-preview">{{ item.preview }}</div>
          <div class="tray-item-actions">
            <button class="tray-btn approve" @click="$emit('approve', item.id)">✓</button>
            <button class="tray-btn reject" @click="$emit('reject', item.id)">✗</button>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface HITLItem {
  id: string
  preview: string
}

const props = defineProps<{
  items: HITLItem[]
}>()

const emit = defineEmits<{
  (e: 'approve', id: string): void
  (e: 'reject', id: string): void
}>()

const open = ref(false)

function approveAll() {
  props.items.forEach(item => emit('approve', item.id))
}
function rejectAll() {
  props.items.forEach(item => emit('reject', item.id))
}
</script>

<style scoped>
.hitl-tray-anchor {
  position: fixed;
  top: var(--spacing-lg);
  right: var(--spacing-lg);
  z-index: 150;
}

.tray-toggle {
  position: relative;
  width: 44px;
  height: 44px;
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 18px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 150ms, border-color 150ms;
}
.tray-toggle.active,
.tray-toggle:hover { background: var(--color-surface-l1); border-color: var(--color-hitl); }

.tray-badge {
  position: absolute;
  top: -6px;
  right: -6px;
  background: var(--color-hitl);
  color: var(--color-base);
  font-size: 10px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
}

/* Drawer */
.tray-drawer {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 320px;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-modal);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  overflow: hidden;
}

.tray-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
}
.tray-title { font-size: 13px; font-weight: 600; }
.tray-bulk { display: flex; gap: 4px; }
.bulk-btn {
  font-size: var(--text-caption);
  border: none;
  border-radius: var(--radius-btn);
  padding: 2px 8px;
  cursor: pointer;
}
.bulk-btn.approve { background: var(--color-success); color: var(--color-text-primary); }
.bulk-btn.reject { background: var(--color-error); color: var(--color-text-primary); }

.tray-empty {
  padding: var(--spacing-md);
  text-align: center;
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}

.tray-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
}
.tray-item:last-child { border-bottom: none; }
.tray-item-preview {
  flex: 1;
  font-size: 13px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-secondary);
}
.tray-item-actions { display: flex; gap: 4px; flex-shrink: 0; }
.tray-btn {
  width: 28px; height: 28px;
  border: none;
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 13px;
}
.tray-btn.approve { background: var(--color-success); color: var(--color-text-primary); }
.tray-btn.reject { background: var(--color-error); color: var(--color-text-primary); }

/* Transitions */
.slide-in-right-enter-active { transition: transform 200ms ease, opacity 200ms ease; }
.slide-in-right-enter-from { transform: translateX(20px); opacity: 0; }
.slide-in-right-leave-active { transition: transform 150ms ease, opacity 150ms ease; }
.slide-in-right-leave-to { transform: translateX(20px); opacity: 0; }
</style>
