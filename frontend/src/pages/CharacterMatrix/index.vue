<template>
  <div class="char-matrix">
    <!-- Error -->
    <div v-if="error" style="padding:16px">
      <NCard><p style="color:var(--color-error)">加载失败：{{ error }}</p><NButton variant="ghost" @click="load">重试</NButton></NCard>
    </div>
    <template v-else>
      <!-- Left: character list -->
      <CharacterList
        :characters="characters"
        :selected="selected?.name ?? null"
        @select="selectByName"
        @create="showCreateForm = true"
      />

      <!-- Right: detail panel -->
      <div class="char-detail">
        <div v-if="selected && detail">
          <div class="tabs">
            <button v-for="tab in tabs" :key="tab" class="tab-btn" :class="{ active: activeTab === tab }" @click="activeTab = tab">{{ tab }}</button>
          </div>

          <!-- 档案 -->
          <NCard v-if="activeTab === '档案'" style="margin-top:12px">
            <ProfileTab :model="detail" :loading="saving" @save="handleProfileSave" @delete="handleDelete" />
          </NCard>

          <!-- 状态 -->
          <NCard v-if="activeTab === '状态'" style="margin-top:12px">
            <StateTab :model="detail" />
          </NCard>

          <!-- 限制 -->
          <NCard v-if="activeTab === '限制'" style="margin-top:12px">
            <ConstraintTab :model="detail" :loading="saving" @save="onConstraintSave" />
          </NCard>

          <!-- 关系 -->
          <NCard v-if="activeTab === '关系'" style="margin-top:12px">
            <RelationTab :model="detail" :loading="saving" :all-characters="characters" @save="onRelationSave" />
          </NCard>

          <!-- 对话口吻 -->
          <NCard v-if="activeTab === '对话口吻'" style="margin-top:12px">
            <DialogueTab :model="detail" :loading="saving" :project-id="projectId" @save="onTabSave" />
          </NCard>

          <!-- 动机冲突 -->
          <NCard v-if="activeTab === '动机冲突'" style="margin-top:12px">
            <MotivationTab :model="detail" :loading="saving" @save="onTabSave" />
          </NCard>

          <!-- Drive 层 -->
          <NCard v-if="activeTab === 'Drive'" style="margin-top:12px">
            <DriveTab :model="detail" :loading="saving" @save="onTabSave" />
          </NCard>

          <!-- Social 矩阵 -->
          <NCard v-if="activeTab === 'Social'" style="margin-top:12px">
            <SocialMatrixTab :model="detail" :loading="saving" @save="onTabSave" />
          </NCard>

          <!-- Runtime 状态 -->
          <NCard v-if="activeTab === 'Runtime'" style="margin-top:12px">
            <RuntimeTab :model="detail" />
          </NCard>
        </div>
        <div v-else-if="loading" style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-text-secondary)">
          <NBreathingLight :size="8" /> 加载中…
        </div>
        <div v-else style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--color-text-secondary)">
          从左侧选择角色
        </div>
      </div>
    </template>

    <!-- Create Form Dialog -->
    <CharacterForm :visible="showCreateForm" @close="showCreateForm = false" @submit="handleCreate" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import NCard from '@/components/common/NCard.vue'
import NButton from '@/components/common/NButton.vue'
import NBreathingLight from '@/components/common/NBreathingLight.vue'
import CharacterList from './components/CharacterList.vue'
import CharacterForm from './components/CharacterForm.vue'
import ProfileTab from './components/ProfileTab.vue'
import StateTab from './components/StateTab.vue'
import ConstraintTab from './components/ConstraintTab.vue'
import RelationTab from './components/RelationTab.vue'
import DialogueTab from './components/DialogueTab.vue'
import MotivationTab from './components/MotivationTab.vue'
import DriveTab from './components/DriveTab.vue'
import SocialMatrixTab from './components/SocialMatrixTab.vue'
import RuntimeTab from './components/RuntimeTab.vue'
import { projects } from '@/api/projects'
import type { CharacterSummary, CharacterDetail, BehaviorConstraintDetail } from '@/types/api'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const characters = ref<CharacterSummary[]>([])
const selected = ref<CharacterSummary | null>(null)
const detail = ref<CharacterDetail | null>(null)
const activeTab = ref('档案')
const tabs = ['档案', '状态', '限制', '关系', '对话口吻', '动机冲突', 'Drive', 'Social', 'Runtime']
const showCreateForm = ref(false)

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await projects.characters(projectId.value)
    characters.value = res.data
  } catch (e: unknown) {
    error.value = e instanceof Error ? e.message : '请求失败'
  } finally {
    loading.value = false
  }
}

async function selectByName(name: string) {
  const c = characters.value.find(ch => ch.name === name)
  if (!c) return
  selected.value = c
  activeTab.value = '档案'
  try {
    const res = await projects.character(projectId.value, c.name)
    detail.value = res.data
  } catch {
    detail.value = null
  }
}

async function handleCreate(data: Partial<CharacterDetail>) {
  try {
    await projects.createCharacter(projectId.value, data)
    showCreateForm.value = false
    ElMessage.success(`角色「${data.name}」创建成功`)
    await load()
    if (data.name) selectByName(data.name)
  } catch (e: any) {
    const msg = e?.response?.data?.detail?.detail ?? e?.message ?? '创建失败'
    ElMessage.error(msg)
  }
}

async function handleProfileSave(partial: Partial<CharacterDetail>) {
  if (!detail.value) return
  saving.value = true
  try {
    const res = await projects.updateCharacter(projectId.value, detail.value.name, partial)
    detail.value = res.data
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleSave() {
  if (!detail.value) return
  saving.value = true
  try {
    const res = await projects.updateCharacter(projectId.value, detail.value.name, detail.value)
    detail.value = res.data
    ElMessage.success('保存成功')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleDelete() {
  if (!detail.value) return
  saving.value = true
  try {
    await projects.deleteCharacter(projectId.value, detail.value.name)
    ElMessage.success(`角色「${detail.value.name}」已删除`)
    selected.value = null
    detail.value = null
    await load()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.detail ?? '删除失败')
  } finally {
    saving.value = false
  }
}

async function onTabSave(partial: Partial<CharacterDetail>) {
  if (!detail.value) return
  saving.value = true
  try {
    const res = await projects.updateCharacter(projectId.value, detail.value.name, partial)
    detail.value = res.data
    ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail?.detail ?? '保存失败')
  } finally {
    saving.value = false
  }
}

async function onConstraintSave(constraints: BehaviorConstraintDetail[]) {
  await onTabSave({ behavior_constraints: constraints })
}

async function onRelationSave(relationships: Record<string, number>) {
  await onTabSave({ relationships })
}

onMounted(load)
</script>

<style scoped>
.char-matrix { display: flex; height: 100%; gap: 16px; }
.char-detail { flex: 1; overflow-y: auto; }
.tabs { display: flex; gap: 4px; flex-wrap: wrap; }
.tab-btn { background: transparent; border: 1px solid var(--color-surface-l2); color: var(--color-text-secondary); padding: 4px 12px; border-radius: var(--radius-btn); cursor: pointer; font-size: 13px; transition: all 150ms; }
.tab-btn.active { background: var(--color-surface-l2); color: var(--color-ai-active); border-color: var(--color-ai-active); }
</style>
