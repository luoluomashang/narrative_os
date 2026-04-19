<template>
  <div class="drive-tab">
    <div class="field-group">
      <label>核心欲望</label>
      <textarea v-model="local.core_desire" placeholder="角色最深层的欲望驱动…" rows="2" />
    </div>
    <div class="field-group">
      <label>核心恐惧</label>
      <textarea v-model="local.core_fear" placeholder="角色最害怕的事情…" rows="2" />
    </div>
    <div class="field-group">
      <label>当前执念</label>
      <textarea v-model="local.current_obsession" placeholder="当前最在意/执着的目标（可变）…" rows="2" />
    </div>
    <div class="field-row">
      <div class="field-group">
        <label>短期目标 <span class="hint">（章节级）</span></label>
        <textarea v-model="local.short_term_goal" rows="2" />
      </div>
      <div class="field-group">
        <label>长期目标 <span class="hint">（全书级）</span></label>
        <textarea v-model="local.long_term_goal" rows="2" />
      </div>
    </div>
    <div class="field-group">
      <label>自我欺骗点</label>
      <textarea v-model="local.self_deception" placeholder="角色不愿承认的自身弱点或盲区…" rows="2" />
    </div>
    <div class="field-row">
      <div class="field-group">
        <label>可妥协项</label>
        <div class="tag-input">
          <span v-for="(t, i) in local.compromisable" :key="`c-${i}`" class="tag">
            {{ t }}<button @click="removeCompromisable(i)">×</button>
          </span>
          <input
            v-model="compromisableInput"
            placeholder="添加…"
            @keydown.enter.prevent="addCompromisable"
            @keydown.comma.prevent="addCompromisable"
          />
        </div>
      </div>
      <div class="field-group">
        <label>不可妥协底线</label>
        <div class="tag-input">
          <span v-for="(t, i) in local.non_negotiable" :key="`n-${i}`" class="tag">
            {{ t }}<button @click="removeNonNegotiable(i)">×</button>
          </span>
          <input
            v-model="nonNegotiableInput"
            placeholder="添加…"
            @keydown.enter.prevent="addNonNegotiable"
            @keydown.comma.prevent="addNonNegotiable"
          />
        </div>
      </div>
    </div>
    <div class="actions">
      <NButton :loading="loading" variant="primary" @click="save">保存 Drive 层</NButton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import NButton from '@/components/common/NButton.vue'
import type { CharacterDrive, CharacterDetail } from '@/types/api'

const props = defineProps<{ model: CharacterDetail; loading: boolean }>()
const emit = defineEmits<{ (e: 'save', v: Partial<CharacterDetail>): void }>()

const empty = (): CharacterDrive => ({
  core_desire: '', core_fear: '', current_obsession: '',
  short_term_goal: '', long_term_goal: '',
  compromisable: [], non_negotiable: [], self_deception: '',
})

const local = ref<CharacterDrive>({ ...empty(), ...(props.model.drive ?? {}) })
const compromisableInput = ref('')
const nonNegotiableInput = ref('')

watch(() => props.model.drive, (d) => {
  local.value = { ...empty(), ...(d ?? {}) }
  compromisableInput.value = ''
  nonNegotiableInput.value = ''
})

function save() {
  emit('save', { drive: { ...local.value } })
}

function addCompromisable() {
  const v = compromisableInput.value.trim()
  const list = local.value.compromisable ?? (local.value.compromisable = [])
  if (!v || list.includes(v)) return
  list.push(v)
  compromisableInput.value = ''
}

function removeCompromisable(index: number) {
  const list = local.value.compromisable ?? (local.value.compromisable = [])
  list.splice(index, 1)
}

function addNonNegotiable() {
  const v = nonNegotiableInput.value.trim()
  const list = local.value.non_negotiable ?? (local.value.non_negotiable = [])
  if (!v || list.includes(v)) return
  list.push(v)
  nonNegotiableInput.value = ''
}

function removeNonNegotiable(index: number) {
  const list = local.value.non_negotiable ?? (local.value.non_negotiable = [])
  list.splice(index, 1)
}
</script>

<style scoped>
.drive-tab { display: flex; flex-direction: column; gap: 14px; padding: 4px; }
.field-group { display: flex; flex-direction: column; gap: 4px; }
.field-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
label { font-size: 13px; font-weight: 500; color: var(--color-text-secondary); }
.hint { font-weight: 400; font-size: 11px; }
textarea { width: 100%; border: 1px solid var(--color-border); border-radius: 6px; padding: 6px 8px; font-size: 13px; resize: vertical; background: var(--color-surface-1); color: var(--color-text-primary); }
.actions { display: flex; justify-content: flex-end; padding-top: 4px; }
.tag-input { display: flex; flex-wrap: wrap; gap: 4px; border: 1px solid var(--color-border); border-radius: 6px; padding: 4px 8px; background: var(--color-surface-1); min-height: 36px; align-items: center; }
.tag { background: var(--color-accent); color: var(--color-text-inverse); border-radius: 12px; padding: 2px 8px; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.tag button { background: none; border: none; color: inherit; cursor: pointer; padding: 0; line-height: 1; font-size: 14px; }
.tag-input input { border: none; outline: none; font-size: 13px; flex: 1; min-width: 80px; background: transparent; color: var(--color-text-primary); }
</style>
