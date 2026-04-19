<template>
  <el-dialog
    :model-value="modelValue"
    width="680px"
    top="12vh"
    class="shell-command-palette"
    :show-close="false"
    :destroy-on-close="false"
    @close="emit('update:modelValue', false)"
  >
    <template #header>
      <div class="shell-command-palette__header">
        <span class="shell-command-palette__eyebrow">Ctrl/Cmd + K</span>
        <h2 class="shell-command-palette__title">命令面板</h2>
      </div>
    </template>

    <div class="shell-command-palette__body">
      <el-input
        ref="inputRef"
        v-model="keyword"
        placeholder="搜索页面、项目或高频动作"
        size="large"
        clearable
      />

      <div class="shell-command-palette__list" role="listbox" aria-label="命令面板结果">
        <button
          v-for="item in filteredActions"
          :key="item.id"
          class="shell-command-palette__item"
          @click="navigate(item.to)"
        >
          <div class="shell-command-palette__item-copy">
            <strong>{{ item.label }}</strong>
            <span>{{ item.description }}</span>
          </div>
          <span class="shell-command-palette__item-tag">{{ item.group }}</span>
        </button>

        <p v-if="!filteredActions.length" class="shell-command-palette__empty">
          没有匹配结果，试试搜索工作区、页面标题或项目名。
        </p>
      </div>
    </div>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useProjectStore } from '@/stores/projectStore'
import {
  buildProjectPath,
  getGlobalPath,
  globalNavigation,
  projectWorkspaces,
} from '@/config/shellNavigation'

interface CommandAction {
  id: string
  label: string
  description: string
  group: string
  to: string
}

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
}>()

const router = useRouter()
const projectStore = useProjectStore()
const keyword = ref('')
const inputRef = ref<{ focus: () => void } | null>(null)

const actions = computed<CommandAction[]>(() => {
  const globalActions = globalNavigation.map((item) => ({
    id: `global-${item.id}`,
    label: item.label,
    description: item.description,
    group: '全局',
    to: getGlobalPath(item),
  }))

  const projectActions = projectStore.projectId
    ? projectWorkspaces.flatMap((workspace) =>
        workspace.items.map((item) => ({
          id: `project-${workspace.id}-${item.id}`,
          label: item.label,
          description: item.description,
          group: workspace.label,
          to: buildProjectPath(projectStore.projectId as string, item.segment),
        })),
      )
    : []

  const projectTargets = projectStore.projectList.slice(0, 8).map((project) => ({
    id: `project-target-${project.project_id}`,
    label: project.title || project.project_id,
    description: `切换到项目 ${project.project_id}`,
    group: '项目',
    to: buildProjectPath(project.project_id),
  }))

  return [...globalActions, ...projectActions, ...projectTargets]
})

const filteredActions = computed(() => {
  const normalized = keyword.value.trim().toLowerCase()
  if (!normalized) return actions.value

  return actions.value.filter((item) => {
    const content = `${item.label} ${item.description} ${item.group}`.toLowerCase()
    return content.includes(normalized)
  })
})

watch(
  () => props.modelValue,
  async (isOpen) => {
    if (!isOpen) {
      keyword.value = ''
      return
    }

    if (!projectStore.projectList.length) {
      await projectStore.loadProjects()
    }

    await nextTick()
    inputRef.value?.focus()
  },
)

function navigate(target: string) {
  emit('update:modelValue', false)
  router.push(target)
}

function handleKeydown(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    emit('update:modelValue', !props.modelValue)
  }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
})

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown)
})
</script>

<style scoped>
.shell-command-palette__header {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-1);
}

.shell-command-palette__eyebrow {
  font-size: var(--text-caption);
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.shell-command-palette__title {
  margin: 0;
  font-size: 1.4rem;
  color: var(--color-text-1);
}

.shell-command-palette__body {
  display: grid;
  gap: var(--spacing-4);
}

.shell-command-palette__list {
  display: grid;
  gap: var(--spacing-2);
  max-height: 52vh;
  overflow: auto;
}

.shell-command-palette__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-3);
  width: 100%;
  padding: var(--spacing-4);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    border-color 150ms ease,
    transform 150ms ease,
    background 150ms ease;
}

.shell-command-palette__item:hover {
  transform: translateY(-1px);
  border-color: color-mix(in srgb, var(--color-accent) 18%, transparent);
  background: var(--color-surface-2);
}

.shell-command-palette__item-copy {
  display: grid;
  gap: 4px;
}

.shell-command-palette__item-copy strong {
  color: var(--color-text-1);
}

.shell-command-palette__item-copy span {
  color: var(--color-text-2);
  line-height: 1.5;
}

.shell-command-palette__item-tag {
  flex-shrink: 0;
  padding: 6px 10px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: var(--text-caption);
}

.shell-command-palette__empty {
  margin: 0;
  padding: var(--spacing-6) var(--spacing-4);
  text-align: center;
  color: var(--color-text-2);
}

:deep(.shell-command-palette .el-dialog) {
  border-radius: var(--radius-xl);
}

@media (max-width: 768px) {
  :deep(.shell-command-palette .el-dialog) {
    width: calc(100vw - 24px) !important;
    margin: 12px auto;
  }
}
</style>