import { ref, readonly } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'system'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'narrative-theme-mode'
const themeModeState = ref<ThemeMode>('light')
const resolvedThemeState = ref<ResolvedTheme>('light')

let initialized = false

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') {
    return 'light'
  }

  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function applyTheme(mode: ThemeMode) {
  if (typeof document === 'undefined') {
    return
  }

  const resolved = mode === 'system' ? getSystemTheme() : mode
  const root = document.documentElement

  resolvedThemeState.value = resolved
  root.dataset.themeMode = mode
  root.dataset.theme = resolved
  root.classList.toggle('dark', resolved === 'dark')
  root.style.colorScheme = resolved
}

function syncTheme() {
  applyTheme(themeModeState.value)
}

function setThemeMode(mode: ThemeMode) {
  themeModeState.value = mode
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(STORAGE_KEY, mode)
  }
  syncTheme()
}

function initThemeMode() {
  if (initialized || typeof window === 'undefined') {
    return
  }

  initialized = true
  const storedMode = window.localStorage.getItem(STORAGE_KEY) as ThemeMode | null
  if (storedMode === 'light' || storedMode === 'dark' || storedMode === 'system') {
    themeModeState.value = storedMode
  }

  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
  mediaQuery.addEventListener('change', () => {
    if (themeModeState.value === 'system') {
      syncTheme()
    }
  })

  syncTheme()
}

export function useThemeMode() {
  return {
    themeMode: readonly(themeModeState),
    resolvedTheme: readonly(resolvedThemeState),
    setThemeMode,
    initThemeMode,
  }
}