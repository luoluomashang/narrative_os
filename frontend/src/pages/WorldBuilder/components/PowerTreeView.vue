<template>
  <div class="power-tree">
    <div
      v-for="(level, idx) in levels"
      :key="idx"
      class="level-row"
    >
      <div
        class="level-node"
        :class="{ active: activeLevel !== undefined && idx <= activeLevel }"
      >
        <div class="level-rank">{{ idx + 1 }}</div>
        <div class="level-info">
          <div class="level-name">{{ level.name }}</div>
          <div v-if="level.description" class="level-desc">{{ level.description }}</div>
          <div v-if="level.requirements" class="level-req">⬆ {{ level.requirements }}</div>
        </div>
      </div>
      <div v-if="idx < levels.length - 1" class="level-connector">
        <div class="connector-line"></div>
      </div>
    </div>
    <div v-if="levels.length === 0" class="tree-empty">暂无等级定义</div>
  </div>
</template>

<script setup lang="ts">
interface PowerLevel {
  name: string
  description: string
  requirements: string
}

defineProps<{
  levels: PowerLevel[]
  activeLevel?: number
}>()
</script>

<style scoped>
.power-tree {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
  padding: 12px 0;
}

.level-row {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}

.level-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  background: var(--wb-blue-soft);
  border: 1px solid var(--wb-neon-blue);
  border-radius: 8px;
  min-width: 200px;
  max-width: 280px;
  transition: all 0.2s ease;
}

.level-node.active {
  box-shadow: var(--wb-glow-blue);
  border-color: var(--wb-neon-blue);
  background: var(--wb-blue-soft-strong);
}

.level-rank {
  min-width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--wb-blue-soft-strong);
  border: 1px solid var(--wb-neon-blue);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: var(--wb-neon-blue);
}

.level-info {
  flex: 1;
  min-width: 0;
}

.level-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--wb-text-main);
}

.level-desc {
  font-size: 11px;
  color: var(--wb-text-soft);
  margin-top: 2px;
}

.level-req {
  font-size: 10px;
  color: var(--wb-text-muted);
  margin-top: 4px;
}

.level-connector {
  display: flex;
  justify-content: center;
  height: 20px;
}

.connector-line {
  width: 2px;
  height: 100%;
  border-left: 2px dashed color-mix(in srgb, var(--wb-neon-blue) 40%, transparent);
}

.tree-empty {
  font-size: 12px;
  color: var(--wb-text-dim);
  font-style: italic;
  text-align: center;
  padding: 16px;
}
</style>
