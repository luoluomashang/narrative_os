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
      <div v-else class="map-placeholder">
        <p>暂无地图图片</p>
        <p class="map-hint">请上传地图底图以开始使用</p>
      </div>

      <!-- Overlay region nodes on the map -->
      <div
        v-for="region in regions"
        :key="region.id"
        class="map-node"
        :style="{ left: `${region.x || 100}px`, top: `${region.y || 100}px` }"
        @click.stop="$emit('node-click', region.id)"
      >
        <div class="map-node-dot"></div>
        <div class="map-node-label">{{ region.name }}</div>
      </div>
    </div>

    <div class="map-toolbar">
      <label class="upload-btn">
        📁 上传地图
        <input type="file" accept="image/*" @change="onFileSelected" />
      </label>
      <button v-if="mapImageUrl" class="clear-btn" @click="clearMap">清除地图</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'

interface RegionData {
  id: string
  name: string
  x?: number
  y?: number
}

const props = defineProps<{
  regions: RegionData[]
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

const storageKey = () => `wb-map-img-${props.projectId}`

onMounted(() => {
  const saved = localStorage.getItem(storageKey())
  if (saved) mapImageUrl.value = saved
})

function onFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input?.files?.[0]
  if (!file) return

  // Validate file size (max 5MB for localStorage)
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

.map-placeholder {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 400px;
  color: #555;
  font-size: 16px;
}

.map-hint {
  font-size: 12px;
  color: #444;
  margin-top: 4px;
}

.map-node {
  position: absolute;
  cursor: pointer;
  transform: translate(-50%, -50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  z-index: 5;
}

.map-node-dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--wb-neon-cyan);
  box-shadow: 0 0 8px rgba(46, 242, 255, 0.5);
  transition: transform 0.2s;
}

.map-node:hover .map-node-dot {
  transform: scale(1.5);
}

.map-node-label {
  font-size: 11px;
  color: #e0e0e0;
  background: rgba(0, 0, 0, 0.6);
  padding: 2px 6px;
  border-radius: 4px;
  white-space: nowrap;
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
  background: rgba(0, 0, 0, 0.6);
  border: 1px solid var(--wb-glass-border);
  border-radius: 6px;
  color: #ccc;
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

.clear-btn {
  padding: 6px 12px;
  background: rgba(255, 64, 64, 0.15);
  border: 1px solid rgba(255, 64, 64, 0.3);
  border-radius: 6px;
  color: #ff6060;
  cursor: pointer;
  font-size: 12px;
  transition: all 0.2s;
}

.clear-btn:hover {
  background: rgba(255, 64, 64, 0.3);
}
</style>
