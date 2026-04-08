<template>
  <div class="style-page">
    <div class="style-header">
      <span class="style-title">风格控制台</span>
      <el-select v-model="activePreset" placeholder="— 选择预设 —" style="width: 180px" @change="applyPreset">
        <el-option v-for="p in presets" :key="p.name" :label="p.name" :value="p.name" />
      </el-select>
    </div>

    <!-- Preset quick buttons -->
    <el-radio-group v-model="activePreset" @change="applyPreset">
      <el-radio-button v-for="p in quickPresets" :key="p.name" :value="p.name">{{ p.label }}</el-radio-button>
    </el-radio-group>

    <!-- 5 style sliders -->
    <div class="sliders-grid">
      <div v-for="dim in styleDims" :key="dim.key" class="slider-row">
        <div class="slider-meta">
          <span class="slider-name">{{ dim.label }}</span>
          <span class="slider-val">{{ dim.value }}</span>
        </div>
        <el-slider
          v-model="dim.value"
          :min="0"
          :max="100"
          :step="1"
          style="flex: 1; margin: 0 8px"
          @change="schedulePreview"
        />
        <div class="slider-extremes">
          <span>{{ dim.low }}</span>
          <span>{{ dim.high }}</span>
        </div>
      </div>
    </div>

    <!-- Reference file drop zone -->
    <div
      class="style-drop-zone"
      :class="{ dragging: isDragging, error: dropError }"
      @dragover.prevent="isDragging = true"
      @dragleave="isDragging = false"
      @drop.prevent="onFileDrop"
    >
      <div v-if="extracting" class="drop-extracting">
        <NBreathingLight :size="10" color="var(--color-ai-active)" />
        <span>提取风格参数中…</span>
      </div>
      <span v-else-if="dropError" class="drop-error">{{ dropError }}</span>
      <span v-else>将 .txt 或 .md 文件拖入此处，自动提取风格参数</span>
    </div>

    <!-- Live preview -->
    <div class="preview-section">
      <div class="preview-header">
        <span>实时预览</span>
        <NButton variant="ghost" @click="refreshPreview">刷新预览</NButton>
      </div>
      <div class="preview-box">
        <NTypewriter v-if="previewText" :text="previewText" :speed="20" />
        <span v-else class="preview-empty">调整滑块后自动生成示例文本…</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import NButton from '@/components/common/NButton.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import NTypewriter from '@/components/common/NTypewriter.vue'
import axios from 'axios'

// ── Style dimensions ──────────────────────────────────────────────
interface StyleDim {
  key: string
  label: string
  value: number
  low: string
  high: string
}

const styleDims = reactive<StyleDim[]>([
  { key: 'adj_density', label: '形容词密度', value: 50, low: '朴素', high: '华丽' },
  { key: 'sentence_complexity', label: '句子复杂度', value: 50, low: '短句', high: '长句' },
  { key: 'dialogue_ratio', label: '对白比例', value: 50, low: '叙事', high: '对话' },
  { key: 'pov_depth', label: '视点深度', value: 50, low: '全知', high: '深度内聚' },
  { key: 'imagery_density', label: '意象密度', value: 50, low: '写实', high: '意象流' },
])

// ── Presets ───────────────────────────────────────────────────────
interface Preset { name: string; label?: string; params: Record<string, number> }
const presets = ref<Preset[]>([
  { name: '武侠·金庸', params: { adj_density: 60, sentence_complexity: 70, dialogue_ratio: 45, pov_depth: 55, imagery_density: 65 } },
  { name: '都市·硬派', params: { adj_density: 30, sentence_complexity: 40, dialogue_ratio: 55, pov_depth: 75, imagery_density: 30 } },
  { name: '奇幻·史诗', params: { adj_density: 75, sentence_complexity: 80, dialogue_ratio: 35, pov_depth: 50, imagery_density: 80 } },
  { name: '恐怖·压抑', params: { adj_density: 65, sentence_complexity: 60, dialogue_ratio: 25, pov_depth: 85, imagery_density: 70 } },
])

const quickPresets = reactive<Preset[]>([
  { name: '海明威·简洁', label: '海明威·简洁', params: { adj_density: 15, sentence_complexity: 20, dialogue_ratio: 60, pov_depth: 40, imagery_density: 20 } },
  { name: '吉布森·赛博', label: '吉布森·赛博', params: { adj_density: 80, sentence_complexity: 75, dialogue_ratio: 30, pov_depth: 90, imagery_density: 85 } },
  { name: '金庸·武侠', label: '金庸·武侠', params: { adj_density: 60, sentence_complexity: 70, dialogue_ratio: 45, pov_depth: 55, imagery_density: 65 } },
])

const activePreset = ref('')

async function loadPresets() {
  try {
    const res = await axios.get('/api/style/presets')
    if (Array.isArray(res.data)) {
      presets.value = res.data
      // Replace quickPresets with first 3 entries that have params
      const withParams = (res.data as Preset[]).filter(p => p.params && Object.keys(p.params).length > 0)
      if (withParams.length >= 3) {
        quickPresets.splice(0, quickPresets.length, ...withParams.slice(0, 3))
      }
    }
  } catch {
    // use defaults
  }
}
loadPresets()

function applyPresetParams(params: Record<string, number>) {
  styleDims.forEach(dim => {
    if (dim.key in params) dim.value = params[dim.key]
  })
  schedulePreview()
}
function applyPreset() {
  const allPresets = [...presets.value, ...quickPresets]
  const p = allPresets.find(p => p.name === activePreset.value)
  if (p) applyPresetParams(p.params)
}

// ── File drop ─────────────────────────────────────────────────────
const isDragging = ref(false)
const extracting = ref(false)
const dropError = ref('')

async function onFileDrop(e: DragEvent) {
  isDragging.value = false
  dropError.value = ''
  const file = e.dataTransfer?.files?.[0]
  if (!file) return

  if (!file.name.endsWith('.txt') && !file.name.endsWith('.md')) {
    dropError.value = '格式不支持，请拖入 .txt 或 .md 文件'
    setTimeout(() => { dropError.value = '' }, 3000)
    return
  }

  extracting.value = true
  try {
    const text = await file.text()
    const res = await axios.post('/api/style/extract', { text: text.slice(0, 5000) })
    const params: Record<string, number> = res.data?.params ?? {}
    // animate to new values
    for (const dim of styleDims) {
      if (dim.key in params) {
        const target = params[dim.key]
        const step = (target - dim.value) / 10
        let i = 0
        const interval = setInterval(() => {
          dim.value = Math.round(dim.value + step)
          if (++i >= 10) {
            dim.value = target
            clearInterval(interval)
          }
        }, 50)
      }
    }
  } catch {
    dropError.value = '提取失败（API 不可用）'
    setTimeout(() => { dropError.value = '' }, 3000)
  } finally {
    extracting.value = false
  }
}

// ── Live preview ──────────────────────────────────────────────────
const previewText = ref('')
let previewTimer: ReturnType<typeof setTimeout> | null = null

function schedulePreview() {
  if (previewTimer) clearTimeout(previewTimer)
  previewTimer = setTimeout(refreshPreview, 300)
}

function refreshPreview() {
  previewText.value = '当前风格参数设置：\n' +
    styleDims.map(d => `${d.label}：${d.value}%（${d.low} ←→ ${d.high}）`).join('\n')
}
</script>

<style scoped>
.style-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow-y: auto;
  padding: var(--spacing-md);
  gap: var(--spacing-md);
  box-sizing: border-box;
  max-width: 800px;
}
.style-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.style-title { font-size: var(--text-h2); font-weight: var(--weight-h2); }
.preset-select {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  padding: 4px 10px;
  font-size: 14px;
}

/* Quick preset buttons */
.preset-btns { display: flex; gap: var(--spacing-sm); flex-wrap: wrap; }
.preset-quick-btn {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  padding: 4px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background 150ms, border-color 150ms;
}
.preset-quick-btn:hover { border-color: var(--color-ai-active); }
.preset-quick-btn.active { background: color-mix(in srgb, var(--color-ai-active) 20%, transparent); border-color: var(--color-ai-active); }

/* Sliders */
.sliders-grid { display: flex; flex-direction: column; gap: var(--spacing-md); }
.slider-row {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  padding: var(--spacing-sm) var(--spacing-md);
}
.slider-meta {
  display: flex;
  justify-content: space-between;
  margin-bottom: 6px;
}
.slider-name { font-size: 14px; font-weight: 500; }
.slider-val { font-size: 13px; color: var(--color-ai-active); font-weight: 600; }
.slider-extremes {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
  margin-top: 4px;
}

/* Drop zone */
.style-drop-zone {
  min-height: 72px;
  border: 2px dashed var(--color-surface-l2);
  border-radius: var(--radius-card);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-sm);
  font-size: 14px;
  color: var(--color-text-secondary);
  transition: border-color 150ms, background 150ms;
  padding: var(--spacing-md);
}
.style-drop-zone.dragging { border-color: var(--color-ai-active); background: color-mix(in srgb, var(--color-ai-active) 5%, transparent); }
.style-drop-zone.error { border-color: var(--color-error); }
.drop-extracting { display: flex; align-items: center; gap: var(--spacing-sm); }
.drop-error { color: var(--color-error); }

/* Preview */
.preview-section {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  overflow: hidden;
}
.preview-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--spacing-sm) var(--spacing-md);
  border-bottom: 1px solid var(--color-surface-l2);
  font-size: 13px;
  font-weight: 500;
}
.preview-box {
  padding: var(--spacing-md);
  font-family: 'Noto Serif SC', 'Georgia', serif;
  font-size: var(--text-body);
  line-height: var(--lh-body);
  max-width: var(--max-line-chars);
  min-height: 100px;
}
.preview-empty { color: var(--color-text-secondary); font-style: italic; font-family: inherit; font-size: 14px; }
</style>
