<template>
  <aside class="char-list">
    <div class="char-list-header">
      <span class="char-list-title">角色列表</span>
      <button class="char-new-btn" @click="$emit('create')">+ 新建</button>
    </div>
    <div
      v-for="c in characters"
      :key="c.name"
      class="char-item"
      :class="{ active: selected === c.name, dead: !c.is_alive }"
      :style="{ background: emotionBg(c.emotion) }"
      @click="$emit('select', c.name)"
    >
      <span class="char-name" :class="{ 'dead-name': !c.is_alive }">{{ c.name }}</span>
      <span class="char-arc-badge">{{ arcShort(c.arc_stage) }}</span>
    </div>
    <div v-if="!characters.length" class="char-list-empty">暂无角色，点击"+ 新建"创建</div>
  </aside>
</template>

<script setup lang="ts">
import type { CharacterSummary } from '@/types/api'

defineProps<{
  characters: CharacterSummary[]
  selected: string | null
}>()

defineEmits<{
  (e: 'select', name: string): void
  (e: 'create'): void
}>()

function arcShort(stage: string): string {
  const map: Record<string, string> = { 防御: '防', 裂缝: '裂', 代偿: '偿', 承认: '认', 改变: '变' }
  return map[stage] ?? stage.slice(0, 1)
}

function emotionBg(emotion: string): string {
  const e = (emotion ?? '').toLowerCase()
  if (e === 'happy' || e === '愉快' || e === '兴奋' || e === '开心') return 'rgba(63,190,138,0.10)'
  if (e === 'anxious' || e === '焦虑' || e === 'angry' || e === '愤怒' || e === '恐惧' || e === '紧张') return 'rgba(255,180,0,0.10)'
  if (e === 'sad' || e === '悲伤' || e === '惆怅' || e === '失落') return 'rgba(120,130,255,0.10)'
  return ''
}
</script>

<style scoped>
.char-list {
  width: 220px;
  flex-shrink: 0;
  background: var(--color-surface-l1);
  border-radius: 20px;
  border: 1px solid var(--color-surface-l2);
  box-shadow: 0 18px 36px rgba(0, 0, 0, 0.22);
  overflow-y: auto;
}
.char-list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-bottom: 1px solid var(--color-surface-l2);
}
.char-list-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.char-new-btn {
  background: var(--color-ai-active);
  color: #0a0a0b;
  border: none;
  padding: 3px 10px;
  border-radius: var(--radius-btn);
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: opacity 150ms;
}
.char-new-btn:hover { opacity: 0.85; }
.char-item {
  padding: 10px 12px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-left: 2px solid transparent;
  transition: all 150ms;
}
.char-item:hover, .char-item.active { background: var(--color-surface-l2); }
.char-item.active { border-left-color: var(--color-ai-active); }
.char-item.dead { opacity: 0.5; }
.char-name {
  font-size: 14px;
  color: var(--color-text-primary);
}
.dead-name {
  text-decoration: line-through;
  color: var(--color-text-secondary);
}
.char-arc-badge {
  font-size: 11px;
  background: var(--color-surface-l2);
  color: var(--color-text-secondary);
  padding: 1px 6px;
  border-radius: 4px;
}
.char-list-empty {
  padding: 24px 12px;
  color: var(--color-text-secondary);
  font-size: 13px;
  text-align: center;
}

@media (max-width: 960px) {
  .char-list {
    width: 100%;
    max-height: 240px;
  }
}
</style>
