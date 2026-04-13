import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const routeState = reactive({ params: { id: 'proj-trpg' } })
const previewArchivesMock = vi.fn()
const createSaveMock = vi.fn()
const listSavesMock = vi.fn()
const loadSaveMock = vi.fn()
const deleteSaveMock = vi.fn()
const setControlModeMock = vi.fn()

const store = reactive({
  sessionId: '',
  phase: 'INIT',
  loading: false,
  summary: null as any,
  turn: 0,
  history: [] as any[],
  scenePressure: 5,
  emotionalTemperature: { current: 5, drift: 0 },
  density: 'normal' as 'dense' | 'normal' | 'sparse',
  createSession: vi.fn(),
  sendStep: vi.fn(),
  triggerBangui: vi.fn(),
  rollback: vi.fn(),
  endSession: vi.fn(),
  reset: vi.fn(),
})

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
}))

vi.mock('@/stores/sessionStore', () => ({
  useSessionStore: () => store,
}))

vi.mock('@/composables/useToast', () => ({
  useToast: () => ({ add: vi.fn() }),
}))

vi.mock('@/api/sessions', () => ({
  sessions: {
    previewArchives: (...args: unknown[]) => previewArchivesMock(...args),
    createSave: (...args: unknown[]) => createSaveMock(...args),
    listSaves: (...args: unknown[]) => listSavesMock(...args),
    loadSave: (...args: unknown[]) => loadSaveMock(...args),
    deleteSave: (...args: unknown[]) => deleteSaveMock(...args),
    setControlMode: (...args: unknown[]) => setControlModeMock(...args),
  },
}))

vi.mock('@/components/common/NTypewriter.vue', () => ({
  default: {
    props: ['text'],
    template: '<div class="typewriter">{{ text }}</div>',
  },
}))

import TRPGPanel from './index.vue'

describe('TRPGPanel page', () => {
  beforeEach(() => {
    store.sessionId = ''
    store.phase = 'INIT'
    store.loading = false
    store.summary = null
    store.turn = 0
    store.history = []
    store.scenePressure = 5
    store.emotionalTemperature = { current: 5, drift: 0 }
    previewArchivesMock.mockResolvedValue({ data: { session_id: 'sid', preview_session_only: { summary: '归档摘要', memory_anchors: [], character_changes: [], projected_changeset_status: 'runtime_only' }, preview_draft_chapter: { chapter_text: '', excerpt: '片段', word_count: 1200, quality_estimate: 'A' }, preview_canon_chapter: { draft_content: '', pending_changes: [], approval_required_fields: ['世界设定'], requires_confirmation: true, projected_changeset_status: 'canon_pending' } } })
    createSaveMock.mockReset()
    listSavesMock.mockReset()
    loadSaveMock.mockReset()
    deleteSaveMock.mockReset()
    setControlModeMock.mockReset()
  })

  it('shows init screen before session starts', () => {
    const wrapper = mount(TRPGPanel)
    expect(wrapper.text()).toContain('TRPG 互动模式')
    expect(wrapper.text()).toContain('开始会话')
  })

  it('renders ended summary with archive preview', async () => {
    store.phase = 'ENDED'
    store.summary = {
      duration_minutes: 12,
      turn_count: 8,
      bangui_count: 2,
      next_hook: '下一章钩子',
      character_delta: [{ name: '主角', change: '觉醒' }],
      preview_session_only: { summary: '本次会话摘要', memory_anchors: [{ label: '锚点' }], character_changes: [], projected_changeset_status: 'runtime_only' },
      preview_draft_chapter: { chapter_text: '', excerpt: '节选', word_count: 1500, quality_estimate: 'A-' },
      preview_canon_chapter: { draft_content: '', pending_changes: [{ change_type: 'canon', description: '变更' }], approval_required_fields: ['角色'], requires_confirmation: true, projected_changeset_status: 'canon_pending' },
    }

    const wrapper = mount(TRPGPanel)
    expect(wrapper.text()).toContain('会话总结')
    expect(wrapper.text()).toContain('下一章钩子')
    expect(wrapper.text()).toContain('本次会话摘要')
    expect(wrapper.text()).toContain('锚点')
  })

  it('sanitizes noisy summary hook and archive preview text', () => {
    store.phase = 'ENDED'
    store.summary = {
      duration_minutes: 1,
      turn_count: 3,
      bangui_count: 0,
      next_hook: '线索落在黑虎帮手里 | [选项 A]：追问 [选项 B]：离开',
      character_delta: [],
      preview_session_only: {
        summary: '你睁开眼，发现自己正躺在牛车上。** [选项 A]：追问 [选项 B]：离开',
        memory_anchors: [],
        character_changes: [],
        projected_changeset_status: 'runtime_only',
      },
      preview_draft_chapter: { chapter_text: '', excerpt: '“多谢老丈。”| [选项 A]：继续', word_count: 800, quality_estimate: 'B+' },
      preview_canon_chapter: { draft_content: '', pending_changes: [], approval_required_fields: [], requires_confirmation: true, projected_changeset_status: 'canon_pending' },
    }

    const wrapper = mount(TRPGPanel)
    expect(wrapper.text()).toContain('线索落在黑虎帮手里')
    expect(wrapper.text()).not.toContain('[选项 A]')
    expect(wrapper.text()).not.toContain('**')
    expect(wrapper.text()).toContain('你睁开眼，发现自己正躺在牛车上。')
  })

  it('renders active session options and pressure state', () => {
    store.sessionId = 'sid-1'
    store.phase = 'PING_PONG'
    store.turn = 4
    store.scenePressure = 8.5
    store.history = [
      {
        turn_id: 4,
        who: 'dm',
        content: '[选项 A]：冲进去 [选项 B]：先观察',
        rolled_back: false,
        has_decision: false,
      },
    ]

    const wrapper = mount(TRPGPanel)
    expect(wrapper.text()).toContain('回合 4')
    expect(wrapper.find('.typewriter').text()).toContain('[选项 A]：冲进去')
    expect(wrapper.text()).toContain('冲进去')
    expect(wrapper.text()).toContain('先观察')
    expect(wrapper.text()).toContain('8.5')
    expect(wrapper.text()).toContain('帮回指令')
    expect(wrapper.text()).toContain('主动介入')
    expect(wrapper.text()).toContain('快速推进')
    expect(wrapper.text()).toContain('立刻插入外部动作，打破僵局')
  })

  it('hydrates DM narrative from the latest active history record', () => {
    store.sessionId = 'sid-history'
    store.phase = 'PING_PONG'
    store.turn = 2
    store.history = [
      { turn_id: 0, who: 'dm', content: '开场白', rolled_back: false, has_decision: false },
      { turn_id: 1, who: 'user', content: '我先观察四周', rolled_back: false, has_decision: false },
      { turn_id: 2, who: 'dm', content: '风从荒草间掠过，马车外传来金属碰撞声。', rolled_back: false, has_decision: false },
    ]

    const wrapper = mount(TRPGPanel)
    expect(wrapper.find('.typewriter').text()).toContain('风从荒草间掠过')
    expect(wrapper.find('.typewriter').text()).not.toContain('我先观察四周')
  })

  it('sanitizes markdown markers in streamed options and history', () => {
    store.sessionId = 'sid-3'
    store.phase = 'PING_PONG'
    store.turn = 2
    store.history = [
      {
        turn_id: 2,
        who: 'dm',
        content: '局势骤然紧张。**[选项 A]**：**冲进去** **[选项 B]**：先观察',
        rolled_back: false,
        has_decision: true,
        decision_options: ['**冲进去**', '先观察**'],
      },
    ]

    const wrapper = mount(TRPGPanel)
    expect(wrapper.text()).toContain('冲进去')
    expect(wrapper.text()).toContain('先观察')
    expect(wrapper.text()).not.toContain('**')
  })

  it('loads archive preview when ending a session', async () => {
    store.sessionId = 'sid-2'
    store.phase = 'PING_PONG'

    const wrapper = mount(TRPGPanel)
    await wrapper.get('.n-btn.danger.sm').trigger('click')
    await flushPromises()

    expect(previewArchivesMock).toHaveBeenCalledWith('sid-2')
  })

  it('converts save turns to UI rounds and restores local history on load', async () => {
    store.sessionId = 'sid-4'
    store.phase = 'PING_PONG'
    store.turn = 3
    store.scenePressure = 4
    store.history = [
      { turn_id: 0, who: 'dm', content: '开场', rolled_back: false, has_decision: false },
      { turn_id: 2, who: 'dm', content: '第二回合', rolled_back: false, has_decision: false },
      { turn_id: 4, who: 'dm', content: '第三回合', rolled_back: false, has_decision: false },
    ]
    listSavesMock.mockResolvedValue({ data: [{ save_id: 'save-1', trigger: 'manual', timestamp: '2026-04-12T09:25:00', turn: 3, scene_pressure: 4 }] })
    loadSaveMock.mockResolvedValue({ data: { save_id: 'save-1', restored_turn: 3, memory_summary_preserved: true } })

    const wrapper = mount(TRPGPanel)
    await wrapper.findAll('.n-btn.ghost.sm')[1].trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('回合 2')

    await wrapper.get('.sl-actions .n-btn.primary.sm').trigger('click')
    await flushPromises()

    expect(store.turn).toBe(2)
    expect(store.history[2].rolled_back).toBe(true)
    expect(wrapper.text()).toContain('已读档至回合 2')
  })

  it('keeps only one rollback radio selected by default', async () => {
    store.sessionId = 'sid-5'
    store.phase = 'PING_PONG'

    const wrapper = mount(TRPGPanel)
    await wrapper.findAll('.n-btn.ghost.sm')[2].trigger('click')
    await flushPromises()

    expect(wrapper.findAll('input[type="radio"]:checked')).toHaveLength(1)
  })
})