<template>
  <div class="motivation-tab">
    <!-- Tension overview bar -->
    <div class="tension-overview" v-if="localMotivations.length">
      <div class="section-title">张力总览</div>
      <div class="tension-bar-wrap">
        <div class="tension-bar" :style="{ width: `${avgTension * 100}%`, background: tensionBarColor }"></div>
      </div>
      <div class="tension-label" :style="{ color: tensionBarColor }">
        均值 {{ avgTension.toFixed(2) }}
        <span v-if="avgTension >= 0.7"> — 当前角色内在冲突强烈，建议在下一章节安排关键宣泄场景</span>
        <span v-else-if="avgTension >= 0.3"> — 中等张力，潜在冲突</span>
        <span v-else> — 低张力，暂时平衡</span>
      </div>
    </div>

    <!-- Motivations list -->
    <div class="section-title" style="margin-top: 12px">动机冲突列表</div>
    <div v-if="!localMotivations.length" class="empty-hint">暂无动机，点击下方"+ 添加动机"</div>
    <div v-for="(m, idx) in localMotivations" :key="idx" class="motivation-item">
      <div class="motivation-row">
        <el-input v-model="m.desire" placeholder="欲望/驱力，如：变得更强" size="small" style="flex:1" />
        <button class="motivation-del" @click="removeMotivation(idx)">×</button>
      </div>
      <el-input v-model="m.fear" placeholder="恐惧，如：失去同伴" size="small" style="margin-top:4px" />
      <div class="tension-slider-row">
        <span class="tension-slider-label">张力</span>
        <el-slider
          v-model="m.tension"
          :min="0" :max="1" :step="0.05"
          :show-tooltip="false"
          style="flex:1"
        />
        <span class="tension-value" :style="{ color: tensionColor(m.tension) }">{{ m.tension.toFixed(2) }}</span>
      </div>
      <el-input v-model="m.notes" placeholder="补充说明（可选）" size="small" style="margin-top:4px" />
    </div>
    <el-button size="small" style="margin-top: 6px" @click="addMotivation">+ 添加动机</el-button>

    <!-- scenario_context + system_instructions -->
    <div class="section-title" style="margin-top: 16px">场景语境与系统指令</div>
    <el-form label-position="top" size="small">
      <el-form-item label="当前场景语境（供 Planner 参考）">
        <el-input v-model="localScenarioContext" type="textarea" :rows="3" placeholder="描述角色当前所处的场景状况" />
      </el-form-item>
      <el-form-item label="角色专属系统提示词">
        <el-input v-model="localSystemInstructions" type="textarea" :rows="4" placeholder="此内容将作为最高优先级规则注入写作 Agent" />
        <div class="field-help">此内容将作为最高优先级规则注入写作 Agent</div>
      </el-form-item>
    </el-form>

    <!-- Save button -->
    <div class="motivation-actions">
      <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import type { CharacterDetail, Motivation } from '@/types/api'

const props = defineProps<{
  model: CharacterDetail
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'save', data: Partial<CharacterDetail>): void
}>()

const localMotivations = ref<Motivation[]>([])
const localScenarioContext = ref('')
const localSystemInstructions = ref('')

watch(() => props.model, (m) => {
  if (m) {
    localMotivations.value = (m.motivations ?? []).map((mot: Motivation) => ({ ...mot }))
    localScenarioContext.value = m.scenario_context ?? ''
    localSystemInstructions.value = m.system_instructions ?? ''
  }
}, { immediate: true })

const avgTension = computed(() => {
  if (!localMotivations.value.length) return 0
  return localMotivations.value.reduce((sum, m) => sum + (m.tension ?? 0), 0) / localMotivations.value.length
})

const tensionBarColor = computed(() => tensionColor(avgTension.value))

function tensionColor(t: number): string {
  if (t >= 0.7) return '#ff4040'
  if (t >= 0.3) return '#ffc42e'
  return '#2eff8a'
}

function addMotivation() {
  localMotivations.value.push({ desire: '', fear: '', tension: 0.5, notes: '' })
}

function removeMotivation(idx: number) {
  localMotivations.value.splice(idx, 1)
}

function handleSave() {
  emit('save', {
    motivations: localMotivations.value.filter((m) => m.desire.trim()),
    scenario_context: localScenarioContext.value,
    system_instructions: localSystemInstructions.value,
  })
}
</script>

<style scoped>
.motivation-tab { padding: 4px 0; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.empty-hint {
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 8px 0;
}
.tension-overview {
  padding: 10px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  margin-bottom: 12px;
}
.tension-bar-wrap {
  height: 8px;
  background: var(--color-surface-l2);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 6px;
}
.tension-bar {
  height: 100%;
  border-radius: 4px;
  transition: width 300ms, background 300ms;
}
.tension-label {
  font-size: 12px;
}
.motivation-item {
  padding: 8px 10px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  margin-bottom: 6px;
}
.motivation-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.motivation-del {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
}
.motivation-del:hover { color: #ff4040; }
.tension-slider-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
}
.tension-slider-label {
  font-size: 12px;
  color: var(--color-text-secondary);
  min-width: 28px;
}
.tension-value {
  font-size: 12px;
  font-weight: 600;
  min-width: 36px;
  text-align: right;
}
.field-help {
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 2px;
}
.motivation-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
