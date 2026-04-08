<template>
  <div class="skill-dsl">
    <div class="filter-row">
      <button
        v-for="g in genres"
        :key="g"
        class="genre-btn"
        :class="{ active: activeGenre === g }"
        @click="activeGenre = g"
      >{{ g }}</button>
    </div>
    <div class="skill-grid">
      <SkillCard
        v-for="s in filteredSkills"
        :key="s.id"
        :skill="s"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import SkillCard, { type SkillDef } from './SkillCard.vue'

const genres = ['全部', '恐怖', '悬疑', '奇幻', '武侠', '言情']
const activeGenre = ref('全部')

const skills: SkillDef[] = [
  { id: 'horror-atmosphere', name: '恐怖气氛渲染', description: '营造压抑、阴暗氛围', genre: '恐怖' },
  { id: 'mystery-clue', name: '悬疑线索埋设', description: '隐性伏笔与反转技法', genre: '悬疑' },
  { id: 'fantasy-worldbuild', name: '奇幻世界构建', description: '宏观设定与细节一致', genre: '奇幻' },
  { id: 'wuxia-action', name: '武侠打斗描写', description: '节奏感与招式美感', genre: '武侠' },
  { id: 'romance-emotion', name: '言情情感渲染', description: '细腻心理与情感波动', genre: '言情' },
]

const filteredSkills = computed(() =>
  activeGenre.value === '全部' ? skills : skills.filter((s) => s.genre === activeGenre.value)
)
</script>

<style scoped>
.skill-dsl { padding: 0; }
.filter-row { display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap; }
.genre-btn {
  background: transparent; border: 1px solid var(--color-surface-l2);
  color: var(--color-text-secondary); padding: 4px 10px;
  border-radius: var(--radius-btn); cursor: pointer; font-size: 12px; transition: all 150ms;
}
.genre-btn:hover, .genre-btn.active {
  background: var(--color-surface-l2); color: var(--color-text-primary);
}
.genre-btn.active { border-color: var(--color-ai-active); color: var(--color-ai-active); }
.skill-grid { display: flex; flex-wrap: wrap; gap: 12px; }
</style>
