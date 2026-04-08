import { ref, onUnmounted } from 'vue'
import client from '@/api/client'
import type { CostResponse } from '@/types/api'

export function useTokenCost(interval = 30_000) {
  const cost = ref<CostResponse | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function fetch() {
    loading.value = true
    try {
      const res = await client.get<CostResponse>('/cost')
      cost.value = res.data
    } catch (e: unknown) {
      error.value = e instanceof Error ? e.message : 'fetch error'
    } finally {
      loading.value = false
    }
  }

  fetch()
  const timer = setInterval(fetch, interval)

  onUnmounted(() => {
    clearInterval(timer)
  })

  return { cost, loading, error, fetch }
}
