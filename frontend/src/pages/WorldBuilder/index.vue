<template>
  <div class="sandbox-page" :data-theme="worldData.world_type || 'continental'" :data-wb-theme="currentTheme">
    <header class="sandbox-header">
      <div>
        <h2 class="sandbox-title">世界观沙盘</h2>
        <p class="sandbox-subtitle">可视化编辑地区、势力与关系网络</p>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="loadWorld">刷新</el-button>
        <el-button type="success" :loading="finalizing" @click="finalizeWorld">完成世界设定</el-button>
        <el-button type="primary" :loading="savingMeta" @click="saveMeta">保存世界信息</el-button>
      </div>
    </header>

    <el-alert
      v-if="finalizeSummary"
      type="success"
      show-icon
      :closable="true"
      class="finalize-alert"
      :title="`已写入知识库：地区 ${finalizeSummary.regions} / 势力 ${finalizeSummary.factions} / 体系 ${finalizeSummary.power_systems} / 关系 ${finalizeSummary.relations}`"
    />

    <div class="sandbox-layout">
      <aside class="left-panel">
        <el-card shadow="never" class="panel-card">
          <template #header>世界信息</template>
          <el-form label-position="top" size="small">
            <el-form-item label="世界名称">
              <el-input v-model="worldData.world_name" placeholder="例如：九州天玄界" />
            </el-form-item>
            <el-form-item label="世界类型">
              <el-select v-model="worldData.world_type" style="width: 100%">
                <el-option label="大陆流" value="continental" />
                <el-option label="位面/世界流" value="planar" />
                <el-option label="星际/宇宙流" value="interstellar" />
                <el-option label="多层世界" value="multi_layer" />
              </el-select>
            </el-form-item>
            <el-form-item label="世界描述">
              <el-input v-model="worldData.world_description" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>节点操作</template>
          <div class="toolbar-actions">
            <el-button type="primary" plain @click="openCreateDialog('region')">+ 地区</el-button>
            <el-button type="warning" plain @click="openCreateDialog('faction')">+ 势力</el-button>
            <el-button type="success" plain @click="powerDialogVisible = true">+ 力量体系</el-button>
          </div>
          <el-divider />
          <div class="stats-grid">
            <div class="stat-item">
              <span>地区</span>
              <strong>{{ worldData.regions.length }}</strong>
            </div>
            <div class="stat-item">
              <span>势力</span>
              <strong>{{ worldData.factions.length }}</strong>
            </div>
            <div class="stat-item">
              <span>体系</span>
              <strong>{{ worldData.power_systems.length }}</strong>
            </div>
            <div class="stat-item">
              <span>关系</span>
              <strong>{{ worldData.relations.length }}</strong>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="panel-card">
          <template #header>关系批量编辑</template>
          <el-form label-position="top" size="small">
            <el-form-item label="筛选关系类型（可选）">
              <el-input v-model="batchRelationFilterType" placeholder="例如：connection / alliance / conflict" />
            </el-form-item>
            <el-form-item label="新关系类型">
              <el-input v-model="batchRelationType" placeholder="例如：alliance" />
            </el-form-item>
            <el-form-item label="标签前缀（可选）">
              <el-input v-model="batchRelationLabelPrefix" placeholder="例如：同盟-" />
            </el-form-item>
            <el-button type="primary" plain :loading="savingDetail" @click="applyBatchRelationUpdate">应用到匹配关系</el-button>
          </el-form>
        </el-card>

        <el-button class="consistency-btn" plain @click="consistencyDrawerVisible = true">🔍 逻辑校验</el-button>
        <el-button class="consistency-btn" plain @click="importTextDialogVisible = true">📥 导入文本</el-button>
      </aside>

      <main ref="canvasPanelRef" class="canvas-panel">
        <div v-if="loading" class="wb-loading-overlay">⬡</div>

        <div class="canvas-overlay-topright">
          <ThemeSwitcher v-model="currentTheme" />
          <span class="overlay-divider"></span>
          <ViewSwitcher v-model="activeView" />
          <button v-if="activeView === 'graph'" class="wb-icon-btn" title="自动布局" @click="autoLayout">⚙ 自动</button>
        </div>

        <div v-if="error" class="error-box">{{ error }}</div>

        <VueFlow
          id="wb-graph"
          v-else-if="activeView === 'graph'"
          class="world-flow"
          :nodes="flowNodes"
          :edges="flowEdges"
          :node-types="nodeTypes"
          connection-mode="loose"
          fit-view-on-init
          @node-click="onNodeClick"
          @edge-click="onEdgeClick"
          @connect="onConnect"
          @node-drag-stop="onNodeDragStop"
          @viewport-change="onViewportChange"
        >
          <Background :gap="22" :size="1" pattern-color="var(--wb-canvas-grid)" />
          <Controls />
          <MiniMap />
        </VueFlow>

        <MapViewCanvas
          v-else-if="activeView === 'map'"
          :regions="worldData.regions"
          :project-id="projectId"
          @node-click="onSubViewNodeClick"
        />

        <LayerViewCanvas
          v-else-if="activeView === 'layer'"
          :regions="worldData.regions"
          @node-click="onSubViewNodeClick"
        />

        <div v-else-if="activeView === 'space'" class="view-placeholder">
          <span class="placeholder-icon">✦</span>
          <p>星图视图正在建设中...</p>
        </div>

        <TimelinePanel :project-id="projectId" />
      </main>

      <aside class="right-panel" :class="{ open: !!selectedNode || !!selectedRelation }">
        <el-card v-if="!selectedNode && !selectedRelation" shadow="never" class="panel-card empty-panel">
          <p>选择一个节点查看详情</p>
        </el-card>

        <el-card v-else shadow="never" class="panel-card">
          <template #header>
            <div class="detail-header">
              <span>
                {{ selectedRelation ? '关系详情' : selectedKind === 'region' ? '地区详情' : '势力详情' }}
              </span>
              <el-button size="small" text @click="closeDetailPanel">关闭</el-button>
            </div>
          </template>

          <el-form v-if="selectedRelation && relationDraft" label-position="top" size="small">
            <el-form-item label="关系类型">
              <el-input v-model="relationDraft.relation_type" />
            </el-form-item>
            <el-form-item label="标签">
              <el-input v-model="relationDraft.label" />
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="relationDraft.description" type="textarea" :rows="3" />
            </el-form-item>
            <div class="detail-actions">
              <el-button type="primary" :loading="savingDetail" @click="saveRelation">保存</el-button>
              <el-button type="danger" plain :loading="savingDetail" @click="deleteRelationByDraft">删除</el-button>
            </div>
          </el-form>

          <RegionDetailPanel
            v-else-if="selectedKind === 'region' && regionDraft"
            :model="regionDraft"
            :loading="savingDetail"
            :factions="worldData.factions"
            :power-systems="worldData.power_systems"
            :project-id="projectId"
            @save="saveRegion"
            @delete="deleteRegion"
          />

          <FactionDetailPanel
            v-else-if="selectedKind === 'faction' && factionDraft"
            :model="factionDraft"
            :loading="savingDetail"
            :regions="worldData.regions"
            :power-systems="worldData.power_systems"
            :project-id="projectId"
            :all-factions="worldData.factions"
            @save="saveFaction"
            @delete="deleteFaction"
            @adopt-relation="adoptSuggestedRelation"
          />
        </el-card>

        <div class="right-panel-section-label">力量体系</div>
        <PowerSystemPanel
          :items="worldData.power_systems"
          :selected-id="selectedPowerSystemId"
          :loading="savingDetail"
          @create="powerDialogVisible = true"
          @select="selectedPowerSystemId = $event"
          @save="savePowerSystem"
          @delete="deletePowerSystem"
        />
      </aside>
    </div>

    <PowerSystemDialog
      :visible="powerDialogVisible"
      :templates="powerTemplates"
      @close="powerDialogVisible = false"
      @create="createPowerSystemByDialog"
    />

    <WorldNodeDialog
      :visible="nodeDialogVisible"
      :mode="nodeDialogMode"
      :regions="worldData.regions"
      :factions="worldData.factions"
      :power-systems="worldData.power_systems"
      @close="nodeDialogVisible = false"
      @create-region="createRegionFromDialog"
      @create-faction="createFactionFromDialog"
    />

    <el-drawer
      v-model="consistencyDrawerVisible"
      title="世界一致性校验"
      size="380px"
      direction="rtl"
    >
      <ConsistencyPanel :world-data="worldData" :project-id="projectId" />
    </el-drawer>

    <el-dialog v-model="importTextDialogVisible" title="文本转图谱导入" width="600px">
      <el-input
        v-model="importText"
        type="textarea"
        :rows="8"
        placeholder="粘贴世界设定文本（最大4000字）..."
        :maxlength="4000"
        show-word-limit
      />
      <div v-if="importPreview" class="import-preview">
        <h4>解析预览</h4>
        <div v-if="importPreview.regions.length" class="preview-section">
          <strong>地区 ({{ importPreview.regions.length }})</strong>
          <div v-for="(r, i) in importPreview.regions" :key="i" class="preview-card">{{ r.name }} — {{ r.region_type || '未分类' }}</div>
        </div>
        <div v-if="importPreview.factions.length" class="preview-section">
          <strong>势力 ({{ importPreview.factions.length }})</strong>
          <div v-for="(f, i) in importPreview.factions" :key="i" class="preview-card">{{ f.name }} — {{ f.scope || 'internal' }}</div>
        </div>
        <div v-if="importPreview.relations.length" class="preview-section">
          <strong>关系 ({{ importPreview.relations.length }})</strong>
          <div v-for="(rel, i) in importPreview.relations" :key="i" class="preview-card">{{ rel.source_name }} → {{ rel.target_name }} ({{ rel.relation_type }})</div>
        </div>
      </div>
      <template #footer>
        <el-button :loading="importParsing" @click="parseImportText">解析</el-button>
        <el-button v-if="importPreview" type="primary" :loading="importApplying" @click="applyImport">全部导入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, markRaw, nextTick, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  VueFlow,
  useVueFlow,
  type Connection,
  type Edge,
  type EdgeMouseEvent,
  type Node,
  type NodeComponent,
  type NodeDragEvent,
  type NodeMouseEvent,
} from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { MiniMap } from '@vue-flow/minimap'
import * as d3 from 'd3-force'
import '@vue-flow/core/dist/style.css'
import { world } from '@/api/world'
import type { Faction, Region, WorldRelation, WorldSandboxData } from '@/api/world'
import RegionNode from './components/RegionNode.vue'
import FactionNode from './components/FactionNode.vue'
import RegionDetailPanel from './components/RegionDetailPanel.vue'
import FactionDetailPanel from './components/FactionDetailPanel.vue'
import PowerSystemPanel from './components/PowerSystemPanel.vue'
import PowerSystemDialog from './components/PowerSystemDialog.vue'
import WorldNodeDialog from './components/WorldNodeDialog.vue'
import ViewSwitcher from './components/ViewSwitcher.vue'
import LayerViewCanvas from './components/LayerViewCanvas.vue'
import MapViewCanvas from './components/MapViewCanvas.vue'
import TimelinePanel from './components/TimelinePanel.vue'
import ConsistencyPanel from './components/ConsistencyPanel.vue'
import ThemeSwitcher from './components/ThemeSwitcher.vue'
import type { WbTheme } from './components/ThemeSwitcher.vue'
import { useViewMode } from './composables/useViewMode'
import type { ViewMode } from './composables/useViewMode'

const route = useRoute()
const projectId = computed(() => String(route.params.id || ''))

const loading = ref(false)
const savingMeta = ref(false)
const savingDetail = ref(false)
const finalizing = ref(false)
const error = ref('')
const finalizeSummary = ref<{ regions: number; factions: number; power_systems: number; relations: number } | null>(null)

const worldData = reactive<WorldSandboxData>({
  world_name: '',
  world_type: 'continental',
  world_description: '',
  regions: [],
  factions: [],
  power_systems: [],
  relations: [],
  world_rules: [],
})

const selectedNode = ref<Node | null>(null)
const selectedRelation = ref<Edge | null>(null)
const selectedKind = computed(() => (selectedNode.value?.data as any)?.kind || '')
const regionDraft = ref<Region | null>(null)
const factionDraft = ref<Faction | null>(null)
const relationDraft = ref<WorldRelation | null>(null)
const selectedPowerSystemId = ref('')
const powerDialogVisible = ref(false)
const nodeDialogVisible = ref(false)
const nodeDialogMode = ref<'region' | 'faction'>('region')
const powerTemplates = ref<{ template: string; name: string; preview_levels: string[]; level_count: number }[]>([])
const batchRelationFilterType = ref('')
const batchRelationType = ref('')
const batchRelationLabelPrefix = ref('')
const consistencyDrawerVisible = ref(false)

// Theme system
const currentTheme = ref<WbTheme>(
  (localStorage.getItem(`wb-theme-${projectId.value}`) as WbTheme) || 'cyberpunk'
)
watch(currentTheme, (v) => {
  localStorage.setItem(`wb-theme-${projectId.value}`, v)
})
const importTextDialogVisible = ref(false)
const importText = ref('')
const importParsing = ref(false)
const importApplying = ref(false)
const importPreview = ref<{ regions: Array<{ name: string; region_type?: string; notes?: string }>; factions: Array<{ name: string; scope?: string; description?: string }>; relations: Array<{ source_name: string; target_name: string; relation_type: string; label?: string }> } | null>(null)

const nodeTypes: Record<string, NodeComponent> = {
  region: markRaw(RegionNode) as unknown as NodeComponent,
  faction: markRaw(FactionNode) as unknown as NodeComponent,
}

// View mode system
const { activeView, saveViewState, getViewState } = useViewMode()

// Focus mode
const focusNodeId = ref<string | null>(null)

const focusNeighborIds = computed(() => {
  if (!focusNodeId.value) return new Set<string>()
  const related = new Set<string>([focusNodeId.value])
  flowEdges.value.forEach(e => {
    if (e.source === focusNodeId.value || e.target === focusNodeId.value) {
      related.add(e.source as string)
      related.add(e.target as string)
    }
  })
  return related
})

const flowNodes = computed<Node[]>(() => {
  const regionNodes = worldData.regions.map((r) => ({
    id: r.id,
    type: 'region',
    position: { x: r.x || 120, y: r.y || 120 },
    data: { label: r.name, kind: 'region', regionType: r.region_type },
    style: focusNodeId.value && !focusNeighborIds.value.has(r.id)
      ? { opacity: '0.15', transition: 'opacity 0.3s' }
      : { opacity: '1', transition: 'opacity 0.3s' },
  }))
  const factionNodes = worldData.factions.map((f, idx) => ({
    id: f.id,
    type: 'faction',
    position: { x: 680, y: 120 + idx * 110 },
    data: { label: f.name, kind: 'faction', scope: f.scope },
    style: focusNodeId.value && !focusNeighborIds.value.has(f.id)
      ? { opacity: '0.15', transition: 'opacity 0.3s' }
      : { opacity: '1', transition: 'opacity 0.3s' },
  }))
  return [...regionNodes, ...factionNodes]
})

// relation_type → edge 视觉映射
const EDGE_STYLE_MAP: Record<string, { style: Record<string, string | number>; animated: boolean }> = {
  alliance:   { style: { stroke: '#2ef2ff', strokeWidth: 2 },                            animated: true },
  conflict:   { style: { stroke: '#ff4040', strokeWidth: 2, strokeDasharray: '6,3' },     animated: true },
  war:        { style: { stroke: '#ff2e88', strokeWidth: 3 },                            animated: true },
  connection: { style: { stroke: '#666688', strokeWidth: 1.5 },                          animated: false },
}

// 性能优化: 节点 > 200 时关闭边动画
const edgeAnimationEnabled = computed(() => flowNodes.value.length < 200)

const flowEdges = computed<Edge[]>(() => {
  return worldData.relations.map((r) => {
    const mapping = EDGE_STYLE_MAP[r.relation_type] || EDGE_STYLE_MAP.connection
    return {
      id: r.id,
      source: r.source_id,
      target: r.target_id,
      label: r.label || r.relation_type,
      animated: edgeAnimationEnabled.value && mapping.animated,
      style: mapping.style,
      labelStyle: { fill: '#e0e0e0', fontSize: '11px' },
      labelBgStyle: { fill: 'rgba(0,0,0,0.6)', rx: 4 },
    }
  })
})

// 性能优化: 视口裁剪（节点 > 100 时启用）
const vfViewport = ref({ x: 0, y: 0, zoom: 1 })
const canvasPanelRef = ref<HTMLElement | null>(null)
const { fitView } = useVueFlow('wb-graph')

function onViewportChange(vp: { x: number; y: number; zoom: number }) {
  vfViewport.value = vp
}

watch([vfViewport, flowNodes], () => {
  const nodes = flowNodes.value
  if (nodes.length < 100) return

  const { x, y, zoom } = vfViewport.value
  const cw = canvasPanelRef.value?.clientWidth ?? 1200
  const ch = canvasPanelRef.value?.clientHeight ?? 800

  const left = -x / zoom
  const top = -y / zoom
  const right = left + cw / zoom
  const bottom = top + ch / zoom

  nodes.forEach(n => {
    const nx = n.position.x; const ny = n.position.y
    n.hidden = nx < left - 80 || nx > right + 80 || ny < top - 80 || ny > bottom + 80
  })
}, { deep: false })

onMounted(loadWorld)

async function loadWorld() {
  if (!projectId.value) return
  loading.value = true
  error.value = ''
  try {
    const [worldRes, tplRes] = await Promise.all([
      world.get(projectId.value),
      world.powerTemplates(projectId.value),
    ])
    Object.assign(worldData, worldRes.data)
    powerTemplates.value = tplRes.data.map((item: any) => ({
      template: item.template,
      name: item.name,
      preview_levels: item.preview_levels || [],
      level_count: Number(item.level_count || 0),
    }))
    if (!selectedPowerSystemId.value && worldData.power_systems.length > 0) {
      selectedPowerSystemId.value = worldData.power_systems[0].id
    }
  } catch (e: any) {
    error.value = e?.message || '加载世界数据失败'
  } finally {
    loading.value = false
  }
}

async function saveMeta() {
  if (!projectId.value) return
  savingMeta.value = true
  try {
    await world.updateMeta(projectId.value, {
      world_name: worldData.world_name,
      world_type: worldData.world_type,
      world_description: worldData.world_description,
    })
    ElMessage.success('世界信息已保存')
  } finally {
    savingMeta.value = false
  }
}

function openCreateDialog(mode: 'region' | 'faction') {
  nodeDialogMode.value = mode
  nodeDialogVisible.value = true
}

// d3-force auto layout
function autoLayout() {
  if (!worldData) return
  const allNodes = flowNodes.value
  if (allNodes.length === 0) return

  interface SimNode extends d3.SimulationNodeDatum {
    id: string
    x: number
    y: number
  }

  const simNodes: SimNode[] = allNodes.map(n => ({
    id: n.id,
    x: n.position.x,
    y: n.position.y,
  }))

  const simLinks = flowEdges.value.map(e => ({
    source: e.source as string,
    target: e.target as string,
  }))

  const simulation = d3.forceSimulation<SimNode>(simNodes)
    .force('link', d3.forceLink(simLinks).id((d: any) => d.id).distance(180).strength(0.8))
    .force('charge', d3.forceManyBody().strength(-400))
    .force('center', d3.forceCenter(600, 400))
    .force('collision', d3.forceCollide(90))
    .stop()

  for (let i = 0; i < 300; i++) simulation.tick()

  simNodes.forEach(sn => {
    const region = worldData.regions.find(r => r.id === sn.id)
    if (region) {
      region.x = sn.x
      region.y = sn.y
    }
  })

  // 布局完成后自动 FitView，确保所有节点可见
  nextTick(() => fitView({ padding: 0.15 }))
}

// View mode camera state save/restore
function onViewMoveEnd(event: { flowTransform: { x: number; y: number; zoom: number } }) {
  saveViewState(activeView.value, {
    zoom: event.flowTransform.zoom,
    x: event.flowTransform.x,
    y: event.flowTransform.y,
  })
}

// Handle node click from non-graph views
function onSubViewNodeClick(nodeId: string) {
  const region = worldData.regions.find(r => r.id === nodeId)
  if (region) {
    selectedRelation.value = null
    relationDraft.value = null
    selectedNode.value = { id: nodeId, position: { x: 0, y: 0 }, data: { label: region.name, kind: 'region' } }
    regionDraft.value = JSON.parse(JSON.stringify(region))
    factionDraft.value = null
  }
}

async function createRegionFromDialog(payload: Omit<Region, 'id'>) {
  if (!projectId.value) return
  const created = await world.createRegion(projectId.value, {
    name: payload.name,
    region_type: payload.region_type,
    x: payload.x,
    y: payload.y,
  })
  const saved = await world.updateRegion(projectId.value, created.data.id, {
    ...created.data,
    ...payload,
    id: created.data.id,
  })
  worldData.regions.push(saved.data)
  nodeDialogVisible.value = false
  ElMessage.success('地区已创建')
}

async function createFactionFromDialog(payload: Omit<Faction, 'id'>) {
  if (!projectId.value) return
  const created = await world.createFaction(projectId.value, {
    name: payload.name,
    scope: payload.scope,
    description: payload.description,
  })
  const saved = await world.updateFaction(projectId.value, created.data.id, {
    ...created.data,
    ...payload,
    id: created.data.id,
  })
  worldData.factions.push(saved.data)
  nodeDialogVisible.value = false
  ElMessage.success('势力已创建')
}

async function createPowerSystemByDialog(payload: { name: string; template: string }) {
  if (!projectId.value) return
  await world.createPowerSystem(projectId.value, payload)
  powerDialogVisible.value = false
  await loadWorld()
  ElMessage.success('力量体系已添加')
}

function onNodeClick(event: NodeMouseEvent) {
  const node = event.node

  // Focus mode: toggle
  if (focusNodeId.value === node.id) {
    focusNodeId.value = null
  } else {
    focusNodeId.value = node.id
  }

  selectedRelation.value = null
  relationDraft.value = null
  selectedNode.value = node
  if ((node.data as any)?.kind === 'region') {
    const found = worldData.regions.find((r) => r.id === node.id)
    regionDraft.value = found ? JSON.parse(JSON.stringify(found)) : null
    factionDraft.value = null
  } else if ((node.data as any)?.kind === 'faction') {
    const found = worldData.factions.find((f) => f.id === node.id)
    factionDraft.value = found ? JSON.parse(JSON.stringify(found)) : null
    regionDraft.value = null
  }
}

function onEdgeClick(event: EdgeMouseEvent) {
  const edge = event.edge
  selectedNode.value = null
  regionDraft.value = null
  factionDraft.value = null
  selectedRelation.value = edge
  const found = worldData.relations.find((r) => r.id === edge.id)
  relationDraft.value = found ? JSON.parse(JSON.stringify(found)) : null
}

async function onConnect(connection: Connection) {
  if (!projectId.value || !connection.source || !connection.target) return
  const res = await world.createRelation(projectId.value, {
    source_id: connection.source,
    target_id: connection.target,
    relation_type: 'connection',
    label: '连接',
    description: '',
  })
  worldData.relations.push(res.data)
  ElMessage.success('关系已创建')
}

async function onNodeDragStop(event: NodeDragEvent) {
  const node = event.node
  if (!projectId.value) return
  const target = worldData.regions.find((r) => r.id === node.id)
  if (!target) return
  target.x = node.position.x
  target.y = node.position.y
  await world.updateRegion(projectId.value, target.id, {
    ...target,
    id: target.id,
  })
}

async function saveRegion() {
  if (!projectId.value || !regionDraft.value) return
  savingDetail.value = true
  try {
    const res = await world.updateRegion(projectId.value, regionDraft.value.id, regionDraft.value)
    const idx = worldData.regions.findIndex((x) => x.id === regionDraft.value!.id)
    if (idx >= 0) worldData.regions[idx] = res.data
    ElMessage.success('地区已保存')
  } finally {
    savingDetail.value = false
  }
}

async function deleteRegion() {
  if (!projectId.value || !regionDraft.value) return
  savingDetail.value = true
  try {
    await world.deleteRegion(projectId.value, regionDraft.value.id)
    worldData.regions = worldData.regions.filter((x) => x.id !== regionDraft.value!.id)
    worldData.relations = worldData.relations.filter(
      (rel) => rel.source_id !== regionDraft.value!.id && rel.target_id !== regionDraft.value!.id,
    )
    selectedNode.value = null
    regionDraft.value = null
    ElMessage.success('地区已删除')
  } finally {
    savingDetail.value = false
  }
}

async function saveFaction() {
  if (!projectId.value || !factionDraft.value) return
  savingDetail.value = true
  try {
    const res = await world.updateFaction(projectId.value, factionDraft.value.id, factionDraft.value)
    const idx = worldData.factions.findIndex((x) => x.id === factionDraft.value!.id)
    if (idx >= 0) worldData.factions[idx] = res.data
    ElMessage.success('势力已保存')
  } finally {
    savingDetail.value = false
  }
}

async function deleteFaction() {
  if (!projectId.value || !factionDraft.value) return
  savingDetail.value = true
  try {
    await world.deleteFaction(projectId.value, factionDraft.value.id)
    worldData.factions = worldData.factions.filter((x) => x.id !== factionDraft.value!.id)
    worldData.relations = worldData.relations.filter(
      (rel) => rel.source_id !== factionDraft.value!.id && rel.target_id !== factionDraft.value!.id,
    )
    selectedNode.value = null
    factionDraft.value = null
    ElMessage.success('势力已删除')
  } finally {
    savingDetail.value = false
  }
}

async function adoptSuggestedRelation(s: { source_id: string; target_id: string; relation_type: string; reason: string }) {
  if (!projectId.value) return
  try {
    const res = await world.createRelation(projectId.value, {
      source_id: s.source_id,
      target_id: s.target_id,
      relation_type: s.relation_type,
      label: s.reason,
    })
    worldData.relations.push(res.data)
    ElMessage.success('已采纳关系建议')
  } catch {
    ElMessage.error('创建关系失败')
  }
}

async function parseImportText() {
  if (!projectId.value || !importText.value.trim()) return
  importParsing.value = true
  importPreview.value = null
  try {
    const res = await world.importText(projectId.value, importText.value)
    importPreview.value = res.data
  } catch {
    ElMessage.error('文本解析失败')
  } finally {
    importParsing.value = false
  }
}

async function applyImport() {
  if (!projectId.value || !importPreview.value) return
  importApplying.value = true
  try {
    const nameToId: Record<string, string> = {}
    for (const r of importPreview.value.regions) {
      const res = await world.createRegion(projectId.value, { name: r.name, region_type: r.region_type })
      worldData.regions.push(res.data)
      nameToId[r.name] = res.data.id
    }
    for (const f of importPreview.value.factions) {
      const res = await world.createFaction(projectId.value, { name: f.name, scope: f.scope, description: f.description })
      worldData.factions.push(res.data)
      nameToId[f.name] = res.data.id
    }
    for (const rel of importPreview.value.relations) {
      const sourceId = nameToId[rel.source_name]
      const targetId = nameToId[rel.target_name]
      if (sourceId && targetId) {
        const res = await world.createRelation(projectId.value, {
          source_id: sourceId,
          target_id: targetId,
          relation_type: rel.relation_type,
          label: rel.label || '',
        })
        worldData.relations.push(res.data)
      }
    }
    ElMessage.success('导入完成')
    importTextDialogVisible.value = false
    importPreview.value = null
    importText.value = ''
  } catch {
    ElMessage.error('导入失败')
  } finally {
    importApplying.value = false
  }
}

async function saveRelation() {
  if (!projectId.value || !relationDraft.value) return
  savingDetail.value = true
  try {
    const res = await world.updateRelation(projectId.value, relationDraft.value.id, {
      relation_type: relationDraft.value.relation_type,
      label: relationDraft.value.label,
      description: relationDraft.value.description,
    })
    const idx = worldData.relations.findIndex((x) => x.id === relationDraft.value!.id)
    if (idx >= 0) worldData.relations[idx] = res.data
    ElMessage.success('关系已保存')
  } finally {
    savingDetail.value = false
  }
}

async function deleteRelationByDraft() {
  if (!projectId.value || !relationDraft.value) return
  savingDetail.value = true
  try {
    await world.deleteRelation(projectId.value, relationDraft.value.id)
    worldData.relations = worldData.relations.filter((x) => x.id !== relationDraft.value!.id)
    selectedRelation.value = null
    relationDraft.value = null
    ElMessage.success('关系已删除')
  } finally {
    savingDetail.value = false
  }
}

async function applyBatchRelationUpdate() {
  if (!projectId.value || !batchRelationType.value.trim()) {
    ElMessage.warning('请先输入新关系类型')
    return
  }
  const filterType = batchRelationFilterType.value.trim()
  const target = worldData.relations.filter((item) => !filterType || item.relation_type === filterType)
  if (target.length === 0) {
    ElMessage.info('没有匹配到可更新关系')
    return
  }

  savingDetail.value = true
  try {
    for (const item of target) {
      const nextLabel = batchRelationLabelPrefix.value
        ? `${batchRelationLabelPrefix.value}${item.label || item.relation_type}`
        : item.label
      const res = await world.updateRelation(projectId.value, item.id, {
        relation_type: batchRelationType.value.trim(),
        label: nextLabel,
      })
      const idx = worldData.relations.findIndex((x) => x.id === item.id)
      if (idx >= 0) worldData.relations[idx] = res.data
    }
    ElMessage.success(`已更新 ${target.length} 条关系`)
  } finally {
    savingDetail.value = false
  }
}

async function savePowerSystem(psId: string, payload: Record<string, any>, syncGlobal = false) {
  if (!projectId.value) return
  savingDetail.value = true
  try {
    const existing = worldData.power_systems.find((item) => item.id === psId)
    if (!existing) return
    const res = await world.updatePowerSystem(projectId.value, psId, {
      ...existing,
      ...payload,
      id: psId,
    })
    const idx = worldData.power_systems.findIndex((x) => x.id === psId)
    if (idx >= 0) worldData.power_systems[idx] = res.data

    let syncedRegions = 0
    let syncedFactions = 0
    if (syncGlobal) {
      // 同步所有“继承全局”的地区，使其引用当前全局体系
      const regionsToSync = worldData.regions.filter((r) => r.power_access?.inherits_global)
      for (const region of regionsToSync) {
        const updated = {
          ...region,
          power_access: {
            ...region.power_access,
            custom_system_id: psId,
          },
          id: region.id,
        }
        const regionRes = await world.updateRegion(projectId.value, region.id, updated)
        const regionIdx = worldData.regions.findIndex((x) => x.id === region.id)
        if (regionIdx >= 0) worldData.regions[regionIdx] = regionRes.data
        syncedRegions += 1
      }

      // 同步未绑定体系的势力到当前全局体系
      const factionsToSync = worldData.factions.filter((f) => !f.power_system_id)
      for (const faction of factionsToSync) {
        const factionRes = await world.updateFaction(projectId.value, faction.id, {
          ...faction,
          power_system_id: psId,
          id: faction.id,
        })
        const factionIdx = worldData.factions.findIndex((x) => x.id === faction.id)
        if (factionIdx >= 0) worldData.factions[factionIdx] = factionRes.data
        syncedFactions += 1
      }
    }

    if (syncGlobal) {
      ElMessage.success(`力量体系已保存并同步：地区 ${syncedRegions} / 势力 ${syncedFactions}`)
      return
    }
    ElMessage.success('力量体系已保存')
  } finally {
    savingDetail.value = false
  }
}

function closeDetailPanel() {
  selectedNode.value = null
  selectedRelation.value = null
  regionDraft.value = null
  factionDraft.value = null
  relationDraft.value = null
}

async function deletePowerSystem(psId: string) {
  if (!projectId.value) return
  savingDetail.value = true
  try {
    await world.deletePowerSystem(projectId.value, psId)
    worldData.power_systems = worldData.power_systems.filter((x) => x.id !== psId)
    if (selectedPowerSystemId.value === psId) {
      selectedPowerSystemId.value = worldData.power_systems[0]?.id || ''
    }
    ElMessage.success('力量体系已删除')
  } finally {
    savingDetail.value = false
  }
}

async function finalizeWorld() {
  if (!projectId.value) return
  finalizing.value = true
  try {
    const res = await world.finalize(projectId.value)
    finalizeSummary.value = {
      regions: Number(res.data.summary?.regions || 0),
      factions: Number(res.data.summary?.factions || 0),
      power_systems: Number(res.data.summary?.power_systems || 0),
      relations: Number(res.data.summary?.relations || 0),
    }
    ElMessage.success('世界设定已写入知识库')
  } finally {
    finalizing.value = false
  }
}
</script>

<style scoped>
.sandbox-page {
  height: calc(100vh - 96px);
  display: flex;
  flex-direction: column;
  gap: 12px;
  background: var(--color-base);
  color: var(--color-text-primary);
}

.sandbox-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.sandbox-title {
  margin: 0;
  font-size: 24px;
}

.sandbox-subtitle {
  margin: 2px 0 0;
  color: var(--color-text-secondary);
}

.header-actions {
  display: flex;
  gap: 8px;
}

.finalize-alert {
  margin-bottom: 8px;
}

.sandbox-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 220px 1fr 0;
  gap: 12px;
  transition: grid-template-columns 0.2s ease;
}

.right-panel.open {
  width: 320px;
}

.sandbox-layout:has(.right-panel.open) {
  grid-template-columns: 220px 1fr 320px;
}

.left-panel,
.right-panel {
  min-height: 0;
  overflow-y: auto;
  background: var(--wb-glass-bg);
  backdrop-filter: blur(var(--wb-glass-blur));
  -webkit-backdrop-filter: blur(var(--wb-glass-blur));
  box-shadow: var(--wb-glass-shadow);
  border-radius: 10px;
}

.left-panel {
  border-right: 1px solid var(--wb-glass-border);
}

.right-panel {
  border-left: 1px solid var(--wb-glass-border);
  transition: width 0.25s cubic-bezier(0.4, 0, 0.2, 1),
              opacity 0.25s ease,
              box-shadow 0.25s ease;
}

.right-panel.open {
  box-shadow: -4px 0 32px rgba(46, 242, 255, 0.12), var(--wb-glass-shadow);
}

.panel-card {
  margin-bottom: 12px;
  --el-card-bg-color: transparent;
  border-color: var(--wb-glass-border);
}

.panel-card :deep(.el-card__header) {
  color: var(--wb-neon-cyan);
  border-bottom-color: var(--wb-glass-border);
}

.panel-card :deep(.el-input__wrapper),
.panel-card :deep(.el-textarea__inner),
.panel-card :deep(.el-select .el-input__wrapper) {
  background: rgba(0, 0, 0, 0.3);
  border-color: rgba(255, 255, 255, 0.08);
  color: var(--color-text-primary);
}

.panel-card :deep(.el-form-item__label) {
  color: var(--color-text-secondary);
}

.canvas-panel {
  min-height: 0;
  border: 1px solid var(--wb-glass-border);
  border-radius: 10px;
  overflow: hidden;
  position: relative;
  background: var(--wb-canvas-bg);
}

.world-flow {
  width: 100%;
  height: 100%;
}

.toolbar-actions {
  display: grid;
  gap: 8px;
}

.stats-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.stat-item {
  border: 1px solid var(--wb-glass-border);
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--color-text-primary);
}

.stat-item span {
  color: var(--color-text-secondary);
  font-size: 12px;
}

.stat-item strong {
  color: var(--wb-neon-cyan);
  font-size: 18px;
}

.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.detail-actions {
  display: flex;
  gap: 8px;
}

.empty-panel {
  color: var(--el-text-color-secondary);
}

.error-box {
  padding: 16px;
  color: var(--el-color-danger);
}

/* WorldBuilder KeyFrame Animations */
@keyframes wb-glow-pulse {
  0%   { box-shadow: 0 0 4px rgba(46, 242, 255, 0.2), 0 0 12px rgba(46, 242, 255, 0.1); }
  100% { box-shadow: 0 0 10px rgba(46, 242, 255, 0.5), 0 0 28px rgba(46, 242, 255, 0.25); }
}

@keyframes wb-flow {
  from { stroke-dashoffset: 24; }
  to   { stroke-dashoffset: 0; }
}

/* View switcher overlay */
.canvas-overlay-topright {
  position: absolute;
  top: 12px;
  right: 12px;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 8px;
}

.overlay-divider {
  width: 1px;
  height: 20px;
  background: var(--wb-glass-border, rgba(255,255,255,0.12));
  flex-shrink: 0;
}

.right-panel-section-label {
  padding: 6px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--wb-neon-cyan, #2ef2ff);
  border-top: 1px solid var(--wb-glass-border, rgba(255,255,255,0.08));
  opacity: 0.7;
  text-transform: uppercase;
}

.wb-icon-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid var(--wb-glass-border);
  border-radius: 6px;
  color: #aaa;
  cursor: pointer;
  font-size: 12px;
  backdrop-filter: blur(8px);
  transition: all 0.2s ease;
}

.wb-icon-btn:hover {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-neon-cyan);
  box-shadow: 0 0 8px rgba(46, 242, 255, 0.2);
}

.view-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #555;
  gap: 12px;
}

.placeholder-icon {
  font-size: 48px;
  opacity: 0.4;
}

.view-placeholder p {
  font-size: 14px;
  color: #666;
}

.consistency-btn {
  width: 100%;
  margin-top: 8px;
}

/* Loading overlay */
@keyframes wb-hex-pulse {
  0%   { opacity: 0.1; }
  50%  { opacity: 0.6; }
  100% { opacity: 0.1; }
}
.wb-loading-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(8, 8, 16, 0.6);
  font-size: 32px;
  animation: wb-hex-pulse 1.2s ease-in-out infinite;
  z-index: 50;
  color: var(--wb-neon-cyan, #2ef2ff);
}

/* Right panel animation */
.right-panel:not(.open) {
  opacity: 0;
  pointer-events: none;
}

.import-preview {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 8px;
  background: rgba(255,255,255,0.02);
}
.import-preview h4 {
  margin: 0 0 8px;
  color: var(--wb-neon-cyan, #2ef2ff);
}
.preview-section {
  margin-bottom: 8px;
}
.preview-card {
  padding: 4px 8px;
  margin: 2px 0;
  border-radius: 4px;
  background: rgba(255,255,255,0.04);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .sandbox-page {
    height: auto;
    min-height: calc(100vh - 96px);
  }

  .sandbox-layout,
  .sandbox-layout:has(.right-panel.open) {
    grid-template-columns: 1fr;
  }

  .canvas-panel {
    height: 56vh;
  }

  .right-panel {
    width: 100%;
  }
}
</style>
