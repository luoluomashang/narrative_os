<template>
  <el-form label-position="top" size="small">
    <el-form-item label="名称">
      <el-input v-model="model.name" />
    </el-form-item>
    <el-form-item label="势力范围">
      <el-select v-model="model.scope" style="width: 100%">
        <el-option label="世界内" value="internal" />
        <el-option label="域外" value="external" />
      </el-select>
    </el-form-item>
    <el-form-item label="描述">
      <div class="field-with-ai">
        <el-input v-model="model.description" type="textarea" :rows="4" />
        <el-button class="ai-expand-btn" size="small" text :loading="expandingField === 'description'" @click="onExpand('description')">✦</el-button>
      </div>
    </el-form-item>
    <el-form-item label="阵营倾向">
      <el-select v-model="model.alignment" style="width: 100%">
        <el-option v-for="item in alignmentOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="控制地区">
      <el-select v-model="model.territory_region_ids" style="width: 100%" multiple collapse-tags>
        <el-option v-for="region in regions" :key="region.id" :label="region.name" :value="region.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="绑定力量体系">
      <el-select v-model="model.power_system_id" style="width: 100%" clearable>
        <el-option v-for="item in powerSystems" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="势力关系映射（每行：势力ID=关系值）">
      <el-input v-model="relationMapText" type="textarea" :rows="4" @change="syncRelationMap" />
    </el-form-item>
    <el-form-item label="备注">
      <el-input v-model="model.notes" type="textarea" :rows="3" />
    </el-form-item>

    <el-collapse v-model="advancedOpen" class="advanced-collapse">
      <el-collapse-item title="⚖ 治理与律法" name="governance">
        <el-form-item label="治理结构">
          <el-input v-model="advancedFields.governance" placeholder="如：元老院制、教主独裁..." />
        </el-form-item>
        <el-form-item label="核心禁忌">
          <el-input v-model="advancedFields.taboos" type="textarea" :rows="2" placeholder="势力内的禁忌事项..." />
        </el-form-item>
        <el-form-item label="歧视与刻板印象">
          <el-input v-model="advancedFields.prejudice" type="textarea" :rows="2" placeholder="对外势力或种族的偏见..." />
        </el-form-item>
      </el-collapse-item>
    </el-collapse>

    <div class="detail-actions">
      <el-button type="primary" :loading="loading" @click="$emit('save')">保存</el-button>
      <el-button type="danger" plain :loading="loading" @click="$emit('delete')">删除</el-button>
    </div>

    <el-divider />
    <el-button type="warning" plain :loading="suggestLoading" @click="onSuggestRelations">✦ AI 建议关系</el-button>
    <div v-if="suggestions.length" class="suggest-list">
      <div v-for="(s, idx) in suggestions" :key="idx" class="suggest-card">
        <div class="suggest-info">
          <strong>{{ s.source_id }} → {{ s.target_id }}</strong>
          <span class="suggest-type">{{ s.relation_type }}</span>
        </div>
        <div class="suggest-reason">{{ s.reason }}</div>
        <el-button size="small" type="success" plain @click="$emit('adopt-relation', s)">采纳</el-button>
      </div>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Faction } from '@/api/world'
import { world } from '@/api/world'

const props = defineProps<{
  model: Faction
  loading: boolean
  regions: Array<{ id: string; name: string }>
  powerSystems: Array<{ id: string; name: string }>
  projectId: string
  allFactionIds: string[]
}>()
defineEmits<{ (e: 'save'): void; (e: 'delete'): void; (e: 'adopt-relation', s: { source_id: string; target_id: string; relation_type: string; reason: string }): void }>()

const advancedOpen = ref<string[]>([])
const advancedFields = ref({
  governance: '',
  taboos: '',
  prejudice: '',
})

const alignmentOptions = [
  { value: 'lawful_good', label: '秩序善良' },
  { value: 'neutral_good', label: '中立善良' },
  { value: 'chaotic_good', label: '混沌善良' },
  { value: 'lawful_neutral', label: '秩序中立' },
  { value: 'true_neutral', label: '绝对中立' },
  { value: 'chaotic_neutral', label: '混沌中立' },
  { value: 'lawful_evil', label: '秩序邪恶' },
  { value: 'neutral_evil', label: '中立邪恶' },
  { value: 'chaotic_evil', label: '混沌邪恶' },
  { value: 'transcendent', label: '超越阵营' },
]

const relationMapText = computed({
  get: () => {
    const entries = Object.entries(props.model.relation_map || {})
    return entries.map(([id, value]) => `${id}=${value}`).join('\n')
  },
  set: (v: string) => {
    const next: Record<string, number> = {}
    for (const line of v.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const [idPart, valuePart] = trimmed.split('=')
      const id = (idPart || '').trim()
      const score = Number((valuePart || '').trim())
      if (!id || Number.isNaN(score)) continue
      next[id] = Math.max(-1, Math.min(1, score))
    }
    props.model.relation_map = next
  },
})

function syncRelationMap() {
  relationMapText.value = relationMapText.value
}

// Parse advanced fields from notes on model change
watch(() => props.model.id, () => {
  const notes = props.model.notes || ''
  advancedFields.value = {
    governance: extractTaggedField(notes, '治理'),
    taboos: extractTaggedField(notes, '禁忌'),
    prejudice: extractTaggedField(notes, '偏见'),
  }
}, { immediate: true })

function extractTaggedField(notes: string, tag: string): string {
  const regex = new RegExp(`\\[${tag}\\]\\s*(.+?)(?=\\n\\[|$)`, 's')
  const match = notes.match(regex)
  return match ? match[1].trim() : ''
}

// Sync advanced fields back to notes
watch(advancedFields, (fields) => {
  // Remove existing tagged sections
  let notes = (props.model.notes || '').replace(/\n?\[(?:治理|禁忌|偏见)\]\s*.+?(?=\n\[|$)/gs, '').trim()
  const parts: string[] = []
  if (fields.governance) parts.push(`[治理] ${fields.governance}`)
  if (fields.taboos) parts.push(`[禁忌] ${fields.taboos}`)
  if (fields.prejudice) parts.push(`[偏见] ${fields.prejudice}`)
  if (parts.length > 0) {
    notes = notes ? `${notes}\n${parts.join('\n')}` : parts.join('\n')
  }
  props.model.notes = notes
}, { deep: true })

// AI 功能
const suggestLoading = ref(false)
const suggestions = ref<Array<{ source_id: string; target_id: string; relation_type: string; reason: string }>>([])
const expandingField = ref<string | null>(null)

async function onSuggestRelations() {
  suggestLoading.value = true
  suggestions.value = []
  try {
    const res = await world.suggestRelations(props.projectId, props.allFactionIds)
    suggestions.value = res.data.suggestions || []
  } catch {
    suggestions.value = []
  } finally {
    suggestLoading.value = false
  }
}

async function onExpand(field: string) {
  expandingField.value = field
  try {
    const res = await world.expandEntityField(props.projectId, 'faction', props.model.id, field)
    if (res.data.generated_content) {
      ;(props.model as any)[field] = res.data.generated_content
    }
  } finally {
    expandingField.value = null
  }
}
</script>

<style scoped>
.detail-actions {
  display: flex;
  gap: 8px;
}

.advanced-collapse {
  margin: 12px 0;
  --el-collapse-header-bg-color: transparent;
  --el-collapse-content-bg-color: transparent;
}

.field-with-ai {
  position: relative;
  width: 100%;
}
.ai-expand-btn {
  position: absolute;
  top: 2px;
  right: 2px;
  font-size: 14px;
  color: var(--wb-neon-cyan, #2ef2ff);
}

.suggest-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.suggest-card {
  padding: 8px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 6px;
  background: rgba(255,255,255,0.03);
}
.suggest-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.suggest-type {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(77, 124, 255, 0.2);
  color: var(--wb-neon-blue, #4d7cff);
}
.suggest-reason {
  font-size: 12px;
  color: rgba(255,255,255,0.6);
  margin-bottom: 6px;
}
</style>
