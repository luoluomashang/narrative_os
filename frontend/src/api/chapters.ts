import client from './client'
import type {
  RunChapterRequest,
  RunChapterResponse,
  PlanChapterRequest,
  PlanChapterResponse,
  MetricsRequest,
  MetricsResponse,
  CheckChapterResponse,
  HumanizeResponse,
} from '@/types/api'

export const chapters = {
  run: (req: RunChapterRequest) =>
    client.post<RunChapterResponse>('/chapters/run', req),
  plan: (req: PlanChapterRequest) =>
    client.post<PlanChapterResponse>('/chapters/plan', req),
  metrics: (req: MetricsRequest) =>
    client.post<MetricsResponse>('/metrics', req),
  check: (text: string, projectId?: string, chapter?: number) =>
    client.post<CheckChapterResponse>('/chapters/check', {
      text,
      project_id: projectId ?? 'default',
      chapter: chapter ?? 0,
    }),
  humanize: (text: string, intensity?: number, projectId?: string) =>
    client.post<HumanizeResponse>('/chapters/humanize', {
      text,
      project_id: projectId ?? 'default',
      intensity: intensity ?? 0.5,
    }),
}
