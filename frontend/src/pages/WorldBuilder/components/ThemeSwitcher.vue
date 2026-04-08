<template>
  <div class="theme-switcher">
    <button
      v-for="t in themes"
      :key="t.key"
      class="theme-btn"
      :class="{ active: modelValue === t.key }"
      :title="t.label"
      @click="emit('update:modelValue', t.key)"
    >
      <span class="theme-icon">{{ t.icon }}</span>
    </button>
  </div>
</template>

<script setup lang="ts">
export type WbTheme = 'cyberpunk' | 'xianxia' | 'classic'

defineProps<{ modelValue: WbTheme }>()
const emit = defineEmits<{ 'update:modelValue': [value: WbTheme] }>()

const themes: { key: WbTheme; icon: string; label: string }[] = [
  { key: 'cyberpunk', icon: '⚡', label: '赛博科幻' },
  { key: 'xianxia', icon: '☯', label: '修仙' },
  { key: 'classic', icon: '○', label: '经典' },
]
</script>

<style scoped>
.theme-switcher {
  display: flex;
  gap: 4px;
  background: rgba(0, 0, 0, 0.5);
  border: 1px solid var(--wb-glass-border);
  border-radius: 8px;
  padding: 3px;
  backdrop-filter: blur(8px);
}

.theme-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  cursor: pointer;
  transition: all 0.2s ease;
}

.theme-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(255, 255, 255, 0.15);
}

.theme-btn.active {
  background: rgba(46, 242, 255, 0.12);
  border-color: var(--wb-neon-cyan, #2ef2ff);
  box-shadow: 0 0 6px rgba(46, 242, 255, 0.25);
}

.theme-icon {
  font-size: 14px;
  line-height: 1;
}
</style>
