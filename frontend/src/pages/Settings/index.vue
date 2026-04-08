<template>
  <div class="settings-page">
    <h2 class="settings-title">系统设置</h2>

    <el-tabs v-model="activeTab" class="settings-tabs">

      <!-- ── Global Settings ──────────────────────── -->
      <el-tab-pane label="全局设置" name="global">

        <!-- Agent behavior -->
        <el-card class="settings-card" header="Agent 行为">
          <div class="setting-row">
            <label class="setting-label">每章 Token 预算</label>
            <el-input-number v-model="agentCfg.perChapterBudget" :min="1000" :max="200000" :step="1000" />
          </div>
          <div class="setting-row">
            <label class="setting-label">最大重写次数</label>
            <el-select v-model="agentCfg.maxRetries" style="width: 120px">
              <el-option v-for="n in [1,2,3,5,10]" :key="n" :label="`${n} 次`" :value="n" />
            </el-select>
          </div>
          <div class="setting-row">
            <label class="setting-label">自动降级模型</label>
            <el-switch v-model="agentCfg.autoDowngrade" />
            <span class="setting-hint">超限时自动切换至低成本模型</span>
          </div>
          <div class="setting-actions">
            <el-button type="primary" :loading="savingAgent" @click="saveAgentConfig">保存 Agent 配置</el-button>
          </div>
        </el-card>

        <!-- LLM Provider Config -->
        <el-card class="settings-card" header="LLM 提供商配置">

          <!-- Provider status badges -->
          <div class="provider-status-row">
            <el-tag
              v-for="(status, name) in providerStatus"
              :key="name"
              :type="status.available ? 'success' : 'info'"
              size="small"
              class="provider-badge"
            >
              {{ PROVIDER_LABELS[name] ?? name }}
            </el-tag>
          </div>

          <!-- Provider selector -->
          <el-radio-group v-model="selectedProvider" class="provider-radio-group">
            <el-radio-button v-for="p in PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</el-radio-button>
          </el-radio-group>

          <!-- OpenAI -->
          <div v-if="selectedProvider === 'openai'" class="provider-fields">
            <div class="setting-row">
              <label class="setting-label">API Key</label>
              <el-input
                v-model="form.openai_api_key"
                type="password"
                show-password
                placeholder="sk-..."
                autocomplete="off"
                class="setting-input-wide"
              />
            </div>
          </div>

          <!-- Anthropic -->
          <div v-else-if="selectedProvider === 'anthropic'" class="provider-fields">
            <div class="setting-row">
              <label class="setting-label">API Key</label>
              <el-input
                v-model="form.anthropic_api_key"
                type="password"
                show-password
                placeholder="sk-ant-..."
                autocomplete="off"
                class="setting-input-wide"
              />
            </div>
          </div>

          <!-- DeepSeek -->
          <div v-else-if="selectedProvider === 'deepseek'" class="provider-fields">
            <div class="setting-row">
              <label class="setting-label">API Key</label>
              <el-input
                v-model="form.deepseek_api_key"
                type="password"
                show-password
                placeholder="sk-..."
                autocomplete="off"
                class="setting-input-wide"
              />
            </div>
          </div>

          <!-- Ollama -->
          <div v-else-if="selectedProvider === 'ollama'" class="provider-fields">
            <div class="setting-row">
              <label class="setting-label">Base URL</label>
              <el-input
                v-model="form.ollama_base_url"
                placeholder="http://localhost:11434"
                class="setting-input-wide"
              />
            </div>
          </div>

          <!-- Custom -->
          <div v-else-if="selectedProvider === 'custom'" class="provider-fields">
            <div class="setting-row">
              <label class="setting-label">Base URL</label>
              <el-input v-model="form.custom_llm_base_url" placeholder="http://localhost:8080/v1" class="setting-input-wide" />
            </div>
            <div class="setting-row">
              <label class="setting-label">API Key (可选)</label>
              <el-input v-model="form.custom_llm_api_key" type="password" show-password placeholder="留空则不带 Authorization" autocomplete="off" class="setting-input-wide" />
            </div>
            <div class="setting-row">
              <label class="setting-label">Small 模型名</label>
              <el-input v-model="form.custom_llm_model_small" placeholder="custom-small" class="setting-input-wide" />
            </div>
            <div class="setting-row">
              <label class="setting-label">Medium 模型名</label>
              <el-input v-model="form.custom_llm_model_medium" placeholder="custom-medium" class="setting-input-wide" />
            </div>
            <div class="setting-row">
              <label class="setting-label">Large 模型名</label>
              <el-input v-model="form.custom_llm_model_large" placeholder="custom-large" class="setting-input-wide" />
            </div>
          </div>

          <!-- Actions -->
          <div class="provider-actions">
            <el-button :loading="testLoading" @click="testConnection">测试连接</el-button>
            <el-button type="primary" :loading="saveLoading" @click="saveSettings">保存配置</el-button>
          </div>

          <!-- Test result -->
          <el-alert
            v-if="testResult"
            :title="testResult.success
              ? `✓ 连接成功 — ${testResult.model_used} (${testResult.latency_ms}ms)`
              : `✗ 连接失败：${testResult.error}`"
            :type="testResult.success ? 'success' : 'error'"
            show-icon
            :closable="false"
            style="margin-top: 12px"
          />
          <el-alert
            v-if="saveMsg"
            :title="saveMsg"
            type="success"
            show-icon
            :closable="false"
            style="margin-top: 12px"
          />

        </el-card>
      </el-tab-pane>

      <!-- ── Project Settings (only in project context) ── -->
      <el-tab-pane v-if="projectId" label="项目设置" name="project">
        <el-card class="settings-card" header="生成参数默认值">
          <div class="setting-row">
            <label class="setting-label">章节长度 (字)</label>
            <el-input-number v-model="projectCfg.chapterLength" :min="500" :max="10000" :step="100" />
          </div>
          <div class="setting-row">
            <label class="setting-label">温度 (Temperature)</label>
            <el-slider v-model="projectCfg.temperature" :min="0" :max="2" :step="0.05" style="flex: 1; margin: 0 16px" />
            <span style="min-width: 36px; text-align: right; font-size: 13px">{{ projectCfg.temperature.toFixed(2) }}</span>
          </div>
        </el-card>

        <el-card class="settings-card" header="Prompt 覆盖">
          <el-input
            v-model="projectCfg.systemPrompt"
            type="textarea"
            :rows="6"
            placeholder="可选：覆盖全局 System Prompt（留空则使用全局默认）"
          />
        </el-card>

        <div class="setting-actions">
          <el-button type="primary" :loading="savingProject" @click="saveProjectConfig">保存项目设置</el-button>
        </div>
      </el-tab-pane>

    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useSettingsStore } from '@/stores/settingsStore'
import { ElMessage } from 'element-plus'
import type { LLMSettingsResponse, LLMTestResult, LLMProviderName } from '@/types/api'

const route = useRoute()
const settingsStore = useSettingsStore()
const projectId = computed(() => (route.params.id as string) || '')

const activeTab = ref('global')

// ── Agent config (sourced from settingsStore.globalSettings) ──────
const agentCfg = ref({
  perChapterBudget: 8000,
  maxRetries: 2,
  autoDowngrade: true,
})
const savingAgent = ref(false)

async function loadAgentConfig() {
  await settingsStore.loadGlobal()
  const g = settingsStore.globalSettings
  if (typeof g.per_chapter_budget === 'number') agentCfg.value.perChapterBudget = g.per_chapter_budget
  if (typeof g.max_retries === 'number') agentCfg.value.maxRetries = g.max_retries
  if (typeof g.auto_downgrade === 'boolean') agentCfg.value.autoDowngrade = g.auto_downgrade
}

async function saveAgentConfig() {
  savingAgent.value = true
  try {
    await settingsStore.updateGlobal({
      per_chapter_budget: agentCfg.value.perChapterBudget,
      max_retries: agentCfg.value.maxRetries,
      auto_downgrade: agentCfg.value.autoDowngrade,
    })
    ElMessage.success('Agent 配置已保存')
  } catch {
    ElMessage.error('保存失败，请检查后端连接')
  } finally {
    savingAgent.value = false
  }
}

// ── LLM Provider Config ───────────────────────────────────────────
const PROVIDERS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'deepseek', label: 'DeepSeek' },
  { value: 'ollama', label: 'Ollama (本地)' },
  { value: 'custom', label: '自定义' },
] as const

const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI', anthropic: 'Anthropic', ollama: 'Ollama',
  deepseek: 'DeepSeek', custom: 'Custom',
}

const selectedProvider = ref<LLMProviderName>('openai')
const providerStatus = ref<LLMSettingsResponse['providers']>({} as LLMSettingsResponse['providers'])
const form = ref({
  openai_api_key: '',
  anthropic_api_key: '',
  ollama_base_url: 'http://localhost:11434',
  deepseek_api_key: '',
  custom_llm_base_url: 'http://localhost:8080/v1',
  custom_llm_api_key: '',
  custom_llm_model_small: 'custom-small',
  custom_llm_model_medium: 'custom-medium',
  custom_llm_model_large: 'custom-large',
})

const testLoading = ref(false)
const saveLoading = ref(false)
const testResult = ref<LLMTestResult | null>(null)
const saveMsg = ref('')

async function loadSettings() {
  try {
    const res = await axios.get<LLMSettingsResponse>('/api/settings/llm')
    providerStatus.value = res.data.providers
    const cfg = res.data.current_config
    form.value.ollama_base_url = cfg.ollama_base_url || form.value.ollama_base_url
    form.value.custom_llm_base_url = cfg.custom_llm_base_url || form.value.custom_llm_base_url
    form.value.custom_llm_model_small = cfg.custom_llm_model_small || form.value.custom_llm_model_small
    form.value.custom_llm_model_medium = cfg.custom_llm_model_medium || form.value.custom_llm_model_medium
    form.value.custom_llm_model_large = cfg.custom_llm_model_large || form.value.custom_llm_model_large
  } catch {
    ElMessage.warning('无法加载 LLM 配置，后端可能未运行')
  }
}

async function testConnection() {
  testResult.value = null
  testLoading.value = true
  try {
    const res = await axios.post<LLMTestResult>('/api/settings/llm/test',
      { provider: selectedProvider.value })
    testResult.value = res.data
  } catch (e: any) {
    testResult.value = { success: false, latency_ms: 0, error: e?.message ?? '请求失败' }
  } finally {
    testLoading.value = false
  }
}

async function saveSettings() {
  saveMsg.value = ''
  saveLoading.value = true
  const payload: Record<string, string> = {}
  const p = selectedProvider.value
  if (p === 'openai' && form.value.openai_api_key) payload.openai_api_key = form.value.openai_api_key
  if (p === 'anthropic' && form.value.anthropic_api_key) payload.anthropic_api_key = form.value.anthropic_api_key
  if (p === 'deepseek' && form.value.deepseek_api_key) payload.deepseek_api_key = form.value.deepseek_api_key
  if (p === 'ollama') payload.ollama_base_url = form.value.ollama_base_url
  if (p === 'custom') {
    payload.custom_llm_base_url = form.value.custom_llm_base_url
    if (form.value.custom_llm_api_key) payload.custom_llm_api_key = form.value.custom_llm_api_key
    payload.custom_llm_model_small = form.value.custom_llm_model_small
    payload.custom_llm_model_medium = form.value.custom_llm_model_medium
    payload.custom_llm_model_large = form.value.custom_llm_model_large
  }
  try {
    await axios.put('/api/settings/llm', payload)
    saveMsg.value = '✓ 配置已保存并写入 .narrative_os.env'
    setTimeout(() => { saveMsg.value = '' }, 4000)
    await loadSettings()
  } catch (e: any) {
    saveMsg.value = '✗ 保存失败：' + (e?.response?.data?.detail ?? e?.message)
  } finally {
    saveLoading.value = false
  }
}

// ── Project Settings ──────────────────────────────────────────────
const projectCfg = ref({
  chapterLength: 2000,
  temperature: 0.7,
  systemPrompt: '',
})
const savingProject = ref(false)

async function loadProjectConfig() {
  if (!projectId.value) return
  await settingsStore.loadProjectSettings(projectId.value)
  const s = settingsStore.projectSettings
  if (typeof s.chapter_length === 'number') projectCfg.value.chapterLength = s.chapter_length
  if (typeof s.temperature === 'number') projectCfg.value.temperature = s.temperature
  if (typeof s.system_prompt === 'string') projectCfg.value.systemPrompt = s.system_prompt
}

async function saveProjectConfig() {
  if (!projectId.value) return
  savingProject.value = true
  try {
    await settingsStore.updateProjectSettings(projectId.value, {
      chapter_length: projectCfg.value.chapterLength,
      temperature: projectCfg.value.temperature,
      system_prompt: projectCfg.value.systemPrompt,
    })
    ElMessage.success('项目设置已保存')
  } catch {
    ElMessage.error('保存失败，请检查后端连接')
  } finally {
    savingProject.value = false
  }
}

onMounted(async () => {
  await Promise.all([loadAgentConfig(), loadSettings()])
  if (projectId.value) await loadProjectConfig()
})
</script>

<style scoped>
.settings-page {
  max-width: 760px;
  padding: var(--spacing-xl) var(--spacing-lg);
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}
.settings-title {
  font-size: var(--text-h1);
  font-weight: var(--weight-h1);
  margin-bottom: var(--spacing-md);
}
.settings-tabs { width: 100%; }
.settings-card { margin-bottom: var(--spacing-lg); }
.setting-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
.setting-row:last-child { border-bottom: none; }
.setting-label { font-size: 14px; min-width: 160px; flex-shrink: 0; }
.setting-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.setting-input-wide { flex: 1; }
.provider-status-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.provider-radio-group { margin-bottom: 16px; }
.provider-fields { margin: 12px 0; }
.provider-actions { display: flex; gap: var(--spacing-sm); margin-top: 16px; }
.setting-actions { display: flex; justify-content: flex-end; margin-top: 12px; }
</style>
