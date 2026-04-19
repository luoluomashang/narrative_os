<template>
  <div class="sandbox-page" :data-theme="worldData.world_type || 'continental'" :data-wb-theme="currentTheme">
    <SystemPageHeader
      eyebrow="World Builder"
      title="世界观沙盘"
      description="可视化编辑地区、势力与关系网络，并发布运行态世界知识。"
    >
      <template #meta>
        <span class="sandbox-pill">项目 {{ projectId }}</span>
        <span class="sandbox-pill">地区 {{ worldData.regions.length }}</span>
        <span class="sandbox-pill">势力 {{ worldData.factions.length }}</span>
        <span class="sandbox-pill">主题 {{ currentTheme }}</span>
      </template>
      <template #actions>
        <SystemButton variant="ghost" :loading="loading" @click="loadWorld">刷新</SystemButton>
        <SystemButton variant="primary" :loading="savingMeta" @click="saveMeta">保存世界信息</SystemButton>
        <SystemButton :loading="finalizing" @click="finalizeWorld">完成世界设定</SystemButton>
        <SystemButton variant="quiet" :loading="publishing" @click="publishWorld">发布运行态</SystemButton>
      </template>
    </SystemPageHeader>

    <el-alert
      v-if="finalizeSummary"
      type="success"
      show-icon
      :closable="true"
      class="finalize-alert"
      :title="`已写入知识库：地区 ${finalizeSummary.regions} / 势力 ${finalizeSummary.factions} / 体系 ${finalizeSummary.power_systems} / 关系 ${finalizeSummary.relations}`"
    />

    <el-alert
      v-if="publishSummary"
      type="success"
      show-icon
      :closable="true"
      class="finalize-alert"
      :title="`RuntimeWorldState 已发布 ${publishSummary.world_version}：地区 ${publishSummary.regions} / 势力 ${publishSummary.factions} / 体系 ${publishSummary.power_systems} / 关系 ${publishSummary.relations}`"
    />

    <SystemCard v-if="publishSummary?.runtime_diff?.sections.length" class="publish-diff-card" title="运行态结构化 Diff">
      <div
        v-for="section in publishSummary.runtime_diff.sections"
        :key="section.key"
        class="publish-diff-section"
      >
        <div class="publish-diff-section-title">{{ section.label }}</div>
        <div
          v-for="item in section.items"
          :key="`${section.key}-${item.target_id}-${item.target_name}`"
          class="publish-diff-item"
        >
          <div class="publish-diff-item-title">{{ item.target_name || item.target_id || item.change_type }}</div>
          <div class="publish-diff-item-effect">{{ item.effect }}</div>
          <div v-if="item.before || item.after" class="publish-diff-item-compare">{{ item.before }} → {{ item.after }}</div>
          <div v-if="item.note" class="publish-diff-item-note">{{ item.note }}</div>
        </div>
      </div>
      <div v-if="publishSummary.runtime_diff.auto_fix_notes.length" class="publish-autofix-block">
        <div class="publish-diff-section-title">自动补全提示</div>
        <div
          v-for="(note, index) in publishSummary.runtime_diff.auto_fix_notes"
          :key="`${index}-${note}`"
          class="publish-autofix-note"
        >
          {{ note }}
        </div>
      </div>
    </SystemCard>

    <SystemStatusBanner
      v-if="currentState === 'success' && worldReadinessIssues.length > 0"
      status="blocking"
      title="发布前仍有阻塞项"
      :message="worldReadinessMessage"
      description="当前仍可继续编辑，但完成世界设定和发布运行态前建议先处理这些约束。"
    >
      <template #actions>
        <SystemButton variant="ghost" @click="openCreateDialog('region')">补充地区</SystemButton>
        <SystemButton variant="quiet" @click="consistencyDrawerVisible = true">打开校验抽屉</SystemButton>
      </template>
    </SystemStatusBanner>

    <SystemStatusBanner
      v-if="currentState === 'success' && activeView === 'graph' && graphPerformanceMessage"
      status="partial-failure"
      title="已进入性能降级模式"
      :message="graphPerformanceMessage"
      description="这是局部降级，不影响节点编辑和关系维护。"
    >
      <template #actions>
        <SystemButton variant="ghost" @click="autoLayout">重新布局</SystemButton>
      </template>
    </SystemStatusBanner>

    <div class="sandbox-layout">
      <aside class="left-panel">
        <SystemCard class="panel-card panel-card--world-info" title="世界信息" description="把基础设定、完整度与编辑表单合并到同一张信息卡里，避免左栏只剩窄表单。">
          <div class="world-meta-grid">
            <div v-for="item in worldMetaSummaryItems" :key="item.label" class="world-meta-stat">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
          <p class="world-meta-copy">{{ worldDescriptionPreview }}</p>

          <el-form label-position="top" size="small" class="world-meta-form">
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
              <el-input v-model="worldData.world_description" type="textarea" :rows="4" />
            </el-form-item>
          </el-form>
        </SystemCard>

        <SystemCard class="panel-card" title="编辑工具" tone="subtle">
          <p class="tool-summary">节点创建、关系批量编辑、逻辑校验与文本导入统一收纳到工具抽屉。</p>
          <div class="toolbar-actions">
            <SystemButton size="sm" variant="primary" @click="toolDrawerVisible = true">打开编辑抽屉</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="consistencyDrawerVisible = true">逻辑校验</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="importTextDialogVisible = true">导入文本</SystemButton>
          </div>
        </SystemCard>
      </aside>

      <main ref="canvasPanelRef" class="canvas-panel">
        <div class="canvas-overlay-topright" v-if="currentState === 'success'">
          <ThemeSwitcher v-model="currentTheme" />
          <span class="overlay-divider"></span>
          <ViewSwitcher v-model="activeView" />
          <button v-if="activeView === 'graph'" class="wb-icon-btn" title="自动布局" @click="autoLayout">⚙ 自动</button>
        </div>

        <div v-if="currentState === 'loading'" class="canvas-state-shell">
          <SystemSkeleton :rows="10" show-header card />
        </div>

        <div v-else-if="currentState === 'blocking'" class="canvas-state-shell">
          <SystemVisualizationFallback
            title="世界沙盘暂时不可用"
            :description="error || '当前无法加载世界数据，请先恢复连接后再继续编辑。'"
            :items="worldSummaryItems"
          >
            <template #actions>
              <SystemButton variant="primary" @click="loadWorld">重新加载</SystemButton>
              <SystemButton variant="quiet" @click="consistencyDrawerVisible = true">打开校验抽屉</SystemButton>
            </template>
          </SystemVisualizationFallback>
        </div>

        <div v-else-if="currentState === 'empty'" class="canvas-state-shell">
          <SystemEmpty
            title="世界草稿还是空的"
            description="先创建地区、势力或力量体系，主画布才会开始承载关系与运行态编辑。"
          >
            <template #action>
              <div class="canvas-empty-actions">
                <SystemButton variant="primary" @click="openCreateDialog('region')">创建地区</SystemButton>
                <SystemButton variant="quiet" @click="openCreateDialog('faction')">创建势力</SystemButton>
              </div>
            </template>
          </SystemEmpty>
        </div>

        <template v-else>
          <VueFlow
            id="wb-graph"
            v-if="activeView === 'graph'"
            class="world-flow"
            :nodes="flowNodes"
            :edges="flowEdges"
            :node-types="nodeTypes"
            :connection-mode="ConnectionMode.Loose"
            fit-view-on-init
            @node-click="onNodeClick"
            @edge-click="onEdgeClick"
            @connect="onConnect"
            @node-drag-stop="onNodeDragStop"
            @viewport-change="onViewportChange"
          >
            <Background :gap="22" :size="1" pattern-color="var(--wb-canvas-grid)" />
            <Controls />
            <MiniMap :width="150" :height="100" />
          </VueFlow>

          <WorldLegend
            v-if="activeView === 'graph'"
            :factions="worldData.factions"
            :regions="worldData.regions"
            @highlight="onLegendHighlight"
            @select="onLegendSelect"
          />

          <MapViewCanvas
            v-else-if="activeView === 'map'"
            :regions="worldData.regions"
            :factions="worldData.factions"
            :relations="worldData.relations"
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
        </template>
      </main>

      <aside class="right-panel" :class="{ open: !!selectedNode || !!selectedRelation }">
        <SystemCard v-if="!selectedNode && !selectedRelation" class="panel-card empty-panel">
          <p>选择一个节点查看详情</p>
        </SystemCard>

        <SystemCard v-else class="panel-card">
          <template #header>
            <div class="detail-header">
              <span>
                {{ selectedRelation ? '关系详情' : selectedKind === 'region' ? '地区详情' : '势力详情' }}
              </span>
              <SystemButton size="sm" variant="ghost" @click="closeDetailPanel">关闭</SystemButton>
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
              <SystemButton variant="primary" :loading="savingDetail" @click="saveRelation">保存</SystemButton>
              <SystemButton variant="danger" :loading="savingDetail" @click="deleteRelationByDraft">删除</SystemButton>
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
        </SystemCard>

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

    <SystemDrawer
      v-model="consistencyDrawerVisible"
      title="世界一致性校验"
      description="集中处理结构冲突、关系缺漏和运行态发布前的基础校验。"
      size="380px"
    >
      <ConsistencyPanel :world-data="worldData" :project-id="projectId" />
    </SystemDrawer>

    <SystemDrawer
      v-model="toolDrawerVisible"
      title="世界编辑工具"
      description="把节点创建、批量关系编辑和辅助入口统一收进工具抽屉，保留主画布为唯一工作焦点。"
      size="420px"
    >
      <SystemCard class="panel-card" title="节点操作">
        <div class="toolbar-actions">
          <SystemButton size="sm" variant="primary" @click="openCreateDialog('region')">+ 地区</SystemButton>
          <SystemButton size="sm" @click="openCreateDialog('faction')">+ 势力</SystemButton>
          <SystemButton size="sm" variant="quiet" @click="powerDialogVisible = true">+ 力量体系</SystemButton>
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
      </SystemCard>

      <SystemCard class="panel-card" title="关系批量编辑">
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
          <SystemButton size="sm" variant="primary" :loading="savingDetail" @click="applyBatchRelationUpdate">应用到匹配关系</SystemButton>
        </el-form>
      </SystemCard>

      <div class="toolbar-actions">
        <SystemButton size="sm" variant="ghost" @click="consistencyDrawerVisible = true">逻辑校验</SystemButton>
        <SystemButton size="sm" variant="ghost" @click="importTextDialogVisible = true">导入文本</SystemButton>
      </div>
    </SystemDrawer>

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
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  ConnectionMode,
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
import type { Faction, Region, WorldPublishPreviewResponse, WorldRelation, WorldRuntimeDiff, WorldSandboxData } from '@/api/world'
import RegionNode from './components/RegionNode.vue'
import FactionNode from './components/FactionNode.vue'
import FactionGroupNode from './components/FactionGroupNode.vue'
import WorldLegend from './components/WorldLegend.vue'
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
import { useAsyncViewState } from '@/composables/useAsyncViewState'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'
import SystemVisualizationFallback from '@/components/system/SystemVisualizationFallback.vue'

const route = useRoute()
const projectId = computed(() => String(route.params.id || ''))

const loading = ref(false)
const savingMeta = ref(false)
const savingDetail = ref(false)
const finalizing = ref(false)
const publishing = ref(false)
const error = ref('')
const finalizeSummary = ref<{ regions: number; factions: number; power_systems: number; relations: number } | null>(null)
const publishSummary = ref<{ world_version: string; regions: number; factions: number; power_systems: number; relations: number; runtime_diff: WorldRuntimeDiff | null } | null>(null)

const worldData = reactive<WorldSandboxData>({
  world_name: '',
  world_type: 'continental',
  world_description: '',
  regions: [],
  factions: [],
  power_systems: [],
  relations: [],
  timeline_events: [],
  world_rules: [],
})

const hasNoWorldContent = computed(() => (
  worldData.regions.length === 0
  && worldData.factions.length === 0
  && worldData.power_systems.length === 0
  && worldData.relations.length === 0
))

const { currentState } = useAsyncViewState({
  loading,
  blocking: computed(() => Boolean(error.value)),
  empty: computed(() => !loading.value && !error.value && hasNoWorldContent.value),
})

const worldSummaryItems = computed(() => [
  { label: '地区', value: worldData.regions.length },
  { label: '势力', value: worldData.factions.length },
  { label: '体系', value: worldData.power_systems.length },
  { label: '关系', value: worldData.relations.length },
])

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
const toolDrawerVisible = ref(false)

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
  factionGroup: markRaw(FactionGroupNode) as unknown as NodeComponent,
}

// View mode system
const { activeView } = useViewMode()

// Focus mode
const focusNodeId = ref<string | null>(null)
// Legend highlight
const highlightFactionId = ref<string | null>(null)

// Clear focus mode and highlight when switching views
watch(activeView, () => {
  focusNodeId.value = null
  highlightFactionId.value = null
})

function onLegendHighlight(factionId: string | null) {
  highlightFactionId.value = factionId
}

function onLegendSelect(factionId: string) {
  const found = worldData.factions.find((f) => f.id === factionId)
  if (!found) return
  selectedRelation.value = null
  relationDraft.value = null
  regionDraft.value = null
  selectedNode.value = { id: found.id, position: { x: found.x ?? 0, y: found.y ?? 0 }, data: { label: found.name, kind: 'faction' } }
  factionDraft.value = JSON.parse(JSON.stringify(found))
}

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

// Build region-to-faction ownership map (bidirectional):
// Prefers faction.territory_region_ids; falls back to region.faction_ids[0]
const regionOwnerMap = computed(() => {
  const map: Record<string, string> = {}
  // faction side: faction lists which regions it controls
  worldData.factions.forEach((f) => {
    f.territory_region_ids.forEach((rid) => {
      map[rid] = f.id
    })
  })
  // region side: region lists which factions it belongs to (take first faction)
  worldData.regions.forEach((r) => {
    if (map[r.id]) return // already mapped from faction side
    const firstFactionId = (r as any).faction_ids?.[0]
    if (firstFactionId) map[r.id] = firstFactionId
  })
  return map
})

// Compute effective region list per faction derived from bidirectional regionOwnerMap
const effectiveFactionRegions = computed(() => {
  const byFaction: Record<string, string[]> = {}
  worldData.factions.forEach((f) => { byFaction[f.id] = [] })
  Object.entries(regionOwnerMap.value).forEach(([rid, fid]) => {
    if (byFaction[fid]) byFaction[fid].push(rid)
  })
  return byFaction
})

function isNodeDimmed(nodeId: string, kind: string): boolean {
  // Focus mode dimming
  if (focusNodeId.value && !focusNeighborIds.value.has(nodeId)) return true
  // Legend highlight dimming
  if (!highlightFactionId.value) return false
  if (highlightFactionId.value === '__none__') {
    if (kind === 'faction') return true
    return !!regionOwnerMap.value[nodeId]
  }
  if (kind === 'faction') return nodeId !== highlightFactionId.value
  const owner = regionOwnerMap.value[nodeId]
  return owner !== highlightFactionId.value
}

const flowNodes = computed<Node[]>(() => {
  const nodes: Node[] = []

  // 1) Faction group container nodes (rendered as background)
  worldData.factions.forEach((f) => {
    const effRegions = effectiveFactionRegions.value[f.id] ?? []
    if (effRegions.length === 0) return
    const groupId = `group-${f.id}`
    nodes.push({
      id: groupId,
      type: 'factionGroup',
      position: { x: f.x || 100, y: f.y || 100 },
      data: {
        label: f.name,
        kind: 'factionGroup',
        color: f.color || 'var(--wb-neon-blue)',
        regionCount: effRegions.length,
        scope: f.scope,
      },
      style: {
        width: '260px',
        height: `${Math.max(140, effRegions.length * 100 + 60)}px`,
        opacity: isNodeDimmed(f.id, 'faction') ? '0.15' : '1',
        transition: 'opacity 0.3s',
        zIndex: -1,
      },
    } as Node)
  })

  // 2) Region nodes — attach to parent group if owned
  const regionNodes = worldData.regions.map((r) => {
    const ownerId = regionOwnerMap.value[r.id]
    const parentGroupId = ownerId ? `group-${ownerId}` : undefined
    const effRegions = ownerId ? (effectiveFactionRegions.value[ownerId] ?? []) : []
    return {
      id: r.id,
      type: 'region',
      position: parentGroupId
        ? { x: 20, y: 40 + (effRegions.indexOf(r.id) || 0) * 100 }
        : { x: r.x || 120, y: r.y || 120 },
      parentNode: parentGroupId,
      expandParent: true,
      data: { label: r.name, kind: 'region', regionType: r.region_type },
      style: {
        opacity: isNodeDimmed(r.id, 'region') ? '0.15' : '1',
        transition: 'opacity 0.3s',
      },
    }
  })

  // 3) Standalone faction nodes (no territory)
  const factionNodes = worldData.factions
    .filter((f) => (effectiveFactionRegions.value[f.id]?.length ?? 0) === 0)
    .map((f, idx) => ({
      id: f.id,
      type: 'faction',
      position: { x: 680, y: 120 + idx * 110 },
      data: { label: f.name, kind: 'faction', scope: f.scope },
      style: {
        opacity: isNodeDimmed(f.id, 'faction') ? '0.15' : '1',
        transition: 'opacity 0.3s',
      },
    }))

  return [...nodes, ...regionNodes, ...factionNodes]
})

// relation_type → edge 视觉映射（覆盖全部 9 种关系类型）
const EDGE_STYLE_MAP: Record<string, { style: Record<string, string | number>; animated: boolean }> = {
  adjacent:   { style: { stroke: 'var(--wb-relation-adjacent)', strokeWidth: 1.5, strokeDasharray: '6,4' },   animated: false },
  border:     { style: { stroke: 'var(--wb-relation-border)', strokeWidth: 2 },                                    animated: false },
  trade:      { style: { stroke: 'var(--wb-relation-trade)', strokeWidth: 2 },                                     animated: true },
  war:        { style: { stroke: 'var(--wb-relation-war)', strokeWidth: 3 },                                       animated: true },
  alliance:   { style: { stroke: 'var(--wb-relation-alliance)', strokeWidth: 2 },                                 animated: true },
  vassal:     { style: { stroke: 'var(--wb-relation-vassal)', strokeWidth: 2, strokeDasharray: '8,3' },          animated: false },
  blockade:   { style: { stroke: 'var(--wb-relation-blockade)', strokeWidth: 2, strokeDasharray: '4,4' },        animated: false },
  teleport:   { style: { stroke: 'var(--wb-relation-teleport)', strokeWidth: 2, strokeDasharray: '2,4' },        animated: true },
  connection: { style: { stroke: 'var(--wb-relation-connection)', strokeWidth: 1.5 },                             animated: false },
}

// 性能优化: 节点 > 200 时关闭边动画
const edgeAnimationEnabled = computed(() => flowNodes.value.length < 200)

const graphPerformanceMessage = computed(() => {
  if (flowNodes.value.length >= 200) {
    return '节点已超过 200，系统已关闭边动画并启用视口外节点裁剪以保持主画布稳定。'
  }

  if (flowNodes.value.length >= 100) {
    return '节点已超过 100，系统会优先保证主画布交互流畅，并开始按视口裁剪非可见节点。'
  }

  return ''
})

function collectWorldCompletenessWarnings() {
  const warnings: string[] = []
  if (worldData.regions.length === 0) warnings.push('至少需要 1 个地区')
  if (worldData.factions.length === 0) warnings.push('至少需要 1 个势力')
  if (!worldData.world_name?.trim()) warnings.push('缺少世界名称')
  if (worldData.relations.length === 0) warnings.push('尚未建立任何关系')

  const factionsNoTerritory = worldData.factions.filter((f) => f.territory_region_ids.length === 0)
  if (factionsNoTerritory.length > 0) {
    warnings.push(`${factionsNoTerritory.length} 个势力无领地：${factionsNoTerritory.map((f) => f.name).join('、')}`)
  }

  const regionsNoDesc = worldData.regions.filter((r) => !r.notes?.trim())
  if (regionsNoDesc.length > 0) {
    warnings.push(`${regionsNoDesc.length} 个地区无描述`)
  }

  return warnings
}

const worldReadinessIssues = computed(() => {
  if (hasNoWorldContent.value) {
    return []
  }

  return collectWorldCompletenessWarnings()
})

const worldReadinessMessage = computed(() => worldReadinessIssues.value.slice(0, 2).join('；'))
const worldTypeLabel = computed(() => {
  switch (worldData.world_type) {
    case 'planar':
      return '位面/世界流'
    case 'interstellar':
      return '星际/宇宙流'
    case 'multi_layer':
      return '多层世界'
    default:
      return '大陆流'
  }
})
const worldDescriptionPreview = computed(() => {
  const description = worldData.world_description?.trim()
  if (!description) {
    return '先用一句完整的世界描述说明主秩序、核心冲突或时代气质，左侧信息区才不会退化成只剩表单控件。'
  }
  return description.length > 120 ? `${description.slice(0, 120).trim()}…` : description
})
const worldMetaSummaryItems = computed(() => [
  { label: '世界类型', value: worldTypeLabel.value },
  { label: '发布准备', value: worldReadinessIssues.value.length === 0 ? '可发布' : '待补全' },
  { label: '描述状态', value: worldData.world_description.trim() ? '已填写' : '待补充' },
  { label: '关系网络', value: `${worldData.relations.length} 条` },
])

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
      labelStyle: { fill: 'var(--wb-text-main)', fontSize: '11px' },
      labelBgStyle: { fill: 'var(--wb-panel-solid-strong)', rx: 4 },
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

// d3-force auto layout (group-aware)
function autoLayout() {
  if (!worldData) return
  const regions = worldData.regions
  const factions = worldData.factions
  if (regions.length === 0 && factions.length === 0) return

  interface SimNode extends d3.SimulationNodeDatum {
    id: string
    x: number
    y: number
  }

  // Build ownership map: regionId → factionId (bidirectional)
  const ownerMap: Record<string, string> = {}
  // faction side
  factions.forEach((f) => {
    f.territory_region_ids.forEach((rid) => {
      ownerMap[rid] = f.id
    })
  })
  // region side (fallback)
  regions.forEach((r) => {
    if (!ownerMap[r.id]) {
      const firstFactionId = (r as any).faction_ids?.[0]
      if (firstFactionId) ownerMap[r.id] = firstFactionId
    }
  })

  // Compute effective territories per faction
  const effectiveTerr: Record<string, string[]> = {}
  factions.forEach((f) => { effectiveTerr[f.id] = [] })
  Object.entries(ownerMap).forEach(([rid, fid]) => {
    if (effectiveTerr[fid]) effectiveTerr[fid].push(rid)
  })

  // Collect faction group centroids first
  const factionIds = factions.filter((f) => (effectiveTerr[f.id]?.length ?? 0) > 0).map((f) => f.id)
  const standaloneFactions = factions.filter((f) => (effectiveTerr[f.id]?.length ?? 0) === 0)
  const unownedRegions = regions.filter((r) => !ownerMap[r.id])

  // Step 1: Layout faction groups + unowned regions + standalone factions as macro nodes
  const macroNodes: SimNode[] = [
    ...factionIds.map((fid) => {
      const f = factions.find((x) => x.id === fid)!
      return { id: `group-${fid}`, x: f.x || 200, y: f.y || 200 }
    }),
    ...unownedRegions.map((r) => ({ id: r.id, x: r.x || 120, y: r.y || 120 })),
    ...standaloneFactions.map((f, idx) => ({ id: f.id, x: 680, y: 120 + idx * 110 })),
  ]

  // Macro edges: relations between groups / unowned regions
  const macroEdgeSet = new Set<string>()
  const macroLinks: { source: string; target: string }[] = []
  flowEdges.value.forEach((e) => {
    const sOwner = ownerMap[e.source as string]
    const tOwner = ownerMap[e.target as string]
    const sId = sOwner ? `group-${sOwner}` : (e.source as string)
    const tId = tOwner ? `group-${tOwner}` : (e.target as string)
    if (sId === tId) return
    const key = [sId, tId].sort().join('|')
    if (macroEdgeSet.has(key)) return
    macroEdgeSet.add(key)
    if (macroNodes.find((n) => n.id === sId) && macroNodes.find((n) => n.id === tId)) {
      macroLinks.push({ source: sId, target: tId })
    }
  })

  if (macroNodes.length > 0) {
    const macroSim = d3.forceSimulation<SimNode>(macroNodes)
      .force('link', d3.forceLink(macroLinks).id((d: any) => d.id).distance(300).strength(0.6))
      .force('charge', d3.forceManyBody().strength(-500))
      .force('center', d3.forceCenter(600, 400))
      .force('collision', d3.forceCollide(140))
      .stop()
    for (let i = 0; i < 300; i++) macroSim.tick()
  }

  // Apply macro positions: group nodes → faction x/y, unowned regions → region x/y
  macroNodes.forEach((mn) => {
    if (mn.id.startsWith('group-')) {
      const fid = mn.id.slice(6)
      const f = factions.find((x) => x.id === fid)
      if (f) { f.x = mn.x; f.y = mn.y }
    } else {
      const r = regions.find((x) => x.id === mn.id)
      if (r) { r.x = mn.x; r.y = mn.y }
    }
  })

  // Step 2: Layout regions within each faction group
  factions.forEach((f) => {
    const memberIds = effectiveTerr[f.id] ?? []
    if (memberIds.length === 0) return
    const memberRegions = memberIds
      .map((rid) => regions.find((r) => r.id === rid))
      .filter(Boolean) as typeof regions

    // Arrange in a compact grid within the group
    const cols = Math.ceil(Math.sqrt(memberRegions.length))
    memberRegions.forEach((r, idx) => {
      const col = idx % cols
      const row = Math.floor(idx / cols)
      r.x = (f.x ?? 0) + 30 + col * 120
      r.y = (f.y ?? 0) + 60 + row * 100
    })
  })

  // 布局完成后自动 FitView，确保所有节点可见（需双 tick 等待 DOM 完全更新）
  nextTick(() => nextTick(() => fitView({ padding: 0.15 })))
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

  // Group node click → select the owning faction
  if ((node.data as any)?.kind === 'factionGroup') {
    const factionId = node.id.replace('group-', '')
    const found = worldData.factions.find((f) => f.id === factionId)
    if (found) {
      selectedNode.value = { id: factionId, position: node.position, data: { label: found.name, kind: 'faction' } }
      factionDraft.value = JSON.parse(JSON.stringify(found))
      regionDraft.value = null
    }
    return
  }

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

  // Faction group node — save the faction's x/y
  if ((node.data as any)?.kind === 'factionGroup') {
    const factionId = node.id.replace('group-', '')
    const target = worldData.factions.find((f) => f.id === factionId)
    if (!target) return
    target.x = node.position.x
    target.y = node.position.y
    try {
      await world.updateFaction(projectId.value, target.id, { ...target, id: target.id })
    } catch {
      // non-critical, position will restore on reload
    }
    return
  }

  // Region node — only save if not inside a faction group (standalone)
  const target = worldData.regions.find((r) => r.id === node.id)
  if (!target) return
  // Skip regions that live inside a group (their internal position is layout-managed)
  if (regionOwnerMap.value[target.id]) return
  target.x = node.position.x
  target.y = node.position.y
  try {
    await world.updateRegion(projectId.value, target.id, { ...target, id: target.id })
  } catch {
    // non-critical
  }
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
  focusNodeId.value = null
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

  const warnings = collectWorldCompletenessWarnings()

  if (warnings.length > 0) {
    try {
      const escapeHtml = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      await ElMessageBox.confirm(
        warnings.map((w, i) => `${i + 1}. ${escapeHtml(w)}`).join('<br>'),
        '世界数据完整性提示',
        {
          confirmButtonText: '仍然继续',
          cancelButtonText: '返回完善',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        }
      )
    } catch {
      return
    }
  }

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

async function publishWorld() {
  if (!projectId.value) return

  publishing.value = true
  try {
    const preview = await world.previewPublish(projectId.value)
    if (preview.data.status !== 'ready' || !preview.data.publish_report) {
      await ElMessageBox.alert(
        renderPublishValidationHtml(preview.data),
        '发布前校验未通过',
        {
          confirmButtonText: '知道了',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        },
      )
      return
    }

    try {
      await ElMessageBox.confirm(
        renderPublishPreviewHtml(preview.data),
        '发布前结构化预览',
        {
          confirmButtonText: '确认发布',
          cancelButtonText: '取消',
          type: 'info',
          dangerouslyUseHTMLString: true,
        },
      )
    } catch {
      return
    }

    const res = await world.publish(projectId.value)
    if (res.data.status !== 'published' || !res.data.publish_report) {
      await ElMessageBox.alert(
        renderPublishValidationHtml(res.data),
        '运行态发布失败',
        {
          confirmButtonText: '知道了',
          type: 'warning',
          dangerouslyUseHTMLString: true,
        },
      )
      return
    }

    publishSummary.value = {
      world_version: res.data.world_version || 'unknown',
      regions: Number(res.data.publish_report.regions_compiled || 0),
      factions: Number(res.data.publish_report.factions_compiled || 0),
      power_systems: Number(res.data.publish_report.power_systems_compiled || 0),
      relations: Number(res.data.publish_report.relations_compiled || 0),
      runtime_diff: res.data.runtime_diff ?? preview.data.runtime_diff ?? null,
    }
    ElMessage.success('RuntimeWorldState 已发布')
  } finally {
    publishing.value = false
  }
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

function renderPublishValidationHtml(response: Pick<WorldPublishPreviewResponse, 'errors' | 'warnings' | 'suggestions'>) {
  const lines = [
    ...(response.errors ?? []).map((item) => `错误：${item}`),
    ...(response.warnings ?? []).map((item) => `提示：${item}`),
    ...(response.suggestions ?? []).map((item) => `建议：${item}`),
  ]
  if (lines.length === 0) {
    return '发布前校验未通过，请先完善世界设定。'
  }
  return lines.map((item) => escapeHtml(item)).join('<br>')
}

function renderPublishPreviewHtml(response: WorldPublishPreviewResponse) {
  const report = response.publish_report
  const sections = response.runtime_diff?.sections ?? []
  const sectionBlocks = sections.slice(0, 4).map((section) => {
    const items = section.items.slice(0, 3).map((item) => {
      const title = escapeHtml(item.target_name || item.target_id || item.change_type)
      const effect = escapeHtml(item.effect)
      const compare = item.before || item.after ? `<div class="wb-preview-compare">${escapeHtml(item.before)} → ${escapeHtml(item.after)}</div>` : ''
      return `<div class="wb-preview-item"><strong>${title}</strong><div>${effect}</div>${compare}</div>`
    }).join('')
    return `<div class="wb-preview-section"><div class="wb-preview-title">${escapeHtml(section.label)}</div>${items}</div>`
  }).join('')
  const autofix = (response.runtime_diff?.auto_fix_notes ?? []).slice(0, 3)
    .map((note) => `<div class="wb-preview-note">${escapeHtml(note)}</div>`)
    .join('')
  return [
    report
      ? `即将发布：地区 ${report.regions_compiled} / 势力 ${report.factions_compiled} / 体系 ${report.power_systems_compiled} / 关系 ${report.relations_compiled}`
      : '即将发布运行态世界。',
    sectionBlocks,
    autofix,
  ].filter(Boolean).join('<br>')
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
  --wb-neon-cyan: #2ef2ff;
  --wb-neon-blue: #4d7cff;
  --wb-neon-red: #ff5e6c;
  --wb-neon-gold: #ffc454;
  --wb-neon-green: #49d89f;
  --wb-neon-violet: #b57cff;
  --wb-canvas-bg: radial-gradient(circle at top, rgba(20, 36, 64, 0.92), rgba(6, 12, 24, 0.98));
  --wb-canvas-grid: rgba(46, 242, 255, 0.18);
  --wb-glass-bg: rgba(6, 14, 28, 0.72);
  --wb-panel-solid: rgba(0, 0, 0, 0.3);
  --wb-panel-solid-strong: rgba(0, 0, 0, 0.6);
  --wb-panel-faint: rgba(255, 255, 255, 0.03);
  --wb-panel-hover: rgba(255, 255, 255, 0.06);
  --wb-glass-border: rgba(130, 201, 255, 0.18);
  --wb-glass-border-strong: rgba(255, 255, 255, 0.1);
  --wb-glass-shadow: 0 24px 60px rgba(2, 6, 23, 0.34);
  --wb-panel-glow: -4px 0 32px rgba(46, 242, 255, 0.12);
  --wb-button-glow: 0 0 8px rgba(46, 242, 255, 0.2);
  --wb-text-main: #e7f6ff;
  --wb-text-muted: rgba(231, 246, 255, 0.7);
  --wb-text-soft: #aab2bf;
  --wb-text-dim: #666688;
  --wb-text-placeholder: #555;
  --wb-overlay: rgba(8, 8, 16, 0.6);
  --wb-region-shell: rgba(0, 40, 80, 0.85);
  --wb-region-core: rgba(0, 30, 60, 0.95);
  --wb-faction-internal-core: rgba(10, 20, 60, 0.92);
  --wb-faction-external-core: rgba(50, 10, 10, 0.92);
  --wb-blue-soft: rgba(77, 124, 255, 0.2);
  --wb-blue-soft-strong: rgba(77, 124, 255, 0.3);
  --wb-red-soft: rgba(255, 94, 108, 0.18);
  --wb-red-soft-strong: rgba(255, 94, 108, 0.3);
  --wb-green-soft: rgba(73, 216, 159, 0.18);
  --wb-gold-soft: rgba(255, 196, 84, 0.18);
  --wb-violet-soft: rgba(181, 124, 255, 0.18);
  --wb-tile-default: #3a3a5c;
  --wb-tile-default-bg: rgba(58, 58, 92, 0.18);
  --wb-tile-default-border: rgba(58, 58, 92, 0.5);
  --wb-map-line: rgba(255, 255, 255, 0.28);
  --wb-glow-cyan: 0 0 8px rgba(46, 242, 255, 0.35);
  --wb-glow-cyan-rest: 0 0 4px rgba(46, 242, 255, 0.2), 0 0 12px rgba(46, 242, 255, 0.1);
  --wb-glow-cyan-active: 0 0 10px rgba(46, 242, 255, 0.5), 0 0 28px rgba(46, 242, 255, 0.25);
  --wb-glow-blue: 0 0 12px rgba(77, 124, 255, 0.5);
  --wb-glow-blue-rest: 0 0 4px rgba(77, 124, 255, 0.15), 0 0 12px rgba(77, 124, 255, 0.08);
  --wb-glow-blue-active: 0 0 10px rgba(77, 124, 255, 0.4), 0 0 24px rgba(77, 124, 255, 0.2);
  --wb-glow-red: 0 0 12px rgba(255, 94, 108, 0.45);
  --wb-glow-red-rest: 0 0 4px rgba(255, 94, 108, 0.15), 0 0 12px rgba(255, 94, 108, 0.08);
  --wb-glow-red-active: 0 0 10px rgba(255, 94, 108, 0.4), 0 0 24px rgba(255, 94, 108, 0.2);
  --wb-relation-adjacent: #888899;
  --wb-relation-border: #888899;
  --wb-relation-trade: #f0c040;
  --wb-relation-war: #ff2e88;
  --wb-relation-alliance: var(--wb-neon-cyan);
  --wb-relation-vassal: var(--wb-neon-violet);
  --wb-relation-blockade: var(--wb-neon-red);
  --wb-relation-teleport: var(--wb-neon-green);
  --wb-relation-connection: #666688;
  --wb-event-historical-bg: rgba(77, 124, 255, 0.2);
  --wb-event-historical-border: rgba(77, 124, 255, 0.4);
  --wb-event-historical-text: #8ab4ff;
  --wb-event-conflict-bg: rgba(255, 94, 108, 0.2);
  --wb-event-conflict-border: rgba(255, 94, 108, 0.4);
  --wb-event-conflict-text: #ff9aa5;
  --wb-event-growth-bg: rgba(73, 216, 159, 0.2);
  --wb-event-growth-border: rgba(73, 216, 159, 0.4);
  --wb-event-growth-text: #9df0cb;
  --wb-event-custom-bg: rgba(181, 124, 255, 0.2);
  --wb-event-custom-border: rgba(181, 124, 255, 0.4);
  --wb-event-custom-text: #d0afff;
}

.sandbox-page[data-wb-theme='xianxia'] {
  --wb-neon-cyan: #8ad9c4;
  --wb-neon-blue: #8ca1db;
  --wb-neon-red: #d9887e;
  --wb-neon-gold: #d7b26d;
  --wb-neon-green: #86c7a8;
  --wb-neon-violet: #bea4d7;
  --wb-canvas-bg: radial-gradient(circle at top, rgba(42, 38, 60, 0.92), rgba(18, 16, 28, 0.98));
  --wb-canvas-grid: rgba(138, 217, 196, 0.16);
  --wb-glass-bg: rgba(28, 20, 34, 0.72);
  --wb-glass-border: rgba(215, 178, 109, 0.2);
  --wb-panel-glow: -4px 0 32px rgba(138, 217, 196, 0.12);
  --wb-button-glow: 0 0 8px rgba(138, 217, 196, 0.22);
  --wb-text-main: #f6efe7;
  --wb-text-muted: rgba(246, 239, 231, 0.72);
  --wb-text-soft: #cfc3b2;
  --wb-text-dim: #7f6f6f;
}

.sandbox-page[data-wb-theme='classic'] {
  --wb-neon-cyan: #6c9dc6;
  --wb-neon-blue: #4f79b8;
  --wb-neon-red: #c26c63;
  --wb-neon-gold: #c89a53;
  --wb-neon-green: #6fa890;
  --wb-neon-violet: #8f79b8;
  --wb-canvas-bg: radial-gradient(circle at top, rgba(34, 40, 54, 0.9), rgba(18, 22, 30, 0.98));
  --wb-canvas-grid: rgba(108, 157, 198, 0.14);
  --wb-glass-bg: rgba(18, 24, 34, 0.74);
  --wb-glass-border: rgba(149, 174, 207, 0.18);
  --wb-panel-glow: -4px 0 32px rgba(108, 157, 198, 0.12);
  --wb-button-glow: 0 0 8px rgba(108, 157, 198, 0.2);
  --wb-text-main: #e6edf5;
  --wb-text-muted: rgba(230, 237, 245, 0.72);
  --wb-text-soft: #aab3bf;
  --wb-text-dim: #6f7886;
}

.sandbox-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: color-mix(in srgb, var(--wb-panel-solid) 88%, var(--color-surface-1));
  border: 1px solid var(--wb-glass-border);
  color: var(--wb-text-main);
  font-size: 0.9rem;
}

.finalize-alert {
  margin-bottom: 8px;
}

.publish-diff-card {
  margin-bottom: 8px;
  border: 1px solid var(--color-surface-l2);
  background: var(--color-surface-l1);
}

.publish-diff-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 12px;
}

.publish-diff-section:last-child {
  margin-bottom: 0;
}

.publish-diff-section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
}

.publish-diff-item {
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--color-base);
  border: 1px solid var(--color-surface-l2);
}

.publish-diff-item-title {
  font-weight: 600;
  color: var(--color-text-primary);
}

.publish-diff-item-effect,
.publish-diff-item-compare,
.publish-diff-item-note,
.publish-autofix-note {
  margin-top: 4px;
  color: var(--color-text-secondary);
  line-height: 1.6;
}

.publish-autofix-block {
  border-top: 1px dashed var(--color-surface-l2);
  padding-top: 12px;
}

.sandbox-layout {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 340px) 1fr;
  gap: 16px;
  position: relative;
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
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(380px, calc(100% - 364px));
  border-left: 1px solid var(--wb-glass-border);
  z-index: 12;
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1),
              opacity 0.25s ease,
              box-shadow 0.25s ease;
  transform: translateX(calc(100% + 12px));
}

.right-panel.open {
  transform: translateX(0);
  box-shadow: var(--wb-panel-glow), var(--wb-glass-shadow);
}

.panel-card {
  margin-bottom: 12px;
  border-color: var(--wb-glass-border);
  background: transparent;
}

.panel-card :deep(.system-card__body) {
  display: grid;
  gap: 14px;
}

.panel-card :deep(.system-card__header) {
  border-bottom: 1px solid var(--wb-glass-border);
}

.panel-card :deep(.system-card__title) {
  color: var(--wb-neon-cyan);
}

.panel-card :deep(.el-input__wrapper),
.panel-card :deep(.el-textarea__inner),
.panel-card :deep(.el-select .el-input__wrapper) {
  background: var(--wb-panel-solid);
  border-color: var(--wb-glass-border-strong);
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
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.world-meta-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.world-meta-stat {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--wb-glass-border);
  background: var(--wb-panel-solid);
  display: grid;
  gap: 6px;
}

.world-meta-stat span {
  color: var(--color-text-secondary);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.world-meta-stat strong {
  color: var(--wb-neon-cyan);
  font-size: 15px;
  line-height: 1.4;
}

.world-meta-copy {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.7;
}

.world-meta-form {
  display: grid;
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

.canvas-state-shell {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100%;
  padding: var(--spacing-6);
}

.canvas-empty-actions {
  display: flex;
  gap: var(--spacing-2);
  flex-wrap: wrap;
}

/* WorldBuilder KeyFrame Animations */
@keyframes wb-glow-pulse {
  0%   { box-shadow: var(--wb-glow-cyan-rest); }
  100% { box-shadow: var(--wb-glow-cyan-active); }
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
  background: var(--wb-glass-border);
  flex-shrink: 0;
}

.right-panel-section-label {
  padding: 6px 12px 4px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 1px;
  color: var(--wb-neon-cyan);
  border-top: 1px solid var(--wb-glass-border);
  opacity: 0.7;
  text-transform: uppercase;
}

.wb-icon-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--wb-panel-solid-strong);
  border: 1px solid var(--wb-glass-border);
  border-radius: 6px;
  color: var(--wb-text-soft);
  cursor: pointer;
  font-size: 12px;
  backdrop-filter: blur(8px);
  transition: all 0.2s ease;
}

.wb-icon-btn:hover {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-neon-cyan);
  box-shadow: var(--wb-button-glow);
}

.view-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--wb-text-placeholder);
  gap: 12px;
}

.placeholder-icon {
  font-size: 48px;
  opacity: 0.4;
}

.view-placeholder p {
  font-size: 14px;
  color: var(--wb-text-dim);
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
/* Right panel animation */
.right-panel:not(.open) {
  opacity: 0;
  pointer-events: none;
}

.import-preview {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid var(--wb-glass-border-strong);
  border-radius: 8px;
  background: var(--wb-panel-faint);
}
.import-preview h4 {
  margin: 0 0 8px;
  color: var(--wb-neon-cyan);
}
.preview-section {
  margin-bottom: 8px;
}
.preview-card {
  padding: 4px 8px;
  margin: 2px 0;
  border-radius: 4px;
  background: var(--wb-panel-hover);
  font-size: 12px;
}

@media (max-width: 1100px) {
  .sandbox-page {
    height: auto;
    min-height: calc(100vh - 96px);
  }

  .sandbox-layout {
    grid-template-columns: 1fr;
  }

  .canvas-panel {
    height: 56vh;
  }

  .right-panel {
    width: 100%;
    max-width: none;
  }
}

@media (max-width: 720px) {
  .world-meta-grid,
  .stats-grid {
    grid-template-columns: 1fr;
  }
}
</style>
