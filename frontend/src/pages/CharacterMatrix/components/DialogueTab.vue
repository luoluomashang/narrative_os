<template>
  <div class="dialogue-tab">
    <!-- VoiceFingerprint editing -->
    <div class="section-title">口吻指纹 (VoiceFingerprint)</div>
    <el-form label-position="top" size="small">
      <el-form-item label="高压被逼时的说话风格">
        <el-input v-model="localVF.under_pressure" placeholder="如：语速加快，带攻击性" />
      </el-form-item>
      <el-form-item label="撒谎时的话语特征">
        <el-input v-model="localVF.when_lying" placeholder="如：会主动转移话题" />
      </el-form-item>
      <el-form-item label="回避话题时的习惯表达">
        <el-input v-model="localVF.deflection" placeholder="如：不回答，反问对方" />
      </el-form-item>
      <el-form-item label="情绪爆发时的模式">
        <el-input v-model="localVF.emotional_peak" placeholder="如：沉默 → 爆发，句子简短有力" />
      </el-form-item>
      <el-form-item label="对话长度倾向">
        <el-select v-model="localVF.default_length" style="width: 120px">
          <el-option label="短" value="short" />
          <el-option label="中" value="medium" />
          <el-option label="长" value="long" />
        </el-select>
      </el-form-item>
    </el-form>

    <!-- Speech style + catchphrases -->
    <div class="section-title" style="margin-top: 12px">语言风格与口头禅</div>
    <el-form label-position="top" size="small">
      <el-form-item label="语言风格">
        <el-input v-model="localSpeechStyle" type="textarea" :rows="2" placeholder="简洁直接，不废话，偶尔用反问" />
      </el-form-item>
      <el-form-item label="口头禅（每行一条）">
        <el-input v-model="catchphrasesText" type="textarea" :rows="2" placeholder="如：绝不认输&#10;有趣" />
      </el-form-item>
    </el-form>

    <!-- Dialogue examples list -->
    <div class="section-title" style="margin-top: 12px">对话示例 (Few-Shot)</div>
    <div v-for="(ex, idx) in localExamples" :key="idx" class="example-item">
      <div class="example-row">
        <el-input v-model="ex.context" placeholder="情境" size="small" style="flex:1" />
        <button class="example-del" @click="removeExample(idx)">×</button>
      </div>
      <el-input v-model="ex.dialogue" type="textarea" :rows="2" placeholder="角色说的话" size="small" />
      <el-input v-model="ex.action" placeholder="伴随动作（可选）" size="small" style="margin-top:4px" />
    </div>
    <div v-if="localExamples.length >= 10" class="limit-hint">已达上限 10 条</div>
    <el-button v-else size="small" style="margin-top: 6px" @click="addExample">+ 添加示例</el-button>

    <!-- Voice test panel -->
    <div class="voice-test-panel">
      <div class="voice-test-title">🎭 口吻试戏</div>
      <div class="voice-test-desc">输入一个场景，验证 AI 是否能以该角色口吻回应</div>
      <div class="voice-test-row">
        <el-input v-model="testScenario" placeholder="如：被敌人包围时 / 遇到久违的故人" size="small" />
        <el-button size="small" type="primary" :loading="testLoading" @click="runTest">试戏</el-button>
      </div>
      <div v-if="testDialogue" class="voice-test-result">
        <div class="test-dialogue">「{{ testDialogue }}」</div>
        <el-button size="small" @click="saveAsExample">保存为示例</el-button>
      </div>
    </div>

    <!-- Save button -->
    <div class="dialogue-actions">
      <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { projects } from '@/api/projects'
import type { CharacterDetail, DialogueExample } from '@/types/api'

const props = defineProps<{
  model: CharacterDetail
  loading: boolean
  projectId: string
}>()

const emit = defineEmits<{
  (e: 'save', data: Partial<CharacterDetail>): void
}>()

type LocalVoiceFingerprint = {
  under_pressure: string
  when_lying: string
  deflection: string
  emotional_peak: string
  default_length: string
}

const localVF = ref<LocalVoiceFingerprint>({
  under_pressure: '',
  when_lying: '',
  deflection: '',
  emotional_peak: '',
  default_length: 'medium',
})
const localSpeechStyle = ref('')
const catchphrasesText = ref('')
const localExamples = ref<DialogueExample[]>([])

const testScenario = ref('')
const testLoading = ref(false)
const testDialogue = ref('')

function normalizeVoiceFingerprint(value?: {
  under_pressure?: string
  when_lying?: string
  deflection?: string
  emotional_peak?: string
  default_length?: string
}): {
  under_pressure: string
  when_lying: string
  deflection: string
  emotional_peak: string
  default_length: string
} {
  const defaultLength = value?.default_length
  const normalizedDefaultLength = defaultLength === 'short' || defaultLength === 'medium' || defaultLength === 'long'
    ? defaultLength
    : 'medium'
  return {
    under_pressure: value?.under_pressure ?? '',
    when_lying: value?.when_lying ?? '',
    deflection: value?.deflection ?? '',
    emotional_peak: value?.emotional_peak ?? '',
    default_length: normalizedDefaultLength,
  }
}

watch(() => props.model, (m) => {
  if (m) {
    localVF.value = normalizeVoiceFingerprint(m.voice_fingerprint)
    localSpeechStyle.value = m.speech_style ?? ''
    catchphrasesText.value = (m.catchphrases ?? []).join('\n')
    localExamples.value = (m.dialogue_examples ?? []).map((e: DialogueExample) => ({ ...e }))
  }
}, { immediate: true })

function addExample() {
  if (localExamples.value.length >= 10) return
  localExamples.value.push({ context: '', dialogue: '', action: '' })
}

function removeExample(idx: number) {
  localExamples.value.splice(idx, 1)
}

async function runTest() {
  if (!testScenario.value.trim()) return
  testLoading.value = true
  testDialogue.value = ''
  try {
    const res = await projects.testVoice(props.projectId, props.model.name, testScenario.value)
    testDialogue.value = res.data.dialogue
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.detail ?? '试戏失败')
  } finally {
    testLoading.value = false
  }
}

function saveAsExample() {
  if (!testDialogue.value || localExamples.value.length >= 10) return
  localExamples.value.push({
    context: testScenario.value,
    dialogue: testDialogue.value,
    action: '',
  })
  ElMessage.success('已添加到对话示例')
}

function handleSave() {
  const catchphrases = catchphrasesText.value.split('\n').map(s => s.trim()).filter(Boolean)
  emit('save', {
    voice_fingerprint: normalizeVoiceFingerprint(localVF.value),
    speech_style: localSpeechStyle.value,
    catchphrases,
    dialogue_examples: localExamples.value.filter((e) => e.dialogue.trim()),
  })
}
</script>

<style scoped>
.dialogue-tab { padding: 4px 0; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.example-item {
  padding: 8px 10px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  margin-bottom: 6px;
}
.example-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}
.example-del {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
}
.example-del:hover { color: var(--color-danger); }
.limit-hint {
  color: var(--color-text-secondary);
  font-size: 12px;
  margin-top: 4px;
}
.voice-test-panel {
  margin-top: 20px;
  padding: 14px;
  border-top: 2px solid var(--color-surface-l2);
  background: color-mix(in srgb, var(--color-accent) 5%, transparent);
  border-radius: var(--radius-btn);
}
.voice-test-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
}
.voice-test-desc {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
}
.voice-test-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.voice-test-result {
  margin-top: 10px;
}
.test-dialogue {
  font-size: 14px;
  color: var(--color-text-primary);
  padding: 10px 14px;
  background: var(--color-accent-soft);
  border-radius: var(--radius-btn);
  border-left: 3px solid var(--color-accent);
  margin-bottom: 8px;
  line-height: 1.6;
}
.dialogue-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
