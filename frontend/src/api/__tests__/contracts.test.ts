import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'

import client from '../client'
import { chapters } from '../chapters'
import { projects } from '../projects'
import { world } from '../world'

const server = setupServer()

beforeAll(() => {
  client.defaults.baseURL = 'http://localhost/api'
  server.listen({ onUnhandledRequest: 'error' })
})

afterEach(() => {
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})

describe('frontend api contracts', () => {
  it('posts chapter plan payload with expected fields', async () => {
    server.use(
      http.post('http://localhost/api/chapters/plan', async ({ request }) => {
        const body = await request.json() as Record<string, unknown>
        expect(body).toMatchObject({ chapter: 3, volume: 1, project_id: 'proj' })
        return HttpResponse.json({ chapter_outline: 'outline', planned_nodes: [], dialogue_goals: [], hook_suggestion: '', hook_type: 'suspense', tension_curve: [] })
      }),
    )

    const response = await chapters.plan({ chapter: 3, volume: 1, target_summary: 'summary', word_count_target: 1800, previous_hook: '', project_id: 'proj', character_names: [], world_rules: [], constraints: [] })
    expect(response.data.chapter_outline).toBe('outline')
  })

  it('requests writing context through projects status endpoint params', async () => {
    server.use(
      http.get('http://localhost/api/projects/proj-1/status', () => HttpResponse.json({ pending_changes_count: 4 })),
    )

    const response = await projects.status('proj-1')
    expect(response.data.pending_changes_count).toBe(4)
  })

  it('normalizes world preview publish response', async () => {
    server.use(
      http.post('http://localhost/api/projects/proj-1/world/publish-preview', () => HttpResponse.json({ status: 'ready', warnings: [], suggestions: [], publish_report: { regions_compiled: 1, factions_compiled: 2, power_systems_compiled: 0, timeline_events_compiled: 0, relations_compiled: 3 }, runtime_diff: { sections: [], auto_fix_notes: [] } })),
    )

    const response = await world.previewPublish('proj-1')
    expect(response.data.status).toBe('ready')
    expect(response.data.publish_report?.relations_compiled).toBe(3)
  })
})