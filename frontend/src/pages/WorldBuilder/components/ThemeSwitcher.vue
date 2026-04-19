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
  background: var(--wb-panel-solid-strong);
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
  background: var(--wb-panel-hover);
  border-color: var(--wb-glass-border-strong);
}

.theme-btn.active {
  background: color-mix(in srgb, var(--wb-neon-cyan) 12%, transparent);
  border-color: var(--wb-neon-cyan);
  box-shadow: var(--wb-button-glow);
}

.theme-icon {
  font-size: 14px;
  line-height: 1;
}
</style>
