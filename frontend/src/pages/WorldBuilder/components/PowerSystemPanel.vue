<template>
  <el-card shadow="never" class="panel-card">
    <template #header>
      <div class="header-row">
        <span>力量体系</span>
        <el-button size="small" type="primary" plain @click="$emit('create')">+ 新增</el-button>
      </div>
    </template>

    <el-empty v-if="items.length === 0" description="尚未创建力量体系" :image-size="56" />

    <div v-else class="ps-list">
      <div
        v-for="item in items"
        :key="item.id"
        class="ps-item"
        :class="{ active: selectedId === item.id }"
        @click="$emit('select', item.id)"
      >
        <div class="ps-title">{{ item.name }}</div>
        <div class="ps-meta">模板：{{ item.template }}</div>
      </div>
    </div>

    <div v-if="selected" class="editor">
      <el-divider />

      <div class="tree-toggle">
        <el-button size="small" text @click="showTree = !showTree">
          {{ showTree ? '▼ 收起技能树' : '▶ 查看技能树' }}
        </el-button>
      </div>
      <PowerTreeView
        v-if="showTree"
        :levels="draft.levels"
        :active-level="draft.levels.length - 1"
      />

      <el-form label-position="top" size="small">
        <el-form-item>
          <el-checkbox v-model="syncToGlobal">保存后同步到全局继承节点</el-checkbox>
        </el-form-item>
        <el-form-item label="体系名称">
          <el-input v-model="draft.name" />
        </el-form-item>
        <el-form-item label="模板类型">
          <el-input v-model="draft.template" disabled />
        </el-form-item>
        <el-form-item label="等级定义">
          <div class="level-list">
            <div v-for="(level, idx) in draft.levels" :key="idx" class="level-item">
              <el-input v-model="level.name" placeholder="境界名称" />
              <el-input v-model="level.description" placeholder="境界描述" />
              <el-input v-model="level.requirements" placeholder="晋升条件" />
              <el-button text type="danger" @click="removeLevel(idx)">删除</el-button>
            </div>
            <el-button size="small" plain @click="addLevel">+ 新增等级</el-button>
          </div>
        </el-form-item>
        <el-form-item label="规则（每行一条）">
          <el-input v-model="rulesText" type="textarea" :rows="4" />
        </el-form-item>
        <el-form-item label="资源（每行一条）">
          <el-input v-model="resourcesText" type="textarea" :rows="3" />
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="draft.notes" type="textarea" :rows="3" />
        </el-form-item>
        <div class="actions">
          <el-button type="primary" :loading="loading" @click="onSave">保存</el-button>
          <el-button type="danger" plain :loading="loading" @click="$emit('delete', selected.id)">删除</el-button>
        </div>
      </el-form>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PowerSystem } from '@/api/world'
import PowerTreeView from './PowerTreeView.vue'

const props = defineProps<{
  items: PowerSystem[]
  selectedId: string
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'create'): void
  (e: 'select', id: string): void
  (e: 'save', id: string, payload: Partial<PowerSystem>, syncGlobal: boolean): void
  (e: 'delete', id: string): void
}>()

const selected = computed(() => props.items.find((x) => x.id === props.selectedId) || null)
const draft = ref<PowerSystem>({
  id: '',
  name: '',
  template: 'custom',
  levels: [],
  rules: [],
  resources: [],
  notes: '',
})
const rulesText = ref('')
const resourcesText = ref('')
const syncToGlobal = ref(false)
const showTree = ref(false)

watch(selected, (val) => {
  if (!val) return
  draft.value = JSON.parse(JSON.stringify(val))
  rulesText.value = (val.rules || []).join('\n')
  resourcesText.value = (val.resources || []).join('\n')
}, { immediate: true })

function onSave() {
  if (!selected.value) return
  emit('save', selected.value.id, {
    name: draft.value.name,
    levels: draft.value.levels,
    rules: rulesText.value.split('\n').map((x) => x.trim()).filter(Boolean),
    resources: resourcesText.value.split('\n').map((x) => x.trim()).filter(Boolean),
    notes: draft.value.notes,
  }, syncToGlobal.value)
}

function addLevel() {
  draft.value.levels.push({
    name: '新等级',
    description: '',
    requirements: '',
  })
}

function removeLevel(index: number) {
  draft.value.levels.splice(index, 1)
}
</script>

<style scoped>
.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ps-list {
  display: grid;
  gap: 8px;
}
.ps-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px 10px;
  cursor: pointer;
}
.ps-item.active {
  border-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.ps-title {
  font-size: 13px;
  font-weight: 600;
}
.ps-meta {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.actions {
  display: flex;
  gap: 8px;
}

.level-list {
  display: grid;
  gap: 8px;
}

.level-item {
  display: grid;
  gap: 6px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 8px;
}

.tree-toggle {
  margin-bottom: 8px;
}
</style>
