<template>
  <div class="settings-page">
    <SystemPageHeader
      eyebrow="Settings"
      :title="projectId ? '项目设置' : '系统设置'"
      :description="projectId
        ? '统一管理当前项目的生成参数、Prompt 覆盖以及与全局模型配置的协同关系。'
        : '统一管理 Agent 行为、全局 LLM 提供商与默认创作参数。'
      "
    >
      <template #meta>
        <span class="settings-meta-pill">{{ projectId ? `项目 ${projectId}` : '全局配置' }}</span>
      </template>
    </SystemPageHeader>

    <SystemSection
      title="配置总览"
      description="先确认当前可用能力与项目覆盖范围，再进入抽屉修改低频配置。"
    >
      <div class="settings-overview-grid" :class="{ 'settings-overview-grid--project': projectId }">
        <SystemCard class="overview-card" tone="accent" title="Agent 策略概览" description="预算、重试和成本降级策略。">
          <template #actions>
            <SystemButton variant="primary" @click="agentDrawerOpen = true">编辑策略</SystemButton>
          </template>
          <div class="overview-metric-grid">
            <div v-for="item in agentSummaryItems" :key="item.label" class="overview-metric">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </SystemCard>

        <SystemCard class="overview-card" title="LLM 能力卡" description="当前提供商状态、可用连接数量与配置入口。">
          <template #actions>
            <SystemButton variant="primary" @click="providerDrawerOpen = true">编辑连接信息</SystemButton>
          </template>
          <div class="overview-metric-grid">
            <div v-for="item in providerOverviewItems" :key="item.label" class="overview-metric">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </SystemCard>

        <SystemCard
          v-if="projectId"
          class="overview-card"
          title="项目默认值"
          description="项目级生成参数与 Prompt 覆盖状态。"
        >
          <template #actions>
            <SystemButton variant="primary" @click="projectDrawerOpen = true">编辑项目设置</SystemButton>
          </template>
          <div class="overview-metric-grid">
            <div v-for="item in projectSummaryItems" :key="item.label" class="overview-metric">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection
      title="全局能力"
      description="Provider 配置收敛为能力卡，测试连接与保存配置分离，避免首屏堆叠大量表单。"
    >
      <div class="settings-capability-grid">
        <SystemCard class="settings-card" title="Agent 行为" description="控制每章预算、重试策略与成本降级兜底。">
          <div class="setting-summary-list">
            <div v-for="item in agentSummaryItems" :key="item.label" class="setting-summary-item">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>

          <template #actions>
            <SystemButton variant="primary" @click="agentDrawerOpen = true">编辑策略</SystemButton>
          </template>
        </SystemCard>

        <SystemCard class="settings-card" title="LLM 提供商配置" description="切换当前查看的提供商，查看可用状态，再进入抽屉维护连接参数。">
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

          <el-radio-group v-model="selectedProvider" class="provider-radio-group">
            <el-radio-button v-for="p in PROVIDERS" :key="p.value" :value="p.value">{{ p.label }}</el-radio-button>
          </el-radio-group>

          <div class="provider-summary-card">
            <div class="provider-summary-card__header">
              <div>
                <strong>{{ selectedProviderLabel }}</strong>
                <p>{{ selectedProviderDescription }}</p>
              </div>
              <span class="provider-state-pill" :class="{ available: currentProviderAvailable }">
                {{ currentProviderAvailable ? '可用' : '待配置' }}
              </span>
            </div>

            <div class="provider-summary-grid">
              <div v-for="item in providerSummaryItems" :key="item.label" class="provider-summary-item">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>

            <div class="provider-actions compact">
              <SystemButton :loading="testLoading" @click="testConnection">测试连接</SystemButton>
              <SystemButton variant="primary" @click="providerDrawerOpen = true">编辑连接信息</SystemButton>
            </div>
          </div>

          <el-alert
            v-if="testResult"
            :title="testResult.success
              ? `✓ 连接成功 — ${testResult.model_used} (${testResult.latency_ms}ms)`
              : `✗ 连接失败：${testResult.error}`"
            :type="testResult.success ? 'success' : 'error'"
            show-icon
            :closable="false"
            class="provider-inline-alert"
          />
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection
      v-if="projectId"
      title="项目覆盖"
      description="把项目级默认值保持为摘要态，仅在需要调整时展开抽屉。"
    >
      <SystemCard class="settings-card" title="项目默认值与 Prompt 覆盖" description="统一管理章节长度、温度与项目级 System Prompt。">
        <div class="setting-summary-list">
          <div v-for="item in projectSummaryItems" :key="item.label" class="setting-summary-item">
            <span>{{ item.label }}</span>
            <strong>{{ item.value }}</strong>
          </div>
        </div>

        <template #actions>
          <SystemButton variant="primary" @click="projectDrawerOpen = true">编辑项目设置</SystemButton>
        </template>
      </SystemCard>
    </SystemSection>

    <SystemDrawer
      v-model="agentDrawerOpen"
      title="Agent 行为配置"
      description="把预算、重试与降级策略集中在抽屉里编辑，避免首屏出现大面积表单。"
      size="420px"
    >
      <div class="setting-row">
        <label class="setting-label">每章 Token 预算</label>
        <el-input-number v-model="agentCfg.perChapterBudget" :min="1000" :max="200000" :step="1000" />
      </div>
      <div class="setting-row">
        <label class="setting-label">最大重写次数</label>
        <el-select v-model="agentCfg.maxRetries" style="width: 120px">
          <el-option v-for="n in [1, 2, 3, 5, 10]" :key="n" :label="`${n} 次`" :value="n" />
        </el-select>
      </div>
      <div class="setting-row">
        <label class="setting-label">自动降级模型</label>
        <el-switch v-model="agentCfg.autoDowngrade" />
        <span class="setting-hint">超限时自动切换至低成本模型</span>
      </div>

      <div class="setting-actions">
        <SystemButton variant="primary" :loading="savingAgent" @click="saveAgentConfig">保存 Agent 配置</SystemButton>
      </div>
    </SystemDrawer>

    <SystemDrawer
      v-model="providerDrawerOpen"
      :title="`${selectedProviderLabel} 连接配置`"
      description="把密钥、Base URL 和模型路由放入抽屉，仅在需要编辑时展开。"
      size="420px"
    >
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

      <div class="provider-actions">
        <SystemButton variant="primary" :loading="saveLoading" @click="saveSettings">保存配置</SystemButton>
      </div>

      <el-alert
        v-if="saveMsg"
        :title="saveMsg"
        :type="saveMsg.startsWith('✓') ? 'success' : 'error'"
        show-icon
        :closable="false"
        style="margin-top: 12px"
      />
    </SystemDrawer>

    <SystemDrawer
      v-if="projectId"
      v-model="projectDrawerOpen"
      title="项目设置"
      description="在抽屉里调整项目级默认生成参数和 Prompt 覆盖。"
      size="460px"
    >
      <div class="setting-row">
        <label class="setting-label">章节长度 (字)</label>
        <el-input-number v-model="projectCfg.chapterLength" :min="500" :max="10000" :step="100" />
      </div>
      <div class="setting-row">
        <label class="setting-label">温度 (Temperature)</label>
        <el-slider v-model="projectCfg.temperature" :min="0" :max="2" :step="0.05" class="setting-slider" />
        <span class="setting-value">{{ projectCfg.temperature.toFixed(2) }}</span>
      </div>
      <div class="setting-stack">
        <label class="setting-label setting-label--stack">Prompt 覆盖</label>
        <el-input
          v-model="projectCfg.systemPrompt"
          type="textarea"
          :rows="6"
          placeholder="可选：覆盖全局 System Prompt（留空则使用全局默认）"
        />
      </div>

      <div class="setting-actions">
        <SystemButton variant="primary" :loading="savingProject" @click="saveProjectConfig">保存项目设置</SystemButton>
      </div>
    </SystemDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import axios from 'axios'
import { useSettingsStore } from '@/stores/settingsStore'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import { ElMessage } from 'element-plus'
import type { LLMSettingsResponse, LLMTestResult, LLMProviderName } from '@/types/api'

const route = useRoute()
const settingsStore = useSettingsStore()
const projectId = computed(() => (route.params.id as string) || '')

// ── Agent config (sourced from settingsStore.globalSettings) ──────
const agentCfg = ref({
  perChapterBudget: 8000,
  maxRetries: 2,
  autoDowngrade: true,
})
const savingAgent = ref(false)
const agentDrawerOpen = ref(false)

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
const providerDrawerOpen = ref(false)

const selectedProviderLabel = computed(
  () => PROVIDERS.find((provider) => provider.value === selectedProvider.value)?.label ?? selectedProvider.value,
)

const selectedProviderDescription = computed(() => {
  if (selectedProvider.value === 'ollama') {
    return '本地模型服务，优先维护 Base URL 与可达性。'
  }
  if (selectedProvider.value === 'custom') {
    return '适用于兼容 OpenAI 协议的自定义模型网关。'
  }
  return '云端模型提供商，通常只需维护 API Key。'
})

const currentProviderAvailable = computed(
  () => Boolean(providerStatus.value?.[selectedProvider.value]?.available),
)

const availableProviderCount = computed(
  () => Object.values(providerStatus.value ?? {}).filter((status) => status?.available).length,
)

const agentSummaryItems = computed(() => [
  { label: '预算', value: `${agentCfg.value.perChapterBudget.toLocaleString()} tokens / 章` },
  { label: '重试上限', value: `${agentCfg.value.maxRetries} 次` },
  { label: '成本策略', value: agentCfg.value.autoDowngrade ? '自动降级' : '固定模型' },
])

const providerOverviewItems = computed(() => [
  { label: '当前提供商', value: selectedProviderLabel.value },
  { label: '可用连接', value: `${availableProviderCount.value} / ${PROVIDERS.length}` },
  { label: '编辑方式', value: '抽屉配置' },
])

const providerSummaryItems = computed(() => {
  if (selectedProvider.value === 'ollama') {
    return [
      { label: '连接方式', value: 'Base URL' },
      { label: '目标地址', value: form.value.ollama_base_url || '未设置' },
    ]
  }
  if (selectedProvider.value === 'custom') {
    return [
      { label: '连接方式', value: '自定义网关' },
      { label: '目标地址', value: form.value.custom_llm_base_url || '未设置' },
      { label: '主模型', value: form.value.custom_llm_model_medium || '未设置' },
    ]
  }
  return [
    { label: '连接方式', value: 'API Key' },
    { label: '当前状态', value: currentProviderAvailable.value ? '已配置' : '未配置' },
  ]
})

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
const projectDrawerOpen = ref(false)

const projectSummaryItems = computed(() => [
  { label: '章节长度', value: `${projectCfg.value.chapterLength} 字` },
  { label: '温度', value: projectCfg.value.temperature.toFixed(2) },
  { label: 'Prompt 覆盖', value: projectCfg.value.systemPrompt.trim() ? '已覆盖' : '继承全局' },
])

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
  max-width: 980px;
  padding: var(--spacing-xl) var(--spacing-lg);
  display: grid;
  gap: var(--spacing-lg);
  overflow-y: auto;
  height: 100%;
  box-sizing: border-box;
}

.settings-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.settings-overview-grid,
.settings-capability-grid {
  display: grid;
  gap: var(--spacing-md);
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.settings-overview-grid--project {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.overview-card,
.settings-card {
  min-width: 0;
}

.overview-metric-grid,
.setting-summary-list {
  display: grid;
  gap: 10px;
}

.overview-metric-grid {
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
}

.overview-metric,
.setting-summary-item {
  display: grid;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: color-mix(in srgb, var(--color-surface-2) 84%, transparent);
}

.overview-metric span,
.setting-summary-item span {
  color: var(--color-text-3);
  font-size: 12px;
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.overview-metric strong,
.setting-summary-item strong {
  color: var(--color-text-1);
  font-size: 0.98rem;
}

.setting-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.setting-row:last-child { border-bottom: none; }
.setting-label { font-size: 14px; min-width: 160px; flex-shrink: 0; }
.setting-label--stack { min-width: 0; }
.setting-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.setting-input-wide { flex: 1; }
.setting-slider { flex: 1; margin: 0 16px; }
.setting-value { min-width: 36px; text-align: right; font-size: 13px; }
.setting-stack {
  display: grid;
  gap: 10px;
  margin-top: 12px;
}
.provider-status-row { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
.provider-radio-group { margin-bottom: 16px; }
.provider-fields { margin: 12px 0; }
.provider-actions { display: flex; gap: var(--spacing-sm); margin-top: 16px; }
.setting-actions { display: flex; justify-content: flex-end; margin-top: 12px; }
.provider-actions.compact { margin-top: 0; }
.provider-inline-alert { margin-top: 12px; }

.provider-summary-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 16px;
  padding: 16px;
  display: grid;
  gap: 14px;
  background: color-mix(in srgb, var(--color-surface-2) 76%, transparent);
}

.provider-summary-card__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.provider-summary-card__header p {
  margin: 6px 0 0;
  color: var(--color-text-3);
  font-size: 13px;
  line-height: 1.6;
}

.provider-state-pill {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-size: 12px;
  font-weight: 700;
}

.provider-state-pill.available {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.provider-summary-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
}

.provider-summary-item {
  display: grid;
  gap: 6px;
}

.provider-summary-item span {
  color: var(--color-text-3);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

@media (max-width: 1024px) {
  .settings-overview-grid,
  .settings-overview-grid--project,
  .settings-capability-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .settings-page {
    padding: var(--spacing-lg) var(--spacing-md);
  }

  .setting-row {
    flex-direction: column;
    align-items: stretch;
  }

  .setting-label {
    min-width: 0;
  }

  .provider-actions,
  .setting-actions {
    justify-content: stretch;
    flex-direction: column;
  }
}
</style>
