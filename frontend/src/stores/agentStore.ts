import { defineStore } from 'pinia'
import { ref } from 'vue'

export type AgentStatus = 'idle' | 'planning' | 'writing' | 'reviewing' | 'error'

export const useAgentStore = defineStore('agent', () => {
  const status = ref<AgentStatus>('idle')
  const currentAgent = ref<string | null>(null)
  const progress = ref<number>(0)
  const lastError = ref<string | null>(null)

  // Cost & budget tracking
  const tokenUsed = ref<number>(0)
  const tokenBudget = ref<number>(100_000)

  // Fallback strategy settings
  const maxRetries = ref<number>(2)
  const autoDowngrade = ref<boolean>(true)
  const perChapterBudget = ref<number>(20_000)
  const defaultModel = ref<string>('gpt4o')

  // Budget critical flag (set by CostDonut)
  const budgetCritical = ref<boolean>(false)

  function setRunning(agent: string) {
    status.value = 'planning'
    currentAgent.value = agent
    progress.value = 0
    lastError.value = null
  }

  function setIdle() {
    status.value = 'idle'
    currentAgent.value = null
    progress.value = 100
  }

  function setError(msg: string) {
    status.value = 'error'
    lastError.value = msg
  }

  function setBudgetCritical() {
    budgetCritical.value = true
  }

  return {
    status, currentAgent, progress, lastError,
    tokenUsed, tokenBudget,
    maxRetries, autoDowngrade, perChapterBudget, defaultModel,
    budgetCritical,
    setRunning, setIdle, setError, setBudgetCritical,
  }
})
