<template>
  <div ref="nodeRef" class="region-node">
    <Handle id="region-left" type="target" :position="Position.Left" />
    <Handle id="region-right" type="source" :position="Position.Right" />
    <div class="node-inner">
      <span class="terrain-icon">{{ terrainIcon }}</span>
      <div class="node-content">
        <div class="node-title">{{ data.label }}</div>
        <div class="node-sub">{{ data.regionType || '区域' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{ data: { label: string; regionType?: string } }>()

const nodeRef = ref<HTMLElement | null>(null)

onMounted(() => {
  const el = nodeRef.value
  if (!el) return
  el.style.transform = 'scale(0)'
  el.style.opacity = '0'
  requestAnimationFrame(() => {
    el.style.transition = 'transform 0.3s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.2s ease'
    el.style.transform = 'scale(1)'
    el.style.opacity = '1'
  })
})

const TERRAIN_ICONS: Record<string, string> = {
  mountain: '⛰',
  plain: '🌾',
  plains: '🌾',
  ocean: '🌊',
  sea: '🌊',
  forest: '🌲',
  desert: '🏜',
  swamp: '🌿',
  city: '🏙',
  ruins: '🏚',
}

const terrainIcon = computed(() => {
  const t = (props.data.regionType || '').toLowerCase()
  return TERRAIN_ICONS[t] || '🌐'
})
</script>

<style scoped>
.region-node {
  min-width: 140px;
  min-height: 60px;
  clip-path: polygon(
    12px 0%, calc(100% - 12px) 0%,
    100% 12px, 100% calc(100% - 12px),
    calc(100% - 12px) 100%, 12px 100%,
    0% calc(100% - 12px), 0% 12px
  );
  background: rgba(0, 40, 80, 0.85);
  padding: 2px;
  animation: wb-glow-pulse var(--wb-anim-pulse, 2s) ease-in-out infinite alternate;
  cursor: pointer;
  transition: transform 0.2s ease, filter 0.2s ease;
}

.region-node:hover {
  transform: scale(1.06);
  box-shadow: var(--wb-glow-cyan);
  filter: brightness(1.2);
}

.node-inner {
  clip-path: polygon(
    12px 0%, calc(100% - 12px) 0%,
    100% 12px, 100% calc(100% - 12px),
    calc(100% - 12px) 100%, 12px 100%,
    0% calc(100% - 12px), 0% 12px
  );
  background: rgba(0, 30, 60, 0.95);
  padding: 10px 14px;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1.5px solid var(--wb-neon-cyan, #2ef2ff);
  border-radius: 2px;
  box-shadow: var(--wb-glow-cyan, 0 0 8px #2ef2ff80);
}

.terrain-icon {
  font-size: 20px;
  flex-shrink: 0;
}

.node-content {
  flex: 1;
  min-width: 0;
}

.node-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0f0ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.node-sub {
  margin-top: 2px;
  font-size: 11px;
  color: rgba(46, 242, 255, 0.6);
}

@keyframes wb-glow-pulse {
  0%   { box-shadow: 0 0 4px rgba(46, 242, 255, 0.2), 0 0 12px rgba(46, 242, 255, 0.1); }
  100% { box-shadow: 0 0 10px rgba(46, 242, 255, 0.5), 0 0 28px rgba(46, 242, 255, 0.25); }
}
</style>
