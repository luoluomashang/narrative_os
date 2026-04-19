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
  background: var(--wb-neon-blue);
}
.scope-internal .node-inner {
  background: var(--wb-faction-internal-core);
  border: 1.5px solid var(--wb-neon-blue);
  box-shadow: var(--wb-glow-blue);
}

/* --- External faction: red glow --- */
.scope-external {
  background: var(--wb-neon-red);
}
.scope-external .node-inner {
  background: var(--wb-faction-external-core);
  border: 1.5px solid var(--wb-neon-red);
  box-shadow: var(--wb-glow-red);
}

.node-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--wb-text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 110px;
}

.node-sub {
  font-size: 10px;
}

.scope-internal .node-sub {
  color: color-mix(in srgb, var(--wb-neon-blue) 70%, transparent);
}

.scope-external .node-sub {
  color: color-mix(in srgb, var(--wb-neon-red) 70%, transparent);
}

@keyframes wb-faction-pulse {
  0%   { box-shadow: var(--wb-glow-blue-rest); }
  100% { box-shadow: var(--wb-glow-blue-active); }
}

.scope-external {
  animation-name: wb-faction-pulse-red;
}

@keyframes wb-faction-pulse-red {
  0%   { box-shadow: var(--wb-glow-red-rest); }
  100% { box-shadow: var(--wb-glow-red-active); }
}
</style>
