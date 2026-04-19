<template>
  <div class="diff-overlay" @click.self="$emit('close')">
    <div class="diff-modal">
      <div class="diff-header">
        <span class="diff-title">改写对比</span>
        <div class="diff-header-actions">
          <NButton variant="primary" @click="acceptAll">全部接受</NButton>
          <NButton variant="ghost" @click="$emit('close')">关闭</NButton>
        </div>
      </div>

      <div class="diff-container">
        <div class="diff-pane">
          <div class="diff-pane-label">原文</div>
          <div class="diff-lines">
            <div
              v-for="(seg, i) in segments"
              :key="i"
              class="diff-line"
              :class="seg.kind"
            >
              <span class="line-num">{{ i + 1 }}</span>
              <span class="line-text">{{ seg.original }}</span>
            </div>
          </div>
        </div>

        <div class="diff-pane">
          <div class="diff-pane-label">改写</div>
          <div class="diff-lines">
            <div
              v-for="(seg, i) in segments"
              :key="i"
              class="diff-line modified"
              :class="seg.kind"
            >
              <span class="line-num">{{ i + 1 }}</span>
              <span class="line-text">{{ seg.modified }}</span>
              <div class="line-actions" v-if="seg.kind === 'changed'">
                <button class="la-btn accept" @click="acceptLine(i)" title="接受">✓</button>
                <button class="la-btn reject" @click="rejectLine(i)" title="拒绝">✗</button>
                <button class="la-btn edit" @click="editLine(i)" title="修改">✏</button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Inline edit textarea -->
      <div v-if="editingLine !== null" class="inline-edit">
        <textarea v-model="editingText" class="inline-textarea" rows="3" />
        <div class="inline-edit-actions">
          <NButton variant="primary" @click="submitEdit">提交修改</NButton>
          <NButton variant="ghost" @click="editingLine = null">取消</NButton>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import NButton from '@/components/common/NButton.vue'

const props = defineProps<{
  original: string
  modified: string
}>()

const emit = defineEmits<{
  (e: 'accept', text: string): void
  (e: 'close'): void
}>()

interface Segment {
  kind: 'same' | 'changed' | 'added' | 'removed'
  original: string
  modified: string
}

// Simple line-diff: split by sentence periods/newlines
const workingLines = ref<string[]>([])

const originalLines = computed(() =>
  props.original.split(/(?<=[。！？\n])/g).filter(Boolean)
)
const modifiedLines = computed(() =>
  props.modified.split(/(?<=[。！？\n])/g).filter(Boolean)
)

const segments = computed<Segment[]>(() => {
  const len = Math.max(originalLines.value.length, modifiedLines.value.length)
  const result: Segment[] = []
  for (let i = 0; i < len; i++) {
    const orig = originalLines.value[i] ?? ''
    const mod = workingLines.value[i] ?? modifiedLines.value[i] ?? ''
    if (orig === mod) {
      result.push({ kind: 'same', original: orig, modified: mod })
    } else if (!orig) {
      result.push({ kind: 'added', original: '', modified: mod })
    } else if (!mod) {
      result.push({ kind: 'removed', original: orig, modified: '' })
    } else {
      result.push({ kind: 'changed', original: orig, modified: mod })
    }
  }
  return result
})

// Initialise working lines when segments computed first time
const initialized = ref(false)
if (!initialized.value) {
  workingLines.value = modifiedLines.value.slice()
  initialized.value = true
}

function acceptLine(_i: number) {
  // keep the modified line (already in workingLines)
}
function rejectLine(i: number) {
  // revert this line to original
  workingLines.value[i] = originalLines.value[i] ?? ''
}

const editingLine = ref<number | null>(null)
const editingText = ref('')
function editLine(i: number) {
  editingLine.value = i
  editingText.value = workingLines.value[i] ?? modifiedLines.value[i] ?? ''
}
function submitEdit() {
  if (editingLine.value !== null) {
    workingLines.value[editingLine.value] = editingText.value
  }
  editingLine.value = null
}

function acceptAll() {
  const finalText = workingLines.value.length > 0
    ? workingLines.value.join('')
    : props.modified
  emit('accept', finalText)
}
</script>

<style scoped>
.diff-overlay {
  position: fixed;
  inset: 0;
  background: var(--color-overlay);
  z-index: 200;
  display: flex;
  align-items: center;
  justify-content: center;
}
.diff-modal {
  width: min(900px, 92vw);
  max-height: 85vh;
  background: var(--color-surface-l1);
  border-radius: var(--radius-modal);
  border: 2px solid var(--color-hitl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.diff-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.diff-title { font-size: var(--text-h2); font-weight: var(--weight-h2); }
.diff-header-actions { display: flex; gap: var(--spacing-sm); }

.diff-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  overflow: auto;
  flex: 1;
}
.diff-pane { overflow: auto; }
.diff-pane + .diff-pane { border-left: 1px solid var(--color-surface-l2); }
.diff-pane-label {
  position: sticky;
  top: 0;
  background: var(--color-surface-l1);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  padding: 4px var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  z-index: 1;
}
.diff-line {
  display: flex;
  align-items: flex-start;
  padding: 3px var(--spacing-md) 3px var(--spacing-sm);
  gap: var(--spacing-sm);
  position: relative;
}
.diff-line.changed { background: color-mix(in srgb, var(--color-warning) 8%, transparent); }
.diff-line.added { background: color-mix(in srgb, var(--color-success) 10%, transparent); }
.diff-line.removed { background: color-mix(in srgb, var(--color-error) 10%, transparent); }
.line-num { font-size: var(--text-caption); color: var(--color-text-secondary); flex-shrink: 0; width: 24px; }
.line-text { font-size: 14px; line-height: 1.7; flex: 1; }
.line-actions {
  display: flex;
  gap: 2px;
  flex-shrink: 0;
  opacity: 0;
  transition: opacity 150ms;
}
.diff-line:hover .line-actions { opacity: 1; }
.la-btn {
  width: 22px; height: 22px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  display: flex; align-items: center; justify-content: center;
}
.la-btn.accept { background: var(--color-success); color: var(--color-text-primary); }
.la-btn.reject { background: var(--color-error); color: var(--color-text-primary); }
.la-btn.edit { background: var(--color-surface-l2); color: var(--color-text-primary); }

.inline-edit {
  border-top: 1px solid var(--color-surface-l2);
  padding: var(--spacing-md);
  flex-shrink: 0;
}
.inline-textarea {
  width: 100%;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-ai-active);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  font-size: var(--text-body);
  padding: var(--spacing-sm);
  resize: vertical;
  box-sizing: border-box;
}
.inline-edit-actions { display: flex; gap: var(--spacing-sm); margin-top: var(--spacing-sm); }
</style>
