<template>
  <div class="cc-page">
    <SystemPageHeader
      eyebrow="Consistency Check"
      title="一致性检查"
      description="对章节文本进行人物、世界规则、情节因果与时间线一致性扫描。"
    />

    <SystemSection title="检查设置" description="选择项目与章节号，粘贴文本后启动检查。">
      <SystemCard>
        <div class="cc-form">
          <div class="form-row-inline">
            <SystemFormField label="项目">
              <input :value="projectId" class="cc-input" disabled />
            </SystemFormField>
            <SystemFormField label="章节号">
              <input v-model.number="chapter" type="number" min="0" class="cc-input" placeholder="0" />
            </SystemFormField>
          </div>
          <SystemFormField label="章节文本" :hint="`当前 ${text.length} / 10000 字`">
            <textarea
              v-model="text"
              class="cc-textarea"
              rows="10"
              maxlength="10000"
              placeholder="粘贴章节文本至此…"
            />
          </SystemFormField>
          <div class="cc-actions">
            <SystemButton variant="primary" :loading="checking" :disabled="checking || !text.trim()" @click="runCheck">
              {{ checking ? '检查中…' : '开始检查' }}
            </SystemButton>
            <SystemButton variant="ghost" @click="clearAll">清除</SystemButton>
          </div>
        </div>
      </SystemCard>
    </SystemSection>

    <SystemSkeleton v-if="checking" :rows="5" show-header card />

    <SystemErrorState v-if="error" title="一致性检查失败" :message="error" />

    <SystemSection v-if="result" title="检查结果" description="汇总检查状态并列出具体问题。">
      <SystemCard :tone="result.passed ? 'accent' : 'warning'" class="result-summary-card">
        <span v-if="result.passed">✓ 一致性检查通过 — 未发现问题</span>
        <span v-else>✗ 发现 {{ result.issues.length }} 个问题</span>
      </SystemCard>

      <SystemCard v-if="result.issues.length > 0" title="问题列表" class="issues-card">
        <div class="issue-list">
          <div v-for="(issue, i) in result.issues" :key="i" class="issue-row">
            <span class="severity-badge" :class="`sev-${issue.severity}`">
              {{ severityLabel(issue.severity) }}
            </span>
            <span class="dim-tag">{{ dimensionLabel(issue.dimension) }}</span>
            <div class="issue-body">
              <div class="issue-desc">{{ issue.description }}</div>
              <div v-if="issue.suggestion" class="issue-suggest">💡 {{ issue.suggestion }}</div>
            </div>
            <span class="issue-conf">{{ Math.round(issue.confidence * 100) }}%</span>
          </div>
        </div>
      </SystemCard>
    </SystemSection>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useProjectStore } from '@/stores/projectStore'
import { chapters } from '@/api'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemFormField from '@/components/system/SystemFormField.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import type { CheckChapterResponse } from '@/types/api'

const store = useProjectStore()
const projectId = computed(() => store.projectId || 'default')
const chapter = ref(0)
const text = ref('')
const checking = ref(false)
const result = ref<CheckChapterResponse | null>(null)
const error = ref('')

function severityLabel(s: string): string {
  return { hard: '🔴 严重', soft: '🟡 警告', info: '🔵 提示' }[s] ?? s
}

function dimensionLabel(d: string): string {
  return {
    character: '人物矛盾',
    world: '世界规则',
    plot: '情节因果',
    timeline: '时间线',
  }[d] ?? d
}

async function runCheck() {
  if (!text.value.trim()) return
  checking.value = true
  result.value = null
  error.value = ''
  try {
    const res = await chapters.check(text.value, projectId.value, chapter.value)
    result.value = res.data
  } catch {
    result.value = null
    error.value = '一致性检查失败，请检查服务状态后重试。'
  } finally {
    checking.value = false
  }
}

function clearAll() {
  text.value = ''
  result.value = null
  error.value = ''
}
</script>

<style scoped>
.cc-page {
  padding: 24px;
  display: grid;
  gap: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.cc-form { display: flex; flex-direction: column; gap: 14px; }
.form-row-inline { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.cc-input, .cc-textarea {
  width: 100%;
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--color-text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 150ms;
  box-sizing: border-box;
}
.cc-input:focus, .cc-textarea:focus { border-color: var(--color-accent); }
.cc-textarea { resize: vertical; font-family: inherit; }
.cc-actions { display: flex; gap: 10px; }
.result-summary-card { font-size: 15px; font-weight: 600; }
.issues-card { margin-top: 0; }
.issue-list { display: flex; flex-direction: column; gap: 10px; }
.issue-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  background: var(--color-surface-l2);
  border-radius: 6px;
}
.severity-badge {
  flex-shrink: 0;
  font-size: 12px;
  white-space: nowrap;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--color-surface-l1);
}
.sev-hard { background: var(--color-danger-soft); color: var(--color-danger); }
.sev-soft { background: var(--color-warning-soft); color: var(--color-warning); }
.sev-info { background: var(--color-info-soft); color: var(--color-info); }
.dim-tag {
  flex-shrink: 0;
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: var(--color-surface-l1);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-surface-l2);
}
.issue-body { flex: 1; }
.issue-desc { font-size: 14px; color: var(--color-text-primary); }
.issue-suggest { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; }
.issue-conf { flex-shrink: 0; font-size: 11px; color: var(--color-text-secondary); white-space: nowrap; }

@media (max-width: 720px) {
  .form-row-inline {
    grid-template-columns: 1fr;
  }
}
</style>
