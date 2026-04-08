import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { projects } from '@/api/projects'
import type { ProjectListItem } from '@/types/api'

export const useProjectStore = defineStore('project', () => {
  const projectId = ref<string | null>(null)
  const projectInfo = ref<Record<string, unknown> | null>(null)
  const projectList = ref<ProjectListItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  const currentProject = computed(() =>
    projectList.value.find((p) => p.project_id === projectId.value) ?? null,
  )
  const isProjectLoaded = computed(() => projectId.value !== null && projectInfo.value !== null)

  /** 仅设置 projectId（不加载数据，用于路由守卫快速同步） */
  function setProjectId(id: string) {
    projectId.value = id
  }

  async function loadProjects() {
    loading.value = true
    try {
      const res = await projects.list()
      projectList.value = res.data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '加载项目失败'
    } finally {
      loading.value = false
    }
  }

  async function loadProjectInfo(id: string) {
    try {
      const res = await projects.status(id)
      projectInfo.value = res.data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '加载项目信息失败'
      throw e
    }
  }

  async function selectProject(id: string) {
    projectId.value = id
    await loadProjectInfo(id)
  }

  async function createProject(form: {
    project_id: string
    title?: string
    genre?: string
    description?: string
  }) {
    await projects.init({
      project_id: form.project_id,
      title: form.title ?? '',
      genre: form.genre,
      description: form.description,
    })
    await loadProjects()
    await selectProject(form.project_id)
    return form.project_id
  }

  async function updateProject(
    data: Partial<{ title: string; genre: string; description: string }>,
  ) {
    if (!projectId.value) return
    await projects.update(projectId.value, data)
    await loadProjectInfo(projectId.value)
    await loadProjects()
  }

  async function deleteProject(id: string) {
    await projects.delete(id)
    if (projectId.value === id) {
      projectId.value = null
      projectInfo.value = null
    }
    await loadProjects()
  }

  return {
    projectId,
    projectInfo,
    projectList,
    loading,
    error,
    currentProject,
    isProjectLoaded,
    setProjectId,
    loadProjects,
    loadProjectInfo,
    selectProject,
    createProject,
    updateProject,
    deleteProject,
  }
})

