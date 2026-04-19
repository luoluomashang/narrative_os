<template>
  <div class="char-page app-page-surface">
    <SystemPageHeader
      eyebrow="Character Matrix"
      title="角色矩阵"
      description="集中编辑角色档案、关系、Drive 与 Runtime，减少在多个页面间来回切换造成的上下文割裂。"
    >
      <template #meta>
        <span class="app-pill">项目 {{ projectId }}</span>
        <span class="app-pill app-pill--accent">角色 {{ characters.length }}</span>
        <span class="app-pill">当前 {{ selected?.name || '未选择' }}</span>
        <span v-if="selected && detail" class="app-pill">完整 {{ completedLayerCount }}/4</span>
      </template>
    </SystemPageHeader>

    <div class="char-matrix">
      <div v-if="error" class="char-error">
        <SystemErrorState
          title="角色矩阵加载失败"
          :message="error"
          action-label="重试"
          @action="load"
        />
      </div>
      <template v-else>
        <CharacterList
          :characters="characters"
          :selected="selected?.name ?? null"
          @select="selectByName"
          @create="showCreateForm = true"
        />

        <div class="char-detail">
          <div v-if="selected && detail">
            <div class="detail-toolbar">
              <div class="section-switch">
                <SystemButton
                  v-for="section in sections"
                  :key="section.id"
                  size="sm"
                  :variant="activeSection === section.id ? 'secondary' : 'ghost'"
                  @click="activeSection = section.id"
                >
                  {{ section.label }}
                </SystemButton>
              </div>
              <p class="section-description">{{ activeSectionDescription }}</p>
            </div>

            <SystemCard
              class="detail-overview-card"
              title="四层状态总览"
              description="先看完整度，再进入具体编辑区，减少标签切换密度。"
              tone="subtle"
            >
              <div class="detail-overview-grid">
                <div v-for="item in detailCompletionItems" :key="item.key" class="detail-overview-item">
                  <span>{{ item.label }}</span>
                  <strong :class="{ 'is-complete': item.complete }">{{ item.status }}</strong>
                  <small>{{ item.detail }}</small>
                </div>
              </div>
            </SystemCard>

            <div class="detail-stack">
              <template v-if="activeSection === 'profile'">
                <SystemCard title="角色档案">
                  <ProfileTab :model="detail" :loading="saving" @save="handleProfileSave" @delete="handleDelete" />
                </SystemCard>
                <SystemCard title="当前状态">
                  <StateTab :model="detail" />
                </SystemCard>
              </template>

              <template v-else-if="activeSection === 'constraints'">
                <SystemCard title="限制规则">
                  <ConstraintTab :model="detail" :loading="saving" @save="onConstraintSave" />
                </SystemCard>
                <SystemCard title="动机与冲突">
                  <MotivationTab :model="detail" :loading="saving" @save="onTabSave" />
                </SystemCard>
              </template>

              <template v-else-if="activeSection === 'relationships'">
                <SystemCard title="角色关系">
                  <RelationTab :model="detail" :loading="saving" :all-characters="characters" @save="onRelationSave" />
                </SystemCard>
                <SystemCard title="Social 矩阵">
                  <SocialMatrixTab :model="detail" :loading="saving" @save="onTabSave" />
                </SystemCard>
              </template>

              <template v-else-if="activeSection === 'style'">
                <SystemCard title="对话口吻">
                  <DialogueTab :model="detail" :loading="saving" :project-id="projectId" @save="onTabSave" />
                </SystemCard>
                <SystemCard title="Drive">
                  <DriveTab :model="detail" :loading="saving" @save="onTabSave" />
                </SystemCard>
              </template>

              <SystemCard v-else title="Runtime">
                <RuntimeTab :model="detail" />
              </SystemCard>
            </div>
          </div>
          <SystemCard v-else-if="loading" class="detail-loading-card">
            <SystemSkeleton :rows="8" show-header />
          </SystemCard>
          <SystemCard v-else class="detail-empty-card" tone="subtle">
            <SystemEmpty
              title="从左侧选择角色"
              description="选择已有角色查看详情，或直接创建一个新角色开始编辑。"
            />
          </SystemCard>
        </div>
      </template>
    </div>

    <CharacterForm :visible="showCreateForm" @close="showCreateForm = false" @submit="handleCreate" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
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
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import type { CharacterSummary, CharacterDetail, BehaviorConstraintDetail } from '@/types/api'

const route = useRoute()
const projectId = computed(() => (route.params.id as string) || 'default')

const loading = ref(false)
const saving = ref(false)
const error = ref<string | null>(null)
const characters = ref<CharacterSummary[]>([])
const selected = ref<CharacterSummary | null>(null)
const detail = ref<CharacterDetail | null>(null)
type SectionId = 'profile' | 'constraints' | 'relationships' | 'style' | 'runtime'

const activeSection = ref<SectionId>('profile')
const sections: Array<{ id: SectionId; label: string; description: string }> = [
  { id: 'profile', label: '档案概览', description: '先确认角色身份、档案和当前状态，再进入更深层编辑。' },
  { id: 'constraints', label: '限制与动机', description: '收束行为限制、冲突来源和行动边界。' },
  { id: 'relationships', label: '关系网络', description: '统一维护角色关系和 Social 矩阵，避免分散切换。' },
  { id: 'style', label: '风格驱动', description: '集中调整对话口吻和 Drive 层驱动方式。' },
  { id: 'runtime', label: '运行态', description: '查看当前 Runtime 快照，不与编辑表单混排。' },
]
const showCreateForm = ref(false)

const activeSectionDescription = computed(
  () => sections.find((section) => section.id === activeSection.value)?.description ?? '',
)

const detailCompletionItems = computed(() => {
  if (!detail.value) {
    return []
  }

  const model = detail.value as unknown as Record<string, unknown>
  const relationshipCount = countFilledEntries(model.relationships)
  const dialogueCount = countFilledEntries(model.dialogue_examples)
  const motivationCount = countFilledEntries(model.motivations)

  const personaReady = hasFilledValue(model, ['role', 'summary', 'description', 'background', 'persona']) || dialogueCount > 0
  const driveReady = hasFilledValue(model, ['drive', 'core_belief', 'motivation']) || motivationCount > 0
  const socialReady = relationshipCount > 0 || hasFilledValue(model, ['social_matrix', 'relationship_profile'])
  const runtimeReady = hasFilledValue(model, ['current_location', 'current_agenda', 'runtime', 'runtime_state', 'emotional_state'])

  return [
    {
      key: 'persona',
      label: 'Persona',
      status: personaReady ? '已就绪' : '待补充',
      detail: personaReady ? `已沉淀 ${Math.max(dialogueCount, 1)} 份档案线索` : '补充基础档案与口吻样例',
      complete: personaReady,
    },
    {
      key: 'drive',
      label: 'Drive',
      status: driveReady ? '已就绪' : '待补充',
      detail: driveReady ? `已记录 ${Math.max(motivationCount, 1)} 条动机/驱动信息` : '补充动机、冲突与驱动力',
      complete: driveReady,
    },
    {
      key: 'social',
      label: 'Social',
      status: socialReady ? '已就绪' : '待补充',
      detail: socialReady ? `已维护 ${Math.max(relationshipCount, 1)} 条关系线索` : '补充关系网络和 Social 矩阵',
      complete: socialReady,
    },
    {
      key: 'runtime',
      label: 'Runtime',
      status: runtimeReady ? '已就绪' : '待补充',
      detail: runtimeReady ? '已有位置、议程或运行态快照' : '补充当前状态与实时上下文',
      complete: runtimeReady,
    },
  ]
})

const completedLayerCount = computed(() => detailCompletionItems.value.filter((item) => item.complete).length)

function hasFilledValue(record: Record<string, unknown>, keys: string[]) {
  return keys.some((key) => {
    const value = record[key]
    if (typeof value === 'string') return value.trim().length > 0
    if (Array.isArray(value)) return value.length > 0
    if (value && typeof value === 'object') return Object.keys(value as Record<string, unknown>).length > 0
    return Boolean(value)
  })
}

function countFilledEntries(value: unknown) {
  if (Array.isArray(value)) {
    return value.length
  }

  if (value && typeof value === 'object') {
    return Object.keys(value as Record<string, unknown>).length
  }

  return 0
}

function readRequestedCharacterName() {
  const candidate = route.query.name ?? route.query.character
  return typeof candidate === 'string' ? candidate.trim() : ''
}

async function load() {
  loading.value = true
  error.value = null
  try {
    const res = await projects.characters(projectId.value)
    characters.value = res.data
    const requestedName = readRequestedCharacterName()
    const nextSelected = requestedName && res.data.some((item) => item.name === requestedName)
      ? requestedName
      : selected.value && res.data.some((item) => item.name === selected.value?.name)
        ? selected.value.name
        : res.data[0]?.name

    if (nextSelected) {
      await selectByName(nextSelected)
    } else {
      selected.value = null
      detail.value = null
    }
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
  activeSection.value = 'profile'
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

watch(
  () => [route.query.name, route.query.character],
  async () => {
    const requestedName = readRequestedCharacterName()
    if (!requestedName) return
    if (!characters.value.some((item) => item.name === requestedName)) return
    if (selected.value?.name === requestedName) return
    await selectByName(requestedName)
  },
)
</script>

<style scoped>
.char-page {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-6);
  min-height: 0;
}

.char-matrix {
  display: flex;
  min-height: 0;
  flex: 1;
  gap: 16px;
}

.char-detail {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.char-error {
  width: 100%;
}

.detail-toolbar {
  display: grid;
  gap: 10px;
  margin-bottom: 12px;
}

.section-switch {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.section-description {
  margin: 0;
  color: var(--color-text-3);
  font-size: 13px;
  line-height: 1.6;
}

.detail-overview-card :deep(.system-card__body) {
  gap: 14px;
}

.detail-overview-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.detail-overview-item {
  display: grid;
  gap: 4px;
  padding: 12px;
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 92%, transparent);
}

.detail-overview-item span {
  color: var(--color-text-3);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.detail-overview-item strong {
  color: var(--color-warning);
}

.detail-overview-item strong.is-complete {
  color: var(--color-success);
}

.detail-overview-item small {
  color: var(--color-text-2);
  line-height: 1.5;
}

.detail-stack {
  display: grid;
  gap: 12px;
}

.detail-loading-card,
.detail-empty-card {
  flex: 1;
}

.detail-empty-card :deep(.system-card__body) {
  min-height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 960px) {
  .char-matrix {
    flex-direction: column;
  }

  .detail-overview-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .detail-overview-grid {
    grid-template-columns: 1fr;
  }
}
</style>
