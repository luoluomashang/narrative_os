<template>
  <div ref="nodeRef" class="faction-node" :class="scopeClass">
    <Handle id="faction-left" type="target" :position="Position.Left" />
    <Handle id="faction-right" type="source" :position="Position.Right" />
    <div class="node-inner">
      <div class="node-title">{{ data.label }}</div>
      <div class="node-sub">{{ data.scope === 'external' ? '域外势力' : '世界内势力' }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Handle, Position } from '@vue-flow/core'

const props = defineProps<{ data: { label: string; scope?: string } }>()

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

const scopeClass = computed(() =>
  props.data.scope === 'external' ? 'scope-external' : 'scope-internal'
)
</script>

<style scoped>
.faction-node {
  min-width: 140px;
  min-height: 60px;
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  padding: 2px;
  cursor: pointer;
  transition: transform 0.18s ease, box-shadow 0.2s ease, filter 0.2s ease;
  animation: wb-faction-pulse var(--wb-anim-pulse, 2s) ease-in-out infinite alternate;
}

.faction-node:hover {
  transform: scale(1.06);
  filter: brightness(1.25);
}

.node-inner {
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  padding: 18px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  gap: 2px;
}

/* --- Internal faction: blue glow --- */
.scope-internal {
  background: var(--wb-neon-blue, #4d7cff);
}
.scope-internal .node-inner {
  background: rgba(10, 20, 60, 0.92);
  border: 1.5px solid var(--wb-neon-blue, #4d7cff);
  box-shadow: var(--wb-glow-blue, 0 0 8px #4d7cff80);
}

/* --- External faction: red glow --- */
.scope-external {
  background: var(--wb-neon-red, #ff4040);
}
.scope-external .node-inner {
  background: rgba(50, 10, 10, 0.92);
  border: 1.5px solid var(--wb-neon-red, #ff4040);
  box-shadow: var(--wb-glow-red, 0 0 8px #ff404080);
}

.node-title {
  font-size: 13px;
  font-weight: 600;
  color: #e0e8ff;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
}

.node-sub {
  font-size: 10px;
}

.scope-internal .node-sub {
  color: rgba(77, 124, 255, 0.7);
}

.scope-external .node-sub {
  color: rgba(255, 64, 64, 0.7);
}

@keyframes wb-faction-pulse {
  0%   { box-shadow: 0 0 4px rgba(77, 124, 255, 0.15), 0 0 12px rgba(77, 124, 255, 0.08); }
  100% { box-shadow: 0 0 10px rgba(77, 124, 255, 0.4), 0 0 24px rgba(77, 124, 255, 0.2); }
}

.scope-external {
  animation-name: wb-faction-pulse-red;
}

@keyframes wb-faction-pulse-red {
  0%   { box-shadow: 0 0 4px rgba(255, 64, 64, 0.15), 0 0 12px rgba(255, 64, 64, 0.08); }
  100% { box-shadow: 0 0 10px rgba(255, 64, 64, 0.4), 0 0 24px rgba(255, 64, 64, 0.2); }
}
</style>
