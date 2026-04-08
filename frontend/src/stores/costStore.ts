import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/api/client'
import type { CostResponse } from '@/types/api'

export const useCostStore = defineStore('cost', () => {
  const cost = ref<CostResponse | null>(null)
  const loading = ref<boolean>(false)
  const error = ref<string | null>(null)

  async function fetch() {
    loading.value = true
    error.value = null
    try {
      const res = await client.get<CostResponse>('/cost')
      cost.value = res.data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : '获取用量数据失败'
    } finally {
      loading.value = false
    }
  }

  return { cost, loading, error, fetch }
})
