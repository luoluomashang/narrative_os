<template>
  <div class="skill-card" :draggable="true" @dragstart="onDragStart">
    <div class="skill-header">
      <span class="skill-name">{{ skill.name }}</span>
      <NTag :label="skill.genre" />
    </div>
    <p class="skill-desc">{{ skill.description.slice(0, 14) }}</p>
    <div class="skill-controls">
      <label>情感倾向</label>
      <NSlider v-model="emotionVal" :min="0" :max="10" />
      <label>句长</label>
      <NSlider v-model="sentenceLen" :min="0" :max="10" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import NTag from '@/components/common/NTag.vue'
import NSlider from '@/components/common/NSlider.vue'

export interface SkillDef {
  id: string
  name: string
  description: string
  genre: string
}

const props = defineProps<{ skill: SkillDef }>()
const emotionVal = ref(5)
const sentenceLen = ref(5)

function onDragStart(e: DragEvent) {
  e.dataTransfer?.setData('skill-id', props.skill.id)
}
</script>

<style scoped>
.skill-card {
  width: 280px;
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-card);
  padding: var(--spacing-md);
  cursor: grab;
  transition: border-color 150ms;
}
.skill-card:hover { border-color: var(--color-ai-active); }
.skill-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }
.skill-name { font-weight: 600; font-size: 14px; }
.skill-desc { font-size: 12px; color: var(--color-text-secondary); margin-bottom: 10px; }
.skill-controls { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--color-text-secondary); }
</style>
