import { defineStore } from 'pinia'
import { ref } from 'vue'
import { settings } from '@/api/settings'
import { projects } from '@/api/projects'

export const useSettingsStore = defineStore('settings', () => {
  const globalSettings = ref<Record<string, unknown>>({})
  const projectSettings = ref<Record<string, unknown>>({})
  const loading = ref(false)

  function getEffective(key: string): unknown {
    return projectSettings.value[key] ?? globalSettings.value[key] ?? undefined
  }

  async function loadGlobal() {
    loading.value = true
    try {
      const res = await settings.getGlobal()
      globalSettings.value = res.data
    } finally {
      loading.value = false
    }
  }

  async function loadProjectSettings(projectId: string) {
    try {
      const res = await projects.getSettings(projectId)
      projectSettings.value = (res.data as { merged: Record<string, unknown> }).merged ?? {}
    } catch {
      // 项目设置加载失败，不影响全局设置
    }
  }

  async function updateGlobal(data: Record<string, unknown>) {
    await settings.updateGlobal(data)
    globalSettings.value = { ...globalSettings.value, ...data }
  }

  async function updateProjectSettings(projectId: string, data: Record<string, unknown>) {
    await projects.updateSettings(projectId, data)
    projectSettings.value = { ...projectSettings.value, ...data }
  }

  return {
    globalSettings,
    projectSettings,
    loading,
    getEffective,
    loadGlobal,
    loadProjectSettings,
    updateGlobal,
    updateProjectSettings,
  }
})
