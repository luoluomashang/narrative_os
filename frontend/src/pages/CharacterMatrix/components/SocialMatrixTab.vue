<template>
  <div class="social-tab">
    <div class="header-row">
      <span class="section-title">关系矩阵</span>
      <NButton variant="ghost" size="small" @click="startAdd">+ 添加关系</NButton>
    </div>

    <!-- Add form -->
    <div v-if="adding" class="add-form">
      <input v-model="newTarget" placeholder="目标角色名…" class="name-input" @keydown.enter.prevent="addRelation" />
      <NButton size="small" variant="primary" @click="addRelation">确认</NButton>
      <NButton size="small" variant="ghost" @click="adding = false">取消</NButton>
    </div>

    <div v-if="Object.keys(local).length === 0" class="empty-hint">尚无关系数据，点击"+ 添加关系"开始</div>

    <!-- Relation cards -->
    <div v-for="(profile, target) in local" :key="target" class="relation-card">
      <div class="card-header">
        <span class="target-name">{{ target }}</span>
        <button class="del-btn" @click="deleteRelation(target as string)">删除</button>
      </div>
      <div class="sliders">
        <div class="slider-row">
          <span class="slider-label">好感</span>
          <input v-model.number="profile.affinity" type="range" min="-1" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.affinity.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">信任</span>
          <input v-model.number="profile.trust" type="range" min="0" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.trust.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">依赖</span>
          <input v-model.number="profile.dependency" type="range" min="0" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.dependency.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">忌惮</span>
          <input v-model.number="profile.fear" type="range" min="0" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.fear.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">嫉妒</span>
          <input v-model.number="profile.jealousy" type="range" min="0" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.jealousy.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">控制欲</span>
          <input v-model.number="profile.control_desire" type="range" min="0" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.control_desire.toFixed(2) }}</span>
        </div>
        <div class="slider-row">
          <span class="slider-label">欠债感</span>
          <input v-model.number="profile.debt_sense" type="range" min="-1" max="1" step="0.05" class="slider-input" />
          <span class="slider-value">{{ profile.debt_sense.toFixed(2) }}</span>
        </div>
      </div>
      <div class="field-group">
        <label>认知标签</label>
        <div class="tags-row">
          <span v-for="(tag, i) in profile.cognitive_tags" :key="i" class="tag">
            {{ tag }}<button @click="removeTag(target as string, i)">×</button>
          </span>
          <input
            v-model="tagInputs[target as string]"
            placeholder="输入标签…"
            class="tag-inline-input"
            @keydown.enter.prevent="addTag(target as string)"
          />
        </div>
      </div>
      <div class="field-group">
        <label>补充说明</label>
        <textarea v-model="profile.notes" rows="2" />
      </div>
    </div>

    <div class="actions">
      <NButton :loading="loading" variant="primary" @click="save">保存 Social 矩阵</NButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, reactive } from 'vue'
import NButton from '@/components/common/NButton.vue'
import type { CharacterDetail, RelationshipProfile } from '@/types/api'

const props = defineProps<{ model: CharacterDetail; loading: boolean }>()
const emit = defineEmits<{ (e: 'save', v: Partial<CharacterDetail>): void }>()

function cloneMatrix(m?: Record<string, RelationshipProfile>): Record<string, RelationshipProfile> {
  if (!m) return {}
  return Object.fromEntries(
    Object.entries(m).map(([k, v]) => [k, {
      target_name: v.target_name ?? k,
      affinity: v.affinity ?? 0,
      trust: v.trust ?? 0.5,
      dependency: v.dependency ?? 0,
      fear: v.fear ?? 0,
      jealousy: v.jealousy ?? 0,
      control_desire: v.control_desire ?? 0,
      debt_sense: v.debt_sense ?? 0,
      cognitive_tags: [...(v.cognitive_tags ?? [])],
      notes: v.notes ?? '',
    }])
  )
}

const local = reactive<Record<string, RelationshipProfile>>(cloneMatrix(props.model.social_matrix))
const tagInputs = reactive<Record<string, string>>({})
const adding = ref(false)
const newTarget = ref('')

watch(() => props.model.social_matrix, (m) => {
  Object.keys(local).forEach(k => delete local[k])
  Object.assign(local, cloneMatrix(m))
})

function startAdd() { adding.value = true; newTarget.value = '' }

function addRelation() {
  const t = newTarget.value.trim()
  if (!t || local[t]) return
  local[t] = { target_name: t, affinity: 0, trust: 0.5, dependency: 0, fear: 0, jealousy: 0, control_desire: 0, debt_sense: 0, cognitive_tags: [], notes: '' }
  tagInputs[t] = ''
  adding.value = false
}

function deleteRelation(target: string) { delete local[target] }

function addTag(target: string) {
  const v = (tagInputs[target] ?? '').trim()
  if (!v) return
  if (!local[target].cognitive_tags.includes(v)) local[target].cognitive_tags.push(v)
  tagInputs[target] = ''
}

function removeTag(target: string, i: number) {
  local[target].cognitive_tags.splice(i, 1)
}

function save() {
  emit('save', { social_matrix: { ...local } })
}
</script>

<style scoped>
.social-tab { display: flex; flex-direction: column; gap: 12px; padding: 4px; }
.header-row { display: flex; justify-content: space-between; align-items: center; }
.section-title { font-size: 14px; font-weight: 600; }
.add-form { display: flex; gap: 8px; align-items: center; }
.name-input { border: 1px solid var(--color-border); border-radius: 6px; padding: 4px 8px; font-size: 13px; flex: 1; background: var(--color-bg-input, #fff); color: var(--color-text); }
.empty-hint { text-align: center; color: var(--color-text-secondary); padding: 24px 0; font-size: 13px; }
.relation-card { border: 1px solid var(--color-border); border-radius: 8px; padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.card-header { display: flex; justify-content: space-between; align-items: center; }
.target-name { font-weight: 600; font-size: 14px; }
.del-btn { background: none; border: none; color: var(--color-error, #ef4444); cursor: pointer; font-size: 13px; }
.sliders { display: flex; flex-direction: column; gap: 6px; }
.slider-row { display: grid; grid-template-columns: 56px 1fr 40px; gap: 6px; align-items: center; }
.slider-label { font-size: 12px; color: var(--color-text-secondary); }
.slider-input { width: 100%; }
.slider-value { font-size: 12px; text-align: right; }
.field-group { display: flex; flex-direction: column; gap: 4px; }
label { font-size: 12px; font-weight: 500; color: var(--color-text-secondary); }
textarea { border: 1px solid var(--color-border); border-radius: 6px; padding: 6px 8px; font-size: 13px; resize: vertical; background: var(--color-bg-input, #fff); color: var(--color-text); width: 100%; }
.tags-row { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; border: 1px solid var(--color-border); border-radius: 6px; padding: 4px 8px; background: var(--color-bg-input, #fff); min-height: 32px; }
.tag { background: var(--color-primary, #6366f1); color: #fff; border-radius: 12px; padding: 2px 8px; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; font-size: 14px; line-height: 1; }
.tag-inline-input { border: none; outline: none; font-size: 12px; flex: 1; min-width: 80px; background: transparent; color: var(--color-text); }
.actions { display: flex; justify-content: flex-end; }
</style>
