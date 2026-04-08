<template>
  <div class="hs-page">
    <header class="hs-header">
      <span class="hs-title">文本润色工作室</span>
      <span class="hs-subtitle">去 AI 痕迹 · 注入人味</span>
    </header>

    <!-- 控制栏 -->
    <div class="hs-controls">
      <div class="intensity-row">
        <label>润色强度 <span class="intensity-val">{{ Math.round(intensity * 100) }}%</span></label>
        <el-slider v-model="intensity" :min="0" :max="1" :step="0.05" style="flex: 1; margin: 0 12px" />
        <span class="intensity-hint">{{ intensityHint }}</span>
      </div>
      <div class="hs-actions">
        <NButton variant="primary" :disabled="processing || !originalText.trim()" @click="runHumanize">
          {{ processing ? '处理中…' : '去 AI 痕迹' }}
        </NButton>
        <NButton variant="ghost" @click="clearAll">清除</NButton>
        <div v-if="elapsed" class="elapsed-info">耗时 {{ elapsed }}ms</div>
      </div>
    </div>

    <!-- 双栏文本区 -->
    <div class="hs-columns">
      <div class="hs-col">
        <div class="col-header">
          <span>原始文本</span>
          <span class="char-count">{{ originalText.length }} 字</span>
        </div>
        <textarea
          v-model="originalText"
          class="hs-textarea"
          placeholder="粘贴原始文本至此…"
          :disabled="processing"
        />
      </div>
      <div class="hs-col">
        <div class="col-header">
          <span>处理后文本</span>
          <span v-if="result" class="char-count">{{ result.humanized.length }} 字 · {{ result.changes_count }} 处改动</span>
        </div>
        <textarea
          :value="result?.humanized ?? ''"
          class="hs-textarea"
          readonly
          placeholder="处理结果将在此显示…"
        />
      </div>
    </div>

    <!-- Diff 面板 -->
    <section v-if="result && result.diff.length > 0" class="hs-diff-section">
      <div class="hs-card">
        <div class="hs-card-title">变更详情 ({{ result.diff.length }} 处)</div>
        <div class="diff-list">
          <div v-for="(entry, i) in result.diff" :key="i" class="diff-row">
            <span class="diff-type-badge" :class="`diff-${entry.type}`">{{ diffTypeLabel(entry.type) }}</span>
            <del v-if="entry.old" class="diff-old">{{ entry.old }}</del>
            <ins v-if="entry.new" class="diff-new">{{ entry.new }}</ins>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import NButton from '@/components/common/NButton.vue'
import { chapters } from '@/api'
import type { HumanizeResponse } from '@/types/api'

const originalText = ref('')
const intensity = ref(0.5)
const processing = ref(false)
const result = ref<HumanizeResponse | null>(null)
const elapsed = ref(0)

const intensityHint = computed(() => {
  if (intensity.value < 0.3) return '轻度润色'
  if (intensity.value < 0.7) return '标准润色'
  return '深度改写'
})

function diffTypeLabel(t: string): string {
  return { replace: '改', insert: '增', delete: '删' }[t] ?? t
}

async function runHumanize() {
  if (!originalText.value.trim()) return
  processing.value = true
  result.value = null
  elapsed.value = 0
  const t0 = Date.now()
  try {
    const res = await chapters.humanize(originalText.value, intensity.value)
    result.value = res.data
    elapsed.value = Date.now() - t0
  } catch {
    result.value = null
  } finally {
    processing.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
  elapsed.value = 0
}
</script>

<style scoped>
.hs-page {
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: 100%;
  box-sizing: border-box;
}
.hs-header { display: flex; align-items: baseline; gap: 12px; }
.hs-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.hs-subtitle { font-size: 13px; color: var(--color-text-secondary); }
.hs-controls {
  display: flex;
  align-items: center;
  gap: 20px;
  flex-wrap: wrap;
}
.intensity-row { display: flex; align-items: center; gap: 10px; font-size: 13px; color: var(--color-text-secondary); }
.intensity-val { color: var(--color-accent); font-weight: 600; }
.hs-slider { width: 160px; accent-color: var(--color-accent); }
.intensity-hint { font-size: 12px; color: var(--color-text-secondary); min-width: 56px; }
.hs-actions { display: flex; align-items: center; gap: 10px; }
.elapsed-info { font-size: 12px; color: var(--color-text-secondary); }
.hs-columns { display: flex; gap: 16px; flex: 1; min-height: 320px; }
.hs-col { flex: 1; display: flex; flex-direction: column; gap: 6px; }
.col-header {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.char-count { font-weight: 400; color: var(--color-text-secondary); }
.hs-textarea {
  flex: 1;
  resize: none;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: 8px;
  padding: 12px;
  color: var(--color-text-primary);
  font-size: 14px;
  line-height: 1.7;
  font-family: inherit;
  outline: none;
  transition: border-color 150ms;
}
.hs-textarea:focus { border-color: var(--color-accent); }
.hs-textarea[readonly] { cursor: default; }
.hs-diff-section {}
.hs-card { background: var(--color-surface-l1); border: 1px solid var(--color-surface-l2); border-radius: 8px; padding: 16px; }
.hs-card-title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 12px; }
.diff-list { display: flex; flex-direction: column; gap: 6px; max-height: 240px; overflow-y: auto; }
.diff-row { display: flex; align-items: baseline; gap: 8px; font-size: 13px; flex-wrap: wrap; }
.diff-type-badge { flex-shrink: 0; font-size: 11px; padding: 1px 5px; border-radius: 3px; font-weight: 600; }
.diff-replace { background: rgba(230, 162, 60, 0.2); color: #e6a23c; }
.diff-insert { background: rgba(103, 194, 58, 0.2); color: #67c23a; }
.diff-delete { background: rgba(245, 108, 108, 0.2); color: #f56c6c; }
del.diff-old { color: #f56c6c; text-decoration: line-through; opacity: 0.8; }
ins.diff-new { color: #67c23a; text-decoration: none; }
</style>
