<template>
  <div class="cc-page">
    <header class="cc-header">
      <span class="cc-title">一致性检查</span>
    </header>

    <!-- 输入区 -->
    <section class="cc-section">
      <div class="cc-card">
        <div class="cc-card-title">检查设置</div>
        <div class="cc-form">
          <div class="form-row-inline">
            <div class="form-col">
              <label>项目</label>
              <input :value="projectId" class="cc-input" disabled />
            </div>
            <div class="form-col">
              <label>章节号</label>
              <input v-model.number="chapter" type="number" min="0" class="cc-input" placeholder="0" />
            </div>
          </div>
          <div class="form-row">
            <label>章节文本 <span class="char-count">{{ text.length }} / 10000</span></label>
            <textarea
              v-model="text"
              class="cc-textarea"
              rows="10"
              maxlength="10000"
              placeholder="粘贴章节文本至此…"
            />
          </div>
          <div class="cc-actions">
            <NButton variant="primary" :disabled="checking || !text.trim()" @click="runCheck">
              {{ checking ? '检查中…' : '开始检查' }}
            </NButton>
            <NButton variant="ghost" @click="clearAll">清除</NButton>
          </div>
        </div>
      </div>
    </section>

    <!-- 结果区 -->
    <section v-if="error" class="cc-section">
      <div class="result-banner banner-fail">{{ error }}</div>
    </section>

    <section v-if="result" class="cc-section">
      <!-- 通过/失败横幅 -->
      <div class="result-banner" :class="result.passed ? 'banner-pass' : 'banner-fail'">
        <span v-if="result.passed">✓ 一致性检查通过 — 未发现问题</span>
        <span v-else>✗ 发现 {{ result.issues.length }} 个问题</span>
      </div>

      <!-- Issues 列表 -->
      <div v-if="result.issues.length > 0" class="cc-card issues-card">
        <div class="cc-card-title">问题列表</div>
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
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import NButton from '@/components/common/NButton.vue'
import { useProjectStore } from '@/stores/projectStore'
import { chapters } from '@/api'
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
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 900px;
  margin: 0 auto;
}
.cc-header { display: flex; align-items: center; }
.cc-title { font-size: 20px; font-weight: 600; color: var(--color-text-primary); }
.cc-card {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: 8px;
  padding: 20px;
}
.cc-card-title { font-size: 15px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 16px; }
.cc-form { display: flex; flex-direction: column; gap: 14px; }
.form-row-inline { display: flex; gap: 16px; }
.form-col { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-row label, .form-col label { font-size: 13px; color: var(--color-text-secondary); display: flex; justify-content: space-between; }
.char-count { color: var(--color-text-secondary); font-weight: 400; }
.cc-input, .cc-textarea {
  background: var(--color-surface-l2);
  border: 1px solid var(--color-surface-l2);
  border-radius: 6px;
  padding: 8px 12px;
  color: var(--color-text-primary);
  font-size: 14px;
  outline: none;
  transition: border-color 150ms;
}
.cc-input:focus, .cc-textarea:focus { border-color: var(--color-accent); }
.cc-textarea { resize: vertical; font-family: inherit; }
.cc-actions { display: flex; gap: 10px; }
.result-banner {
  border-radius: 8px;
  padding: 14px 20px;
  font-size: 15px;
  font-weight: 600;
}
.banner-pass { background: rgba(103, 194, 58, 0.15); color: #67c23a; border: 1px solid rgba(103, 194, 58, 0.3); }
.banner-fail { background: rgba(245, 108, 108, 0.15); color: #f56c6c; border: 1px solid rgba(245, 108, 108, 0.3); }
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
.sev-hard { background: rgba(245, 108, 108, 0.2); color: #f56c6c; }
.sev-soft { background: rgba(230, 162, 60, 0.2); color: #e6a23c; }
.sev-info { background: rgba(64, 158, 255, 0.2); color: #409eff; }
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
</style>
