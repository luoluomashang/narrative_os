<template>
  <el-form label-position="top" size="small">
    <el-form-item label="名称">
      <el-input v-model="model.name" />
    </el-form-item>
    <el-form-item label="地区类型">
      <el-input v-model="model.region_type" />
    </el-form-item>
    <el-form-item label="地形">
      <el-input v-model="model.geography.terrain" />
    </el-form-item>
    <el-form-item label="气候">
      <el-input v-model="model.geography.climate" />
    </el-form-item>
    <el-form-item label="地理特征（每行一条）">
      <el-input v-model="specialFeaturesText" type="textarea" :rows="3" @change="syncSpecialFeatures" />
    </el-form-item>
    <el-form-item label="地标（每行一条）">
      <el-input v-model="landmarksText" type="textarea" :rows="3" @change="syncLandmarks" />
    </el-form-item>

    <el-divider>种族与文明</el-divider>
    <el-form-item label="主导种族">
      <el-input v-model="model.race.primary_race" />
    </el-form-item>
    <el-form-item label="次要种族（每行一条）">
      <el-input v-model="secondaryRacesText" type="textarea" :rows="3" @change="syncSecondaryRaces" />
    </el-form-item>
    <el-form-item>
      <el-checkbox v-model="model.race.is_mixed">是否混居</el-checkbox>
    </el-form-item>
    <el-form-item label="种族说明">
      <el-input v-model="model.race.race_notes" type="textarea" :rows="2" />
    </el-form-item>

    <el-form-item label="文明名称">
      <el-input v-model="model.civilization.name" />
    </el-form-item>
    <el-form-item label="信仰体系">
      <el-input v-model="model.civilization.belief_system" />
    </el-form-item>
    <el-form-item label="文化标签（每行一条）">
      <el-input v-model="cultureTagsText" type="textarea" :rows="3" @change="syncCultureTags" />
    </el-form-item>
    <el-form-item label="政体">
      <el-input v-model="model.civilization.govt_type" />
    </el-form-item>

    <el-divider>力量接入与势力归属</el-divider>
    <el-form-item>
      <el-checkbox v-model="model.power_access.inherits_global">继承全局力量体系</el-checkbox>
    </el-form-item>
    <el-form-item label="专属力量体系" v-if="!model.power_access.inherits_global">
      <el-select v-model="model.power_access.custom_system_id" style="width: 100%" clearable>
        <el-option v-for="item in powerSystems" :key="item.id" :label="item.name" :value="item.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="力量备注">
      <el-input v-model="model.power_access.power_notes" type="textarea" :rows="2" />
    </el-form-item>
    <el-form-item label="所属势力">
      <el-select v-model="model.faction_ids" style="width: 100%" multiple collapse-tags>
        <el-option v-for="f in factions" :key="f.id" :label="f.name" :value="f.id" />
      </el-select>
    </el-form-item>

    <el-form-item label="阵营倾向">
      <el-select v-model="model.alignment" style="width: 100%">
        <el-option v-for="item in alignmentOptions" :key="item.value" :label="item.label" :value="item.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="标签（每行一条）">
      <el-input v-model="tagsText" type="textarea" :rows="2" @change="syncTags" />
    </el-form-item>
    <el-form-item label="备注">
      <div class="field-with-ai">
        <el-input v-model="model.notes" type="textarea" :rows="4" />
        <el-button class="ai-expand-btn" size="small" text :loading="expandingField === 'notes'" @click="onExpand('notes')">✦</el-button>
      </div>
    </el-form-item>

    <el-collapse v-model="advancedOpen" class="advanced-collapse">
      <el-collapse-item title="⚙ 经济与资源" name="economy">
        <el-form-item label="主要货币">
          <el-input v-model="advancedFields.currency" placeholder="如：灵石、金币..." />
        </el-form-item>
        <el-form-item label="核心资源">
          <el-input v-model="advancedFields.resources" type="textarea" :rows="2" placeholder="矿产、农业、法宝材料..." />
        </el-form-item>
        <el-form-item label="贸易路线">
          <el-input v-model="advancedFields.trade" type="textarea" :rows="2" placeholder="连通地区及主要商品..." />
        </el-form-item>
      </el-collapse-item>
      <el-collapse-item title="🏛 文化与信仰" name="culture">
        <el-form-item label="建筑风格">
          <el-input v-model="advancedFields.architecture" placeholder="如：飞檐斗拱、浮空塔..." />
        </el-form-item>
        <el-form-item label="禁忌与禁令">
          <el-input v-model="advancedFields.taboos" type="textarea" :rows="2" placeholder="当地禁忌与法令..." />
        </el-form-item>
      </el-collapse-item>
    </el-collapse>

    <div class="detail-actions">
      <el-button type="primary" :loading="loading" @click="$emit('save')">保存</el-button>
      <el-button type="danger" plain :loading="loading" @click="$emit('delete')">删除</el-button>
    </div>
  </el-form>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Region } from '@/api/world'
import { world } from '@/api/world'

const props = defineProps<{
  model: Region
  loading: boolean
  factions: Array<{ id: string; name: string }>
  powerSystems: Array<{ id: string; name: string }>
  projectId: string
}>()

defineEmits<{ (e: 'save'): void; (e: 'delete'): void }>()

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

const advancedOpen = ref<string[]>([])
const advancedFields = ref({
  currency: '',
  resources: '',
  trade: '',
  architecture: '',
  taboos: '',
})

// Parse advanced fields from tags on model change
watch(() => props.model.id, () => {
  const tags = props.model.tags || []
  advancedFields.value = {
    currency: tags.find(t => t.startsWith('adv:currency:'))?.replace('adv:currency:', '') || '',
    resources: tags.find(t => t.startsWith('adv:resources:'))?.replace('adv:resources:', '') || '',
    trade: tags.find(t => t.startsWith('adv:trade:'))?.replace('adv:trade:', '') || '',
    architecture: tags.find(t => t.startsWith('adv:architecture:'))?.replace('adv:architecture:', '') || '',
    taboos: tags.find(t => t.startsWith('adv:taboos:'))?.replace('adv:taboos:', '') || '',
  }
}, { immediate: true })

// Sync advanced fields back to tags before save
watch(advancedFields, (fields) => {
  const baseTags = (props.model.tags || []).filter(t => !t.startsWith('adv:'))
  const advTags: string[] = []
  if (fields.currency) advTags.push(`adv:currency:${fields.currency}`)
  if (fields.resources) advTags.push(`adv:resources:${fields.resources}`)
  if (fields.trade) advTags.push(`adv:trade:${fields.trade}`)
  if (fields.architecture) advTags.push(`adv:architecture:${fields.architecture}`)
  if (fields.taboos) advTags.push(`adv:taboos:${fields.taboos}`)
  props.model.tags = [...baseTags, ...advTags]
}, { deep: true })

const specialFeaturesText = computed({
  get: () => (props.model.geography.special_features || []).join('\n'),
  set: (v: string) => {
    props.model.geography.special_features = v.split('\n').map((x) => x.trim()).filter(Boolean)
  },
})
const landmarksText = computed({
  get: () => (props.model.geography.landmarks || []).join('\n'),
  set: (v: string) => {
    props.model.geography.landmarks = v.split('\n').map((x) => x.trim()).filter(Boolean)
  },
})
const secondaryRacesText = computed({
  get: () => (props.model.race.secondary_races || []).join('\n'),
  set: (v: string) => {
    props.model.race.secondary_races = v.split('\n').map((x) => x.trim()).filter(Boolean)
  },
})
const cultureTagsText = computed({
  get: () => (props.model.civilization.culture_tags || []).join('\n'),
  set: (v: string) => {
    props.model.civilization.culture_tags = v.split('\n').map((x) => x.trim()).filter(Boolean)
  },
})
const tagsText = computed({
  get: () => (props.model.tags || []).join('\n'),
  set: (v: string) => {
    props.model.tags = v.split('\n').map((x) => x.trim()).filter(Boolean)
  },
})

watch(
  () => props.model.power_access.inherits_global,
  (inheritsGlobal) => {
    if (inheritsGlobal) {
      props.model.power_access.custom_system_id = null
    }
  },
)

function syncSpecialFeatures() {
  specialFeaturesText.value = specialFeaturesText.value
}
function syncLandmarks() {
  landmarksText.value = landmarksText.value
}
function syncSecondaryRaces() {
  secondaryRacesText.value = secondaryRacesText.value
}
function syncCultureTags() {
  cultureTagsText.value = cultureTagsText.value
}
function syncTags() {
  tagsText.value = tagsText.value
}

// AI 扩写
const expandingField = ref<string | null>(null)

async function onExpand(field: string) {
  expandingField.value = field
  try {
    const res = await world.expandEntityField(props.projectId, 'region', props.model.id, field)
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
</style>
