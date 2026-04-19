import { flushPromises, mount, shallowMount } from '@vue/test-utils'
import { reactive, ref } from 'vue'

const { worldApi, messageSuccess, messageError, messageWarning, messageInfo, messageConfirm, messageAlert } = vi.hoisted(() => ({
  worldApi: {
    get: vi.fn(),
    powerTemplates: vi.fn(),
    updateMeta: vi.fn(),
    finalize: vi.fn(),
    previewPublish: vi.fn(),
    publish: vi.fn(),
  },
  messageSuccess: vi.fn(),
  messageError: vi.fn(),
  messageWarning: vi.fn(),
  messageInfo: vi.fn(),
  messageConfirm: vi.fn(),
  messageAlert: vi.fn(),
}))

const routeState = reactive({ params: { id: 'world-proj' } })

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
}))

vi.mock('element-plus', () => ({
  ElMessage: {
    success: (...args: unknown[]) => messageSuccess(...args),
    error: (...args: unknown[]) => messageError(...args),
    warning: (...args: unknown[]) => messageWarning(...args),
    info: (...args: unknown[]) => messageInfo(...args),
  },
  ElMessageBox: {
    confirm: (...args: unknown[]) => messageConfirm(...args),
    alert: (...args: unknown[]) => messageAlert(...args),
  },
}))

vi.mock('@vue-flow/core', () => ({
  ConnectionMode: { Loose: 'Loose' },
  VueFlow: { template: '<div><slot /></div>' },
  useVueFlow: () => ({ fitView: vi.fn() }),
}))

vi.mock('@vue-flow/background', () => ({ Background: { template: '<div />' } }))
vi.mock('@vue-flow/controls', () => ({ Controls: { template: '<div />' } }))
vi.mock('@vue-flow/minimap', () => ({ MiniMap: { template: '<div />' } }))
vi.mock('d3-force', () => ({ forceSimulation: vi.fn(() => ({ force: vi.fn().mockReturnThis(), stop: vi.fn().mockReturnThis(), tick: vi.fn() })), forceLink: vi.fn(() => ({ id: vi.fn().mockReturnThis(), distance: vi.fn().mockReturnThis(), strength: vi.fn().mockReturnThis() })), forceManyBody: vi.fn(() => ({ strength: vi.fn().mockReturnThis() })), forceCenter: vi.fn(), forceCollide: vi.fn() }))

vi.mock('@/api/world', () => ({ world: worldApi }))
vi.mock('./composables/useViewMode', () => {
  return { useViewMode: () => ({ activeView: ref('graph') }) }
})
vi.mock('./components/RegionNode.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/FactionNode.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/FactionGroupNode.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/WorldLegend.vue', () => ({
  default: {
    template: `
      <div>
        <button class="legend-highlight" @click="$emit('highlight', 'f1')">highlight</button>
        <button class="legend-select" @click="$emit('select', 'f1')">select</button>
      </div>
    `,
  },
}))
vi.mock('./components/RegionDetailPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/FactionDetailPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/PowerSystemPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/PowerSystemDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/WorldNodeDialog.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/ViewSwitcher.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/LayerViewCanvas.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/MapViewCanvas.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/TimelinePanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/ConsistencyPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/ThemeSwitcher.vue', () => ({ default: { template: '<div />' } }))

import WorldBuilder from './index.vue'

const worldDataResponse = {
  data: {
    world_name: '九州',
    world_type: 'continental',
    world_description: '描述',
    regions: [{ id: 'r1', name: '北境', region_type: 'ice', x: 0, y: 0, geography: {}, race: {}, civilization: {}, power_access: {}, faction_ids: [], tags: [], notes: '说明' }],
    factions: [{ id: 'f1', name: '宗门', scope: 'global', territory_region_ids: ['r1'], relation_map: {}, power_system_id: null, description: '', x: 1, y: 1 }],
    power_systems: [],
    relations: [{ id: 'rel1', source_id: 'r1', target_id: 'f1', relation_type: 'ally', label: '同盟', description: '' }],
    timeline_events: [],
    world_rules: [],
  },
}

describe('WorldBuilder page', () => {
  beforeEach(() => {
    worldApi.get.mockResolvedValue(worldDataResponse)
    worldApi.powerTemplates.mockResolvedValue({ data: [] })
    worldApi.updateMeta.mockResolvedValue({ data: {} })
    worldApi.finalize.mockResolvedValue({ data: { summary: { regions: 1, factions: 1, power_systems: 0, relations: 1 } } })
    worldApi.previewPublish.mockResolvedValue({ data: { status: 'ready', publish_report: { regions_compiled: 1, factions_compiled: 1, power_systems_compiled: 0, relations_compiled: 1 }, runtime_diff: { sections: [{ key: 'regions', label: '地区', items: [{ target_id: 'r1', target_name: '北境', change_type: 'update', before: '旧', after: '新', effect: '同步', note: 'note' }] }], auto_fix_notes: ['自动补齐'] }, warnings: [], suggestions: [] } })
    worldApi.publish.mockResolvedValue({ data: { status: 'published', world_version: '2.1.1', publish_report: { regions_compiled: 1, factions_compiled: 1, power_systems_compiled: 0, relations_compiled: 1 }, runtime_diff: { sections: [{ key: 'regions', label: '地区', items: [{ target_id: 'r1', target_name: '北境', change_type: 'update', before: '旧', after: '新', effect: '同步', note: 'note' }] }], auto_fix_notes: ['自动补齐'] }, warnings: [], suggestions: [] } })
    messageConfirm.mockResolvedValue(undefined)
    messageAlert.mockResolvedValue(undefined)
  })

  it('loads world data on mount', async () => {
    const wrapper = shallowMount(WorldBuilder)
    await flushPromises()

    expect(worldApi.get).toHaveBeenCalledWith('world-proj')
    expect(worldApi.powerTemplates).toHaveBeenCalledWith('world-proj')
    expect(wrapper.text()).toContain('地区1')
    expect(wrapper.text()).toContain('势力1')
  })

  it('saves world meta', async () => {
    const wrapper = shallowMount(WorldBuilder)
    await flushPromises()

    await wrapper.findAll('button')[1].trigger('click')
    await flushPromises()

    expect(worldApi.updateMeta).toHaveBeenCalledWith('world-proj', expect.objectContaining({ world_name: '九州' }))
    expect(messageSuccess).toHaveBeenCalled()
  })

  it('finalizes world and shows summary banner', async () => {
    const wrapper = shallowMount(WorldBuilder)
    await flushPromises()

    await wrapper.findAll('button')[2].trigger('click')
    await flushPromises()

    expect(worldApi.finalize).toHaveBeenCalledWith('world-proj')
    expect(messageSuccess).toHaveBeenCalledWith('世界设定已写入知识库')
  })

  it('publishes runtime world and renders diff summary', async () => {
    const wrapper = shallowMount(WorldBuilder)
    await flushPromises()

    await wrapper.findAll('button')[3].trigger('click')
    await flushPromises()

    expect(worldApi.previewPublish).toHaveBeenCalledWith('world-proj')
    expect(worldApi.publish).toHaveBeenCalledWith('world-proj')
    expect(wrapper.text()).toContain('自动补齐')
    expect(wrapper.text()).toContain('北境')
  })

  it('opens faction detail panel when selecting from legend', async () => {
    const wrapper = mount(WorldBuilder)
    await flushPromises()

    await wrapper.get('.legend-select').trigger('click')
    await flushPromises()

    expect(wrapper.text()).not.toContain('选择一个节点查看详情')
    expect(wrapper.get('.right-panel').classes()).toContain('open')
  })
})