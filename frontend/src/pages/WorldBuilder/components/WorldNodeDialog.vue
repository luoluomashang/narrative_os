<template>
  <el-dialog :model-value="visible" :title="mode === 'region' ? '新建地区' : '新建势力'" width="760px" @close="$emit('close')">
    <el-form v-if="mode === 'region'" label-position="top" size="small">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="地区名称">
            <el-input v-model="regionForm.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="地区类型">
            <el-input v-model="regionForm.region_type" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="地形">
            <el-input v-model="regionForm.geography.terrain" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="气候">
            <el-input v-model="regionForm.geography.climate" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="地理特征（每行一条）">
        <el-input v-model="regionSpecialFeatures" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="地标（每行一条）">
        <el-input v-model="regionLandmarks" type="textarea" :rows="2" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="主导种族">
            <el-input v-model="regionForm.race.primary_race" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="文明名称">
            <el-input v-model="regionForm.civilization.name" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="次要种族（每行一条）">
        <el-input v-model="regionSecondaryRaces" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="文化标签（每行一条）">
        <el-input v-model="regionCultureTags" type="textarea" :rows="2" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="阵营">
            <el-select v-model="regionForm.alignment" style="width: 100%">
              <el-option v-for="item in alignmentOptions" :key="item.value" :label="item.label" :value="item.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="所属势力">
            <el-select v-model="regionForm.faction_ids" style="width: 100%" multiple collapse-tags>
              <el-option v-for="f in factions" :key="f.id" :label="f.name" :value="f.id" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item>
        <el-checkbox v-model="regionForm.power_access.inherits_global">继承全局力量体系</el-checkbox>
      </el-form-item>
      <el-form-item label="专属力量体系" v-if="!regionForm.power_access.inherits_global">
        <el-select v-model="regionForm.power_access.custom_system_id" style="width: 100%" clearable>
          <el-option v-for="ps in powerSystems" :key="ps.id" :label="ps.name" :value="ps.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="标签（每行一条）">
        <el-input v-model="regionTags" type="textarea" :rows="2" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="regionForm.notes" type="textarea" :rows="3" />
      </el-form-item>
    </el-form>

    <el-form v-else label-position="top" size="small">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="势力名称">
            <el-input v-model="factionForm.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="势力范围">
            <el-select v-model="factionForm.scope" style="width: 100%">
              <el-option label="世界内" value="internal" />
              <el-option label="域外" value="external" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="阵营">
        <el-select v-model="factionForm.alignment" style="width: 100%">
          <el-option v-for="item in alignmentOptions" :key="item.value" :label="item.label" :value="item.value" />
        </el-select>
      </el-form-item>
      <el-form-item label="控制地区">
        <el-select v-model="factionForm.territory_region_ids" style="width: 100%" multiple collapse-tags>
          <el-option v-for="r in regions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="绑定力量体系">
        <el-select v-model="factionForm.power_system_id" style="width: 100%" clearable>
          <el-option v-for="ps in powerSystems" :key="ps.id" :label="ps.name" :value="ps.id" />
        </el-select>
      </el-form-item>
      <el-form-item label="关系映射（每行：势力ID=关系值）">
        <el-input v-model="factionRelationMap" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="factionForm.description" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="备注">
        <el-input v-model="factionForm.notes" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" @click="submitCreate">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Faction, PowerSystem, Region } from '@/api/world'

const props = defineProps<{
  visible: boolean
  mode: 'region' | 'faction'
  regions: Region[]
  factions: Faction[]
  powerSystems: PowerSystem[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create-region', payload: Omit<Region, 'id'>): void
  (e: 'create-faction', payload: Omit<Faction, 'id'>): void
}>()

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

const regionForm = ref<Omit<Region, 'id'>>({
  name: '新地区',
  region_type: '区域',
  x: 120,
  y: 120,
  geography: {
    terrain: '',
    climate: '',
    special_features: [],
    landmarks: [],
  },
  race: {
    primary_race: '',
    secondary_races: [],
    is_mixed: false,
    race_notes: '',
  },
  civilization: {
    name: '',
    belief_system: '',
    culture_tags: [],
    govt_type: '',
  },
  power_access: {
    inherits_global: true,
    custom_system_id: null,
    power_notes: '',
  },
  faction_ids: [],
  alignment: 'true_neutral',
  tags: [],
  notes: '',
})

const factionForm = ref<Omit<Faction, 'id'>>({
  name: '新势力',
  scope: 'internal',
  description: '',
  territory_region_ids: [],
  alignment: 'true_neutral',
  relation_map: {},
  power_system_id: null,
  notes: '',
})

const regionSpecialFeatures = computed({
  get: () => regionForm.value.geography.special_features.join('\n'),
  set: (v: string) => {
    regionForm.value.geography.special_features = splitLines(v)
  },
})

const regionLandmarks = computed({
  get: () => regionForm.value.geography.landmarks.join('\n'),
  set: (v: string) => {
    regionForm.value.geography.landmarks = splitLines(v)
  },
})

const regionSecondaryRaces = computed({
  get: () => regionForm.value.race.secondary_races.join('\n'),
  set: (v: string) => {
    regionForm.value.race.secondary_races = splitLines(v)
  },
})

const regionCultureTags = computed({
  get: () => regionForm.value.civilization.culture_tags.join('\n'),
  set: (v: string) => {
    regionForm.value.civilization.culture_tags = splitLines(v)
  },
})

const regionTags = computed({
  get: () => regionForm.value.tags.join('\n'),
  set: (v: string) => {
    regionForm.value.tags = splitLines(v)
  },
})

const factionRelationMap = computed({
  get: () => Object.entries(factionForm.value.relation_map || {}).map(([id, score]) => `${id}=${score}`).join('\n'),
  set: (v: string) => {
    const map: Record<string, number> = {}
    for (const line of v.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed) continue
      const [idPart, scorePart] = trimmed.split('=')
      const id = (idPart || '').trim()
      const score = Number((scorePart || '').trim())
      if (!id || Number.isNaN(score)) continue
      map[id] = Math.max(-1, Math.min(1, score))
    }
    factionForm.value.relation_map = map
  },
})

watch(
  () => props.visible,
  (isVisible) => {
    if (!isVisible) return
    regionForm.value = {
      ...regionForm.value,
      name: '新地区',
      region_type: '区域',
      x: 120 + Math.random() * 260,
      y: 100 + Math.random() * 260,
    }
    factionForm.value = {
      ...factionForm.value,
      name: '新势力',
      scope: 'internal',
    }
  },
)

function splitLines(input: string) {
  return input.split('\n').map((x) => x.trim()).filter(Boolean)
}

function submitCreate() {
  if (props.mode === 'region') {
    emit('create-region', JSON.parse(JSON.stringify(regionForm.value)))
  } else {
    emit('create-faction', JSON.parse(JSON.stringify(factionForm.value)))
  }
}
</script>
