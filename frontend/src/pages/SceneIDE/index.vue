<template>
  <div class="scene-ide-page">
    <!-- Header bar -->
    <div class="ide-header">
      <span class="ide-title">场景生成 IDE</span>
      <div class="ide-controls">
        <input
          v-model.number="currentChapter"
          type="number"
          min="1"
          max="9999"
          class="chapter-input"
          placeholder="章节号"
          title="章节号（1-9999）"
        />
        <input
          v-model="targetSummary"
          type="text"
          class="summary-input"
          placeholder="本章摘要（可选）"
          title="本章目标摘要"
        />
        <select v-model="llmRoute" class="llm-select">
          <option value="gpt4o">GPT-4o — 精准 / 高成本</option>
          <option value="claude3">Claude 3.5 — 均衡 / 中成本</option>
          <option value="llama3">Llama 3 — 快速 / 低成本</option>
        </select>
        <NButton variant="primary" :loading="generating" @click="generate">生成</NButton>
        <NButton variant="ghost" @click="planOnly">仅规划</NButton>
      </div>
    </div>

    <!-- Three-column layout -->
    <div class="ide-columns">
      <!-- Left: Context Injection (25%) -->
      <div class="ide-col ide-left">
        <div class="col-header">上下文注入</div>

        <div
          v-for="block in contextBlocks"
          :key="block.id"
          class="ctx-block"
          :class="{ excluded: block.excluded }"
        >
          <div class="ctx-block-header">
            <span class="ctx-block-title">{{ block.label }}</span>
            <button class="exclude-btn" @click="toggleExclude(block.id)">
              {{ block.excluded ? '恢复' : '排除' }}
            </button>
          </div>
          <div class="ctx-block-body">{{ block.preview }}</div>
        </div>

        <div class="token-estimate">
          Token 估算：<strong>{{ estimatedTokens }}</strong>
        </div>
      </div>

      <!-- Center: Generation Control + Output (50%) -->
      <div class="ide-col ide-center">
        <!-- Control row -->
        <div class="gen-controls">
          <div class="control-group">
            <label>文长</label>
            <div class="btn-group">
              <button
                v-for="l in lengths"
                :key="l.value"
                :class="['len-btn', { active: lengthMode === l.value }]"
                @click="lengthMode = l.value"
              >{{ l.label }}</button>
            </div>
          </div>
          <div class="control-group">
            <label>温度</label>
            <NSlider v-model="temperature" :min="0" :max="1" :step="0.05" />
          </div>
          <!-- Skill queue -->
          <div class="skill-queue" @dragover.prevent @drop="onSkillDrop">
            <span v-if="skillQueue.length === 0" class="queue-hint">拖拽技能到此</span>
            <NTag
              v-for="s in skillQueue"
              :key="s"
              :label="s"
              color="var(--color-ai-active)"
            />
          </div>
        </div>

        <!-- Output area -->
        <div
          class="output-area"
          :class="{
            'border-generating': generating,
            'border-done': !generating && generatedText.length > 0,
          }"
        >
          <div class="output-tools">
            <button class="tool-btn" @click="copyOutput" title="复制">⎘</button>
            <button class="tool-btn" @click="clearOutput" title="清除">✕</button>
          </div>

          <NBreathingLight v-if="generating" :size="8" color="var(--color-ai-active)" />

          <div v-if="errorMsg" class="error-card">
            <span>⚠ {{ errorMsg }}</span>
          </div>
          <NTypewriter v-else :text="generatedText" :speed="25" class="output-text" />

          <!-- Inline annotations -->
          <div v-if="annotations.length > 0" class="annotation-legend">
            <span class="annotation-soft">黄色下划线</span> 次要设定冲突 ·
            <span class="annotation-hard">红色波浪</span> 严重 OOC
          </div>
        </div>
      </div>

      <!-- Right: Real-time Diagnostics (25%) -->
      <div class="ide-col ide-right">
        <div class="col-header">实时诊断</div>

        <div v-if="diagnostics.length === 0 && !generating" class="diag-empty">
          生成后自动分析…
        </div>

        <div
          v-for="(d, i) in diagnostics"
          :key="i"
          class="diag-card"
          :class="`diag-${d.type}`"
        >
          <div class="diag-icon">{{ diagIcon(d.type) }}</div>
          <div class="diag-body">
            <div class="diag-title">{{ d.title }}</div>
            <div class="diag-desc">{{ d.description }}</div>
            <div v-if="d.type === 'warning'" class="diag-actions">
              <button class="diag-btn" @click="requestRewrite(i)">请求改写</button>
              <button class="diag-btn ghost" @click="ignoreDiag(i)">标记忽略</button>
            </div>
          </div>
        </div>

        <!-- Token cost info -->
        <div class="cost-info">
          <span>输入 {{ inputTokens }} token</span>
          <span>输出 {{ outputTokens }} token</span>
        </div>

        <!-- Generation pipeline stepper -->
        <div class="col-header" style="margin-top:16px">生成流水线</div>
        <NWorkflowStepper :steps="pipelineSteps" :current="pipelineCurrent" style="margin-top:8px" />
      </div>
    </div>

    <!-- DiffView modal -->
    <DiffView
      v-if="showDiff"
      :original="diffOriginal"
      :modified="diffModified"
      @accept="onDiffAccept"
      @close="showDiff = false"
    />

    <!-- HITL tray -->
    <HITLTray :items="hitlItems" @approve="approveHITL" @reject="rejectHITL" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import NButton from '@/components/common/NButton.vue'
import NSlider from '@/components/common/NSlider.vue'
import NTag from '@/components/common/NTag.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import NTypewriter from '@/components/common/NTypewriter.vue'
import NWorkflowStepper from '@/components/common/NWorkflowStepper.vue'
import DiffView from '@/components/DiffView.vue'
import HITLTray from '@/components/HITLTray.vue'
import axios from 'axios'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

// 章节信息
const currentChapter = ref(1)

onMounted(() => {
  const q = route.query.chapter
  if (q) currentChapter.value = Number(q) || 1
})
const targetSummary = ref('')

// ── Context blocks ────────────────────────────────────────────────
interface CtxBlock { id: string; label: string; preview: string; excluded: boolean; tokens: number }
const contextBlocks = ref<CtxBlock[]>([
  { id: 'plot_node', label: '当前情节节点', preview: '第一章·初始', excluded: false, tokens: 120 },
  { id: 'characters', label: '相关角色状态', preview: '主角 · 反派', excluded: false, tokens: 200 },
  { id: 'short_term', label: '短期记忆', preview: '最近 5 条事件…', excluded: false, tokens: 150 },
  { id: 'rag', label: '长期 RAG 结果', preview: 'lore 片段 ×3', excluded: false, tokens: 300 },
])
function toggleExclude(id: string) {
  const b = contextBlocks.value.find(b => b.id === id)
  if (b) b.excluded = !b.excluded
}
const estimatedTokens = computed(() =>
  contextBlocks.value.filter(b => !b.excluded).reduce((s, b) => s + b.tokens, 0)
)

// ── Generation controls ───────────────────────────────────────────
const llmRoute = ref('llama3')
const lengthMode = ref('medium')
const temperature = ref(0.7)
const lengths = [
  { label: '短', value: 'short' },
  { label: '中', value: 'medium' },
  { label: '长', value: 'long' },
]
const skillQueue = ref<string[]>([])
function onSkillDrop(e: DragEvent) {
  const id = e.dataTransfer?.getData('skill-id')
  if (id && !skillQueue.value.includes(id)) skillQueue.value.push(id)
}

// ── Output ────────────────────────────────────────────────────────
const generating = ref(false)
const generatedText = ref('')
const errorMsg = ref('')
const annotations = ref<{ type: 'soft' | 'hard'; phrase: string }[]>([])
const inputTokens = ref(0)
const outputTokens = ref(0)

// ── Pipeline stepper ──────────────────────────────────────────────
const pipelineStages = ['规划', '撰写', '审核', '诊断']
const pipelineCurrent = computed(() => {
  if (!generating.value && generatedText.value) return 4
  if (generating.value) return 1
  return 0
})
const pipelineSteps = computed(() =>
  pipelineStages.map((label, i) => ({
    label,
    status: (i < pipelineCurrent.value
      ? 'done'
      : i === pipelineCurrent.value
        ? 'active'
        : 'pending') as 'done' | 'active' | 'pending',
  }))
)

async function generate() {
  if (generating.value) return
  if (!currentChapter.value || currentChapter.value < 1) {
    errorMsg.value = '请输入有效的章节号（最小为 1）'
    return
  }
  generating.value = true
  errorMsg.value = ''
  generatedText.value = ''

  // 将前端控件值映射到后端合法字段
  const strategyMap: Record<string, string> = {
    gpt4o: 'COST_OPTIMIZED',
    claude3: 'COST_OPTIMIZED',
    llama3: 'COST_OPTIMIZED',
  }
  const wordCountMap: Record<string, number> = {
    short: 1200,
    medium: 2000,
    long: 3000,
  }

  try {
    const res = await axios.post('/api/chapters/run', {
      chapter: currentChapter.value,
      volume: 1,
      target_summary: targetSummary.value || `第 ${currentChapter.value} 章`,
      word_count_target: wordCountMap[lengthMode.value] ?? 2000,
      strategy: strategyMap[llmRoute.value] ?? 'COST_OPTIMIZED',
      project_id: projectId.value,
      skill_names: skillQueue.value,
    })
    generatedText.value = res.data.text ?? ''
    inputTokens.value = 0
    outputTokens.value = res.data.word_count ?? 0
    loadDiagnostics()
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
      ?.response?.data?.detail ?? (e as { message?: string })?.message ?? '生成失败'
    errorMsg.value = msg
    diagnostics.value = [{
      type: 'info',
      title: 'API 不可用',
      description: '后端未运行或参数错误：' + msg,
    }]
  } finally {
    generating.value = false
  }
}

async function planOnly() {
  generating.value = true
  errorMsg.value = ''
  try {
    const res = await axios.post('/api/chapters/plan', {
      chapter: currentChapter.value,
      volume: 1,
      target_summary: targetSummary.value || `第 ${currentChapter.value} 章`,
      project_id: projectId.value,
    })
    generatedText.value = JSON.stringify(res.data, null, 2)
  } catch (e: unknown) {
    const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
      ?.response?.data?.detail ?? (e as { message?: string })?.message ?? '规划失败'
    errorMsg.value = msg
  } finally {
    generating.value = false
  }
}

function copyOutput() {
  navigator.clipboard.writeText(generatedText.value)
}
function clearOutput() {
  generatedText.value = ''
  annotations.value = []
  diagnostics.value = []
}

// ── Diagnostics ───────────────────────────────────────────────────
interface Diag { type: 'warning' | 'pass' | 'info'; title: string; description: string }
const diagnostics = ref<Diag[]>([])

function diagIcon(t: string) {
  return t === 'warning' ? '[!]' : t === 'pass' ? '[✓]' : '[i]'
}
function ignoreDiag(i: number) { diagnostics.value.splice(i, 1) }

async function loadDiagnostics() {
  diagnostics.value = []
  try {
    const res = await axios.post('/api/chapters/check', {
      text: generatedText.value,
      chapter: 1,
    })
    const issues: Array<{ severity: string; description: string; suggestion: string }> =
      res.data?.issues ?? []
    diagnostics.value = issues.map(iss => ({
      type: iss.severity === 'hard' ? 'warning' : 'info',
      title: iss.severity === 'hard' ? '严重冲突' : '提示',
      description: iss.description + (iss.suggestion ? ' → ' + iss.suggestion : ''),
    }))
    if (issues.length === 0) {
      diagnostics.value.push({ type: 'pass', title: '通过', description: '无一致性问题' })
    }
    diagnostics.value.push({
      type: 'info',
      title: 'Token',
      description: `输入 ${inputTokens.value} / 输出 ${outputTokens.value}`,
    })
  } catch {
    diagnostics.value.push({ type: 'info', title: '诊断不可用', description: '无法获取诊断信息' })
  }
}

// ── DiffView ──────────────────────────────────────────────────────
const showDiff = ref(false)
const diffOriginal = ref('')
const diffModified = ref('')

function requestRewrite(_index: number) {
  diffOriginal.value = generatedText.value
  diffModified.value = generatedText.value + '\n\n[AI 改写建议将在此显示]'
  showDiff.value = true
}
function onDiffAccept(text: string) {
  generatedText.value = text
  showDiff.value = false
}

// ── HITL ──────────────────────────────────────────────────────────
interface HITLItem { id: string; preview: string }
const hitlItems = ref<HITLItem[]>([])

function approveHITL(id: string) {
  hitlItems.value = hitlItems.value.filter(h => h.id !== id)
}
function rejectHITL(id: string) {
  hitlItems.value = hitlItems.value.filter(h => h.id !== id)
}
</script>

<style scoped>
.scene-ide-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* Header */
.ide-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.ide-title { font-size: var(--text-h2); font-weight: var(--weight-h2); }
.ide-controls { display: flex; gap: var(--spacing-sm); align-items: center; }
.llm-select {
  background: var(--color-surface-l1);
  color: var(--color-text-primary);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  padding: 4px 8px;
  font-size: var(--text-caption);
}
.chapter-input {
  width: 64px;
  background: var(--color-surface-l1);
  border: 1px solid #444;
  color: var(--color-text-primary);
  border-radius: var(--radius-btn);
  padding: 4px 8px;
  font-size: 13px;
}
.summary-input {
  width: 200px;
  background: var(--color-surface-l1);
  border: 1px solid #444;
  color: var(--color-text-primary);
  border-radius: var(--radius-btn);
  padding: 4px 8px;
  font-size: 13px;
}

/* Columns */
.ide-columns {
  display: grid;
  grid-template-columns: 25% 50% 25%;
  flex: 1;
  overflow: hidden;
}
.ide-col { display: flex; flex-direction: column; overflow: hidden; }
.ide-left { border-right: 1px solid var(--color-surface-l2); overflow-y: auto; }
.ide-center { border-right: 1px solid var(--color-surface-l2); }
.ide-right { overflow-y: auto; }

.col-header {
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--color-text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}

/* Context blocks */
.ctx-block {
  margin: var(--spacing-xs) var(--spacing-sm);
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm);
  transition: opacity 200ms;
}
.ctx-block.excluded { opacity: 0.35; }
.ctx-block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.ctx-block-title { font-size: 13px; font-weight: 500; }
.exclude-btn {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--text-caption);
  padding: 2px 4px;
  border-radius: 3px;
}
.exclude-btn:hover { color: var(--color-hitl); }
.ctx-block-body { font-size: var(--text-caption); color: var(--color-text-secondary); }
.token-estimate {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  margin-top: auto;
  border-top: 1px solid var(--color-surface-l2);
}

/* Generation controls */
.gen-controls {
  display: flex;
  gap: var(--spacing-md);
  align-items: center;
  flex-wrap: wrap;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  flex-shrink: 0;
}
.control-group { display: flex; align-items: center; gap: var(--spacing-sm); }
.control-group label { font-size: var(--text-caption); color: var(--color-text-secondary); }
.btn-group { display: flex; gap: 2px; }
.len-btn {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  color: var(--color-text-primary);
  padding: 2px 10px;
  font-size: var(--text-caption);
  cursor: pointer;
  border-radius: var(--radius-btn);
  transition: background 150ms;
}
.len-btn.active { background: var(--color-ai-active); color: var(--color-base); border-color: var(--color-ai-active); }
.skill-queue {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  min-height: 28px;
  min-width: 120px;
  background: var(--color-surface-l1);
  border: 2px dashed var(--color-surface-l2);
  border-radius: var(--radius-btn);
  padding: 4px 8px;
  align-items: center;
  transition: border-color 150ms;
}
.skill-queue:hover { border-color: var(--color-ai-active); }
.queue-hint { font-size: var(--text-caption); color: var(--color-text-secondary); }

/* Output area */
.output-area {
  flex: 1;
  overflow-y: auto;
  position: relative;
  border: 2px solid transparent;
  margin: var(--spacing-sm);
  border-radius: var(--radius-card);
  padding: var(--spacing-md);
  background: var(--color-surface-l1);
  transition: border-color 400ms;
}
.border-generating { border-color: var(--color-ai-active); animation: breathing 2s ease-in-out infinite; }
.border-done { border-color: var(--color-success); }
.output-tools {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
}
.tool-btn {
  background: var(--color-surface-l2);
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 4px;
  width: 28px;
  height: 28px;
  font-size: 14px;
}
.tool-btn:hover { color: var(--color-text-primary); }
.output-text {
  font-family: 'Noto Serif SC', 'Georgia', serif;
  font-size: var(--text-body);
  line-height: var(--lh-body);
  max-width: var(--max-line-chars);
  white-space: pre-wrap;
}
.error-card {
  padding: var(--spacing-md);
  background: color-mix(in srgb, var(--color-error) 15%, transparent);
  border-radius: var(--radius-card);
  color: var(--color-error);
  font-size: 14px;
}
.annotation-legend {
  margin-top: var(--spacing-md);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}
.annotation-soft { text-decoration: underline; text-decoration-color: var(--color-warning); }
.annotation-hard { text-decoration: underline wavy var(--color-hitl); }

/* Diagnostics */
.diag-empty { padding: var(--spacing-md); font-size: var(--text-caption); color: var(--color-text-secondary); text-align: center; }
.diag-card {
  display: flex;
  gap: var(--spacing-sm);
  margin: var(--spacing-xs) var(--spacing-sm);
  padding: var(--spacing-sm);
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  border-left: 3px solid transparent;
}
.diag-warning { border-left-color: var(--color-hitl); }
.diag-pass { border-left-color: var(--color-success); }
.diag-info { border-left-color: var(--color-text-secondary); }
.diag-icon { font-size: var(--text-caption); font-family: monospace; flex-shrink: 0; padding-top: 2px; }
.diag-title { font-size: 13px; font-weight: 600; margin-bottom: 2px; }
.diag-desc { font-size: var(--text-caption); color: var(--color-text-secondary); }
.diag-actions { display: flex; gap: var(--spacing-sm); margin-top: var(--spacing-xs); }
.diag-btn {
  font-size: var(--text-caption);
  background: var(--color-surface-l2);
  border: none;
  color: var(--color-text-primary);
  border-radius: var(--radius-btn);
  padding: 3px 10px;
  cursor: pointer;
}
.diag-btn:hover { background: var(--color-ai-active); color: var(--color-base); }
.diag-btn.ghost { background: none; border: 1px solid var(--color-surface-l2); }
.cost-info {
  display: flex;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  margin-top: auto;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
