import client from './client'
import type { CostSummaryResponse, CostHistoryItem } from '@/types/api'

export const cost = {
  summary: (project_id?: string) =>
    client.get<CostSummaryResponse>('/cost/summary', { params: project_id ? { project_id } : {} }),
  history: (days?: number, project_id?: string) =>
    client.get<CostHistoryItem[]>('/cost/history', {
      params: { days: days ?? 7, ...(project_id ? { project_id } : {}) },
    }),
}
