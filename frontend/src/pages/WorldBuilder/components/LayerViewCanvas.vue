<template>
  <div class="layer-view">
    <div
      v-for="layer in computedLayers"
      :key="layer.level"
      class="layer-band"
      :style="{ borderColor: layer.color }"
    >
      <div class="layer-label" :style="{ color: layer.color }">{{ layer.name }}</div>
      <div class="layer-nodes">
        <div
          v-for="node in layer.nodes"
          :key="node.id"
          class="lv-node"
          :style="{ borderColor: layer.color, boxShadow: `0 0 8px ${layer.color}40` }"
          @click="$emit('node-click', node.id)"
        >
          {{ node.name }}
        </div>
        <div v-if="layer.nodes.length === 0" class="lv-empty">暂无节点</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface RegionData {
  id: string
  name: string
  tags?: string[]
}

const props = defineProps<{
  regions: RegionData[]
}>()

defineEmits<{ (e: 'node-click', id: string): void }>()

const LAYER_COLORS = ['#2ef2ff', '#4d7cff', '#ff2e88', '#ffc42e', '#2eff8a']
const LAYER_NAMES: Record<number, string> = {
  1: '下界',
  2: '中界',
  3: '上界',
  4: '仙界',
  5: '神界',
}

const computedLayers = computed(() => {
  // 解析 regions 的 tags 中的 layer:N 标签
  const layerMap = new Map<number, RegionData[]>()

  props.regions.forEach(r => {
    let layerNum = 0 // 默认归入"未分层"
    if (r.tags) {
      const layerTag = r.tags.find(t => /^layer:\d+$/.test(t))
      if (layerTag) {
        layerNum = parseInt(layerTag.split(':')[1], 10)
      }
    }
    if (!layerMap.has(layerNum)) layerMap.set(layerNum, [])
    layerMap.get(layerNum)!.push(r)
  })

  // 如果没有任何 layer tag，创建默认单层
  if (layerMap.size === 0) {
    layerMap.set(0, [])
  }

  const levels = Array.from(layerMap.keys()).sort((a, b) => b - a) // 高层在上
  return levels.map((level, idx) => ({
    level,
    name: level === 0 ? '未分层' : (LAYER_NAMES[level] || `第${level}层`),
    color: LAYER_COLORS[idx % LAYER_COLORS.length],
    nodes: layerMap.get(level) || [],
  }))
})
</script>

<style scoped>
.layer-view {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  overflow-y: auto;
}

.layer-band {
  border: 1px solid;
  border-radius: 12px;
  padding: 16px;
  background: rgba(0, 0, 0, 0.3);
  backdrop-filter: blur(6px);
}

.layer-label {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  letter-spacing: 1px;
}

.layer-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.lv-node {
  padding: 8px 16px;
  border: 1px solid;
  border-radius: 8px;
  background: rgba(13, 13, 20, 0.7);
  color: #e0e0e0;
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s ease;
}

.lv-node:hover {
  transform: scale(1.05);
  filter: brightness(1.2);
}

.lv-empty {
  font-size: 12px;
  color: #555;
  font-style: italic;
}
</style>
