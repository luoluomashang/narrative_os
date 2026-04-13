import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const pushMock = vi.fn()
const routeState = reactive({ params: { id: 'proj-alpha' }, query: { chapter: '3' } })

const projectStatusMock = vi.fn()
const writingContextMock = vi.fn()
const chapterRunMock = vi.fn()
const chapterPlanMock = vi.fn()
const clientGetMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('@/api/projects', () => ({
  projects: {
    status: (...args: unknown[]) => projectStatusMock(...args),
  },
}))

vi.mock('@/api/chapters', () => ({
  chapters: {
    writingContext: (...args: unknown[]) => writingContextMock(...args),
    run: (...args: unknown[]) => chapterRunMock(...args),
    plan: (...args: unknown[]) => chapterPlanMock(...args),
  },
}))

vi.mock('@/api/client', () => ({
  default: {
    get: (...args: unknown[]) => clientGetMock(...args),
  },
}))

import WritingPage from './index.vue'

const makeContext = () => ({
  data: {
    project_id: 'proj-alpha',
    chapter: 3,
    previous_hook: '旧钩子',
    current_volume_goal: '卷目标',
    pending_changes_count: 2,
    world: { published: true, factions: ['宗门'], regions: ['北境'], rules: ['禁术'] },
    characters: [
      {
        name: '主角',
        current_location: '北境',
        current_agenda: '调查',
        current_pressure: 0.8,
        recent_key_events: ['入城'],
      },
    ],
    prechecks: [{ key: 'world', passed: true, severity: 'info', message: 'ok' }],
  },
})

describe('Writing page', () => {
  beforeEach(() => {
    projectStatusMock.mockResolvedValue({ data: { pending_changes_count: 2 } })
    writingContextMock.mockResolvedValue(makeContext())
    clientGetMock.mockResolvedValue({
      data: {
        status: 'completed',
        steps: [
          {
            step_id: 'step-1',
            step_index: 1,
            agent_name: 'planner',
            status: 'completed',
            artifact: { token_in: 12, token_out: 24 },
          },
        ],
      },
    })
  })

  it('hydrates workbench data on mount', async () => {
    const wrapper = mount(WritingPage)
    await flushPromises()

    expect(projectStatusMock).toHaveBeenCalledWith('proj-alpha')
    expect(writingContextMock).toHaveBeenCalledWith('proj-alpha', 3)
    expect(wrapper.text()).toContain('待确认变更 2')
    expect(wrapper.text()).toContain('已发布')
    expect(wrapper.text()).toContain('主角')
  })

  it('routes precheck action via router push', async () => {
    writingContextMock.mockResolvedValue({
      data: {
        ...makeContext().data,
        prechecks: [{ key: 'fix', passed: false, severity: 'warning', message: 'go', action_path: '/world' }],
      },
    })
    const wrapper = mount(WritingPage)
    await flushPromises()

    await wrapper.get('.link-btn').trigger('click')
    expect(pushMock).toHaveBeenCalledWith('/world')
  })

  it('renders plan output after clicking plan only', async () => {
    chapterPlanMock.mockResolvedValue({ data: { chapter_outline: '规划结果', planned_nodes: [], hook_suggestion: '', hook_type: 'suspense', tension_curve: [], dialogue_goals: [] } })
    const wrapper = mount(WritingPage)
    await flushPromises()

    await wrapper.get('textarea').setValue('本章摘要')
    await wrapper.findAll('.ghost-btn')[1].trigger('click')
    await flushPromises()

    expect(chapterPlanMock).toHaveBeenCalled()
    expect(wrapper.text()).toContain('规划结果')
  })

  it('formats structured plan payloads into readable sections', async () => {
    chapterPlanMock.mockResolvedValue({
      data: {
        chapter_outline: '```json\n{"outline":"沈砚发现疆图缺口","nodes":[{"id":"n1"}]}\n```',
        planned_nodes: [{ id: 'n1', type: 'setup', summary: '核对疆图', tension: 0.2, characters: ['沈砚'] }],
        hook_suggestion: '禁库里还藏着第二份底稿',
        hook_type: 'suspense',
        tension_curve: [0.2, 0.6, 0.9],
        dialogue_goals: ['突出沈砚的怀疑与克制'],
      },
    })
    const wrapper = mount(WritingPage)
    await flushPromises()

    await wrapper.get('textarea').setValue('本章摘要')
    await wrapper.findAll('.ghost-btn')[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('剧情骨架')
    expect(wrapper.text()).toContain('沈砚发现疆图缺口')
    expect(wrapper.text()).toContain('[setup] 核对疆图')
    expect(wrapper.text()).toContain('Hook 建议: 禁库里还藏着第二份底稿')
    expect(wrapper.text()).toContain('张力曲线: 0.2 → 0.6 → 0.9')
  })

  it('blocks planning when target summary is empty', async () => {
    const wrapper = mount(WritingPage)
    await flushPromises()

    expect(wrapper.findAll('.ghost-btn')[1].attributes('disabled')).toBeDefined()
    expect(chapterPlanMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('生成结果会显示在这里。')
  })

  it('renders generated text and run telemetry after generation', async () => {
    chapterRunMock.mockResolvedValue({ data: { text: '生成正文', run_id: 'run-123' } })
    const wrapper = mount(WritingPage)
    await flushPromises()

    const textarea = wrapper.get('textarea')
    await textarea.setValue('本章摘要')
    const primaryButtons = wrapper.findAll('.primary-btn')
    await primaryButtons[0].trigger('click')
    await flushPromises()

    expect(chapterRunMock).toHaveBeenCalled()
    expect(clientGetMock).toHaveBeenCalledWith('/runs/run-123/steps')
    expect(wrapper.text()).toContain('生成正文')
    expect(wrapper.text()).toContain('12 / 输出 24')
  })

  it('shows error banner when generation fails', async () => {
    chapterRunMock.mockRejectedValue(new Error('boom'))
    const wrapper = mount(WritingPage)
    await flushPromises()

    await wrapper.get('textarea').setValue('本章摘要')
    await wrapper.findAll('.primary-btn')[0].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('boom')
    expect(wrapper.text()).toContain('失败')
  })

  it('shows validation error when generate is called without summary', async () => {
    const wrapper = mount(WritingPage)
    await flushPromises()

    const vm = wrapper.vm as unknown as { generate: () => Promise<void> }
    await vm.generate()
    await flushPromises()

    expect(chapterRunMock).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('请先填写本章摘要')
    expect(wrapper.text()).toContain('未启动')
  })
})