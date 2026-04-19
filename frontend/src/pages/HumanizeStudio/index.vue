<template>
  <div class="hs-page">
    <SystemPageHeader
      eyebrow="Humanize Studio"
      title="文本润色工作室"
      description="去 AI 痕迹，注入人味，并保留原文与改写结果的对照。"
    />

    <SystemSection title="润色设置" description="选择润色强度后执行文本处理。" dense>
      <SystemCard tone="subtle">
        <div class="hs-controls">
          <div class="intensity-row">
            <label>润色强度 <span class="intensity-val">{{ Math.round(intensity * 100) }}%</span></label>
            <el-slider v-model="intensity" :min="0" :max="1" :step="0.05" style="flex: 1; margin: 0 12px" />
            <span class="intensity-hint">{{ intensityHint }}</span>
          </div>
          <div class="hs-actions">
            <SystemButton variant="primary" :loading="processing" :disabled="processing || !originalText.trim()" @click="runHumanize">
              {{ processing ? '处理中…' : '去 AI 痕迹' }}
            </SystemButton>
            <SystemButton variant="ghost" @click="clearAll">清除</SystemButton>
            <div v-if="elapsed" class="elapsed-info">耗时 {{ elapsed }}ms</div>
          </div>
        </div>
      </SystemCard>
    </SystemSection>

    <SystemErrorState v-if="error" title="润色失败" :message="error" />

    <SystemSection title="文本对照" description="左侧原始文本，右侧展示处理结果。" dense>
      <div class="hs-columns">
        <SystemCard class="hs-col-card" title="原始文本">
          <template #actions>
            <span class="char-count">{{ originalText.length }} 字</span>
          </template>
          <textarea
            v-model="originalText"
            class="hs-textarea"
            placeholder="粘贴原始文本至此…"
            :disabled="processing"
          />
        </SystemCard>

        <SystemCard class="hs-col-card" title="处理后文本">
          <template #actions>
            <span v-if="result" class="char-count">{{ result.humanized.length }} 字 · {{ result.changes_count }} 处改动</span>
          </template>

          <SystemSkeleton v-if="processing" :rows="10" show-header />
          <textarea
            v-else-if="result"
            :value="result.humanized"
            class="hs-textarea"
            readonly
            placeholder="处理结果将在此显示…"
          />
          <SystemEmpty
            v-else
            title="等待处理结果"
            description="输入原始文本并执行润色后，这里会显示改写结果。"
          />
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection v-if="result && result.diff.length > 0" :title="`变更详情 (${result.diff.length} 处)`" description="逐项查看替换、插入与删除明细。" dense>
      <SystemCard>
        <div class="diff-list">
          <div v-for="(entry, i) in result.diff" :key="i" class="diff-row">
            <span class="diff-type-badge" :class="`diff-${entry.type}`">{{ diffTypeLabel(entry.type) }}</span>
            <del v-if="entry.old" class="diff-old">{{ entry.old }}</del>
            <ins v-if="entry.new" class="diff-new">{{ entry.new }}</ins>
          </div>
        </div>
      </SystemCard>
    </SystemSection>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { chapters } from '@/api'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import type { HumanizeResponse } from '@/types/api'

const originalText = ref('')
const intensity = ref(0.5)
const processing = ref(false)
const result = ref<HumanizeResponse | null>(null)
const elapsed = ref(0)
const error = ref('')

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
  error.value = ''
  const t0 = Date.now()
  try {
    const res = await chapters.humanize(originalText.value, intensity.value)
    result.value = res.data
    elapsed.value = Date.now() - t0
  } catch {
    result.value = null
    error.value = '润色失败，请稍后重试。'
  } finally {
    processing.value = false
  }
}

function clearAll() {
  originalText.value = ''
  result.value = null
  elapsed.value = 0
  error.value = ''
}
</script>

<style scoped>
.hs-page {
  padding: 24px;
  display: grid;
  gap: 20px;
  height: 100%;
  box-sizing: border-box;
  overflow-y: auto;
}

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
.hs-columns { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; min-height: 320px; }
.hs-col-card { display: flex; flex-direction: column; min-height: 320px; }
.hs-col-card :deep(.system-card__body) { flex: 1; display: flex; min-height: 0; }
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
.diff-list { display: flex; flex-direction: column; gap: 6px; max-height: 240px; overflow-y: auto; }
.diff-row { display: flex; align-items: baseline; gap: 8px; font-size: 13px; flex-wrap: wrap; }
.diff-type-badge { flex-shrink: 0; font-size: 11px; padding: 1px 5px; border-radius: 3px; font-weight: 600; }
.diff-replace { background: var(--color-warning-soft); color: var(--color-warning); }
.diff-insert { background: var(--color-success-soft); color: var(--color-success); }
.diff-delete { background: var(--color-danger-soft); color: var(--color-danger); }
del.diff-old { color: var(--color-danger); text-decoration: line-through; opacity: 0.8; }
ins.diff-new { color: var(--color-success); text-decoration: none; }

@media (max-width: 900px) {
  .hs-columns {
    grid-template-columns: 1fr;
  }
}
</style>
