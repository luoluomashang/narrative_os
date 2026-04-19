<template>
  <div
    class="map-view"
    @wheel.prevent="onWheel"
    @mousedown="onPanStart"
    @mousemove="onPanMove"
    @mouseup="onPanEnd"
    @mouseleave="onPanEnd"
  >
    <div
      class="map-canvas"
      :style="{ transform: `translate(${panX}px, ${panY}px) scale(${scale})` }"
    >
      <img
        v-if="mapImageUrl"
        :src="mapImageUrl"
        class="map-bg-image"
        draggable="false"
      />

      <!-- SVG adjacency lines -->
      <svg class="map-adjacency-svg" :width="svgWidth" :height="svgHeight">
        <line
          v-for="edge in adjacencyEdges"
          :key="edge.id"
          :x1="edge.x1" :y1="edge.y1"
          :x2="edge.x2" :y2="edge.y2"
          class="adjacency-line"
        />
      </svg>

      <!-- Territory tiles -->
      <div
        v-for="tile in tileData"
        :key="tile.id"
        class="map-tile"
        :class="{ 'no-owner': !tile.color }"
        :style="{
          left: `${tile.x}px`,
          top: `${tile.y}px`,
          '--tile-color': tile.color || 'var(--wb-tile-default)',
          '--tile-bg': tile.color ? `${tile.color}30` : 'var(--wb-tile-default-bg)',
          '--tile-border': tile.color ? `${tile.color}80` : 'var(--wb-tile-default-border)',
        }"
        @click.stop="$emit('node-click', tile.id)"
      >
        <div class="tile-body">
          <div class="tile-icon">{{ tileIcon(tile.regionType) }}</div>
          <div class="tile-name">{{ tile.name }}</div>
          <div v-if="tile.factionName" class="tile-faction">{{ tile.factionName }}</div>
        </div>
      </div>

      <div v-if="regions.length === 0 && !mapImageUrl" class="map-placeholder">
        <p>暂无地区数据</p>
        <p class="map-hint">请先在图视图创建地区与邻接关系</p>
      </div>
    </div>

    <div class="map-toolbar">
      <label class="upload-btn">
        📁 上传底图
        <input type="file" accept="image/*" @change="onFileSelected" />
      </label>
      <button v-if="mapImageUrl" class="clear-btn" @click="clearMap">清除底图</button>
      <button class="layout-btn" @click="autoTileLayout">⚙ 重排地块</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'

interface RegionData {
  id: string
  name: string
  region_type?: string
  x?: number
  y?: number
}

interface FactionData {
  id: string
  name: string
  color?: string | null
  territory_region_ids: string[]
}

interface RelationData {
  id: string
  source_id: string
  target_id: string
  relation_type: string
}

const props = defineProps<{
  regions: RegionData[]
  factions: FactionData[]
  relations: RelationData[]
  projectId: string
}>()

defineEmits<{ (e: 'node-click', id: string): void }>()

const mapImageUrl = ref<string | null>(null)
const scale = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const panStartX = ref(0)
const panStartY = ref(0)

const TILE_W = 110
const TILE_H = 80

const storageKey = () => `wb-map-img-${props.projectId}`

onMounted(() => {
  const saved = localStorage.getItem(storageKey())
  if (saved) mapImageUrl.value = saved
  // Auto layout on first load if regions have default positions
  if (props.regions.length > 0 && props.regions.every(r => !r.x || !r.y)) {
    autoTileLayout()
  }
})

// Region ownership map — check both faction.territory_region_ids and region.faction_ids
const regionOwnerMap = computed(() => {
  const map: Record<string, FactionData> = {}
  // faction-side: faction lists which regions it owns
  props.factions.forEach((f) => {
    f.territory_region_ids.forEach((rid) => {
      map[rid] = f
    })
  })
  // region-side: region lists which factions it belongs to (take first faction if multiple)
  props.regions.forEach((r) => {
    if (map[r.id]) return // already assigned from faction side
    const firstFactionId = (r as any).faction_ids?.[0]
    if (firstFactionId) {
      const faction = props.factions.find((f) => f.id === firstFactionId)
      if (faction) map[r.id] = faction
    }
  })
  return map
})

// Adjacency relations only
const adjacencyRelations = computed(() =>
  props.relations.filter((r) => r.relation_type === 'adjacent' || r.relation_type === 'border')
)

// Tile data for rendering
const tileData = computed(() =>
  props.regions.map((r) => {
    const owner = regionOwnerMap.value[r.id]
    return {
      id: r.id,
      name: r.name,
      regionType: r.region_type,
      x: r.x || 100,
      y: r.y || 100,
      color: owner?.color || null,
      factionName: owner?.name || null,
    }
  })
)

// SVG edges for adjacency lines
const svgWidth = computed(() => {
  const maxX = Math.max(...tileData.value.map(t => t.x), 800)
  return maxX + TILE_W + 40
})
const svgHeight = computed(() => {
  const maxY = Math.max(...tileData.value.map(t => t.y), 600)
  return maxY + TILE_H + 40
})

const adjacencyEdges = computed(() => {
  const regionMap = new Map(tileData.value.map(t => [t.id, t]))
  return adjacencyRelations.value
    .map((rel) => {
      const s = regionMap.get(rel.source_id)
      const t = regionMap.get(rel.target_id)
      if (!s || !t) return null
      return {
        id: rel.id,
        x1: s.x + TILE_W / 2,
        y1: s.y + TILE_H / 2,
        x2: t.x + TILE_W / 2,
        y2: t.y + TILE_H / 2,
      }
    })
    .filter(Boolean) as { id: string; x1: number; y1: number; x2: number; y2: number }[]
})

function tileIcon(regionType?: string): string {
  const icons: Record<string, string> = {
    city: '🏙', mountain: '⛰', forest: '🌲', plain: '🌾',
    desert: '🏜', ocean: '🌊', swamp: '🌿', island: '🏝',
    cave: '🕳', ruins: '🏚', capital: '🏰', village: '🏘',
  }
  return icons[regionType || ''] || '◈'
}

// Auto-layout: place tiles using adjacency-aware compact grid
function autoTileLayout() {
  const regions = props.regions
  if (regions.length === 0) return

  // Build adjacency graph
  const adj: Record<string, Set<string>> = {}
  regions.forEach(r => { adj[r.id] = new Set() })
  adjacencyRelations.value.forEach(rel => {
    if (adj[rel.source_id]) adj[rel.source_id].add(rel.target_id)
    if (adj[rel.target_id]) adj[rel.target_id].add(rel.source_id)
  })

  // BFS placement from the most-connected region
  const placed = new Map<string, { col: number; row: number }>()
  const cellOccupied = new Set<string>()

  // Sort by connection count desc to start from hub
  const sorted = [...regions].sort((a, b) => (adj[b.id]?.size || 0) - (adj[a.id]?.size || 0))

  const queue: string[] = []
  const centerCol = Math.ceil(Math.sqrt(regions.length))
  const startRow = Math.floor(centerCol / 2)
  const startCol = Math.floor(centerCol / 2)

  // Place first node at center
  placed.set(sorted[0].id, { col: startCol, row: startRow })
  cellOccupied.add(`${startCol},${startRow}`)
  queue.push(sorted[0].id)

  // BFS to place neighbors
  const directions = [
    { dc: 1, dr: 0 }, { dc: -1, dr: 0 },
    { dc: 0, dr: 1 }, { dc: 0, dr: -1 },
    { dc: 1, dr: 1 }, { dc: -1, dr: -1 },
  ]

  while (queue.length > 0) {
    const current = queue.shift()!
    const pos = placed.get(current)!
    const neighbors = adj[current] || new Set()
    for (const nid of neighbors) {
      if (placed.has(nid)) continue
      // Find nearest free cell to current
      for (const dir of directions) {
        const nc = pos.col + dir.dc
        const nr = pos.row + dir.dr
        const key = `${nc},${nr}`
        if (!cellOccupied.has(key)) {
          placed.set(nid, { col: nc, row: nr })
          cellOccupied.add(key)
          queue.push(nid)
          break
        }
      }
    }
  }

  // Place any remaining unconnected regions
  let nextCol = 0
  let nextRow = Math.max(...[...placed.values()].map(p => p.row), 0) + 2
  for (const r of regions) {
    if (placed.has(r.id)) continue
    placed.set(r.id, { col: nextCol, row: nextRow })
    cellOccupied.add(`${nextCol},${nextRow}`)
    nextCol++
    if (nextCol >= centerCol) { nextCol = 0; nextRow++ }
  }

  // Apply positions
  const offsetX = 60
  const offsetY = 60
  const gapX = TILE_W + 20
  const gapY = TILE_H + 20
  placed.forEach((pos, rid) => {
    const r = regions.find(x => x.id === rid)
    if (r) {
      r.x = offsetX + pos.col * gapX
      r.y = offsetY + pos.row * gapY
    }
  })
}

// Trigger re-layout when adjacency changes
watch(() => adjacencyRelations.value.length, () => {
  // Don't auto-layout if user has positioned regions
})

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input?.files?.[0]
  if (!file) return
  if (file.size > 5 * 1024 * 1024) {
    alert('地图图片不能超过 5MB')
    return
  }
  const reader = new FileReader()
  reader.onload = (e) => {
    const dataUrl = e.target?.result as string
    mapImageUrl.value = dataUrl
    try {
      localStorage.setItem(storageKey(), dataUrl)
    } catch {
      alert('图片过大，无法缓存到本地存储')
    }
  }
  reader.readAsDataURL(file)
}

function clearMap() {
  mapImageUrl.value = null
  localStorage.removeItem(storageKey())
}

function onWheel(e: WheelEvent) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1
  scale.value = Math.max(0.2, Math.min(3, scale.value + delta))
}

function onPanStart(e: MouseEvent) {
  if (e.button !== 0) return
  isPanning.value = true
  panStartX.value = e.clientX - panX.value
  panStartY.value = e.clientY - panY.value
}

function onPanMove(e: MouseEvent) {
  if (!isPanning.value) return
  panX.value = e.clientX - panStartX.value
  panY.value = e.clientY - panStartY.value
}

function onPanEnd() {
  isPanning.value = false
}
</script>

<style scoped>
.map-view {
  width: 100%;
  height: 100%;
  position: relative;
  overflow: hidden;
  cursor: grab;
  background: var(--wb-canvas-bg);
}

.map-view:active {
  cursor: grabbing;
}

.map-canvas {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  min-width: 100%;
  min-height: 100%;
}

.map-bg-image {
  display: block;
  max-width: none;
  user-select: none;
  pointer-events: none;
}

.map-adjacency-svg {
  position: absolute;
  top: 0;
  left: 0;
  pointer-events: none;
  z-index: 1;
}

.adjacency-line {
  stroke: var(--wb-map-line);
  stroke-width: 2;
  stroke-dasharray: 6 4;
}

.map-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: var(--wb-text-placeholder);
  font-size: 16px;
}

.map-hint {
  font-size: 12px;
  color: var(--wb-text-dim);
  margin-top: 4px;
}

.map-tile {
  position: absolute;
  width: 110px;
  cursor: pointer;
  z-index: 5;
  transition: transform 0.15s;
}

.map-tile:hover {
  transform: scale(1.08);
  z-index: 10;
}

.tile-body {
  background: var(--tile-bg);
  border: 2px solid var(--tile-border);
  border-radius: 10px;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  backdrop-filter: blur(4px);
}

.map-tile:hover .tile-body {
  border-color: var(--tile-color);
  box-shadow: 0 0 12px var(--tile-bg);
}

.tile-icon {
  font-size: 20px;
}

.tile-name {
  font-size: 11px;
  font-weight: 600;
  color: var(--wb-text-main);
  text-align: center;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}

.tile-faction {
  font-size: 9px;
  color: var(--tile-color);
  opacity: 0.7;
}

.map-toolbar {
  position: absolute;
  top: 12px;
  left: 12px;
  display: flex;
  gap: 8px;
  z-index: 10;
}

.upload-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  background: var(--wb-panel-solid-strong);
  border: 1px solid var(--wb-glass-border);
  border-radius: 6px;
  color: var(--wb-text-main);
  cursor: pointer;
  font-size: 12px;
  backdrop-filter: blur(8px);
  transition: all 0.2s;
}

.upload-btn:hover {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-neon-cyan);
}

.upload-btn input[type="file"] {
  display: none;
}

.layout-btn {
  padding: 6px 12px;
  background: var(--wb-panel-solid-strong);
  border: 1px solid var(--wb-glass-border);
  border-radius: 6px;
  color: var(--wb-text-main);
  cursor: pointer;
  font-size: 12px;
  backdrop-filter: blur(8px);
  transition: all 0.2s;
}

.layout-btn:hover {
  color: var(--wb-neon-cyan);
  border-color: var(--wb-neon-cyan);
}

.clear-btn {
  padding: 6px 12px;
  background: var(--wb-red-soft);
  border: 1px solid color-mix(in srgb, var(--wb-neon-red) 35%, transparent);
  border-radius: 6px;
  color: var(--wb-neon-red);
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: var(--wb-red-soft-strong);
}
</style>
