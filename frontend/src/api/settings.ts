import client from './client'

export const settings = {
  getGlobal: () =>
    client.get<Record<string, unknown>>('/settings'),
  updateGlobal: (data: Record<string, unknown>) =>
    client.put('/settings', { settings: data }),
  getLlm: () =>
    client.get<Record<string, unknown>>('/settings/llm'),
  updateLlm: (data: Record<string, unknown>) =>
    client.put('/settings/llm', data),
  testLlm: (provider: string) =>
    client.post('/settings/llm/test', { provider }),
}
