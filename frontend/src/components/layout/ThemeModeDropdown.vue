<template>
  <el-dropdown trigger="click" @command="handleCommand">
    <el-button text circle class="theme-mode-trigger" :aria-label="`主题模式：${currentOption.label}`">
      <el-icon><component :is="currentOption.icon" /></el-icon>
    </el-button>

    <template #dropdown>
      <el-dropdown-menu>
        <el-dropdown-item v-for="option in options" :key="option.value" :command="option.value">
          <span class="theme-mode-option">
            <span class="theme-mode-option__label">
              <el-icon><component :is="option.icon" /></el-icon>
              <span>{{ option.label }}</span>
            </span>
            <el-icon v-if="themeMode === option.value"><Check /></el-icon>
          </span>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Check, Monitor, Moon, Sunny } from '@element-plus/icons-vue'
import { useThemeMode, type ThemeMode } from '@/composables/useThemeMode'

const { themeMode, setThemeMode } = useThemeMode()

const options = [
  { value: 'light', label: '浅色', icon: Sunny },
  { value: 'dark', label: '深色', icon: Moon },
  { value: 'system', label: '跟随系统', icon: Monitor },
] as const satisfies Array<{ value: ThemeMode; label: string; icon: typeof Sunny }>

const currentOption = computed(() => options.find((option) => option.value === themeMode.value) ?? options[0])

function handleCommand(command: ThemeMode) {
  setThemeMode(command)
}
</script>

<style scoped>
.theme-mode-trigger {
  color: var(--color-text-2);
}

.theme-mode-trigger:hover {
  color: var(--color-text-1);
}

.theme-mode-option {
  min-width: 150px;
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--spacing-4);
}

.theme-mode-option__label {
  display: inline-flex;
  align-items: center;
  gap: var(--spacing-2);
}
</style>