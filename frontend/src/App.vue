<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import TopBar from '@/components/layout/TopBar.vue'
import Sidebar from '@/components/layout/Sidebar.vue'
import MainContent from '@/components/layout/MainContent.vue'
import client from '@/api/client'
import { useThemeMode } from '@/composables/useThemeMode'
import type { CostResponse } from '@/types/api'

const { initThemeMode, resolvedTheme, themeMode } = useThemeMode()
initThemeMode()

const backendOnline = ref<boolean | null>(null)
const cost = ref<CostResponse | null>(null)
const isMobileLayout = ref(false)
const isMobileNavigationOpen = ref(false)

let healthTimer: ReturnType<typeof setInterval> | undefined
let costTimer: ReturnType<typeof setInterval> | undefined
let mediaQuery: MediaQueryList | undefined

function updateViewportState(event?: MediaQueryList | MediaQueryListEvent) {
  const matches = event?.matches ?? mediaQuery?.matches ?? false
  isMobileLayout.value = matches
  if (!matches) {
    isMobileNavigationOpen.value = false
  }
}

async function checkHealth() {
  try {
    await client.get('/health')
    backendOnline.value = true
  } catch {
    backendOnline.value = false
  }
}

async function fetchCost() {
  try {
    const response = await client.get<CostResponse>('/cost/summary')
    cost.value = response.data
  } catch {
    cost.value = null
  }
}

function openMobileNavigation() {
  isMobileNavigationOpen.value = true
}

function closeMobileNavigation() {
  isMobileNavigationOpen.value = false
}

onMounted(() => {
  mediaQuery = window.matchMedia('(max-width: 960px)')
  updateViewportState(mediaQuery)
  mediaQuery.addEventListener('change', updateViewportState)
  checkHealth()
  fetchCost()
  healthTimer = setInterval(checkHealth, 15_000)
  costTimer = setInterval(fetchCost, 30_000)
})

onUnmounted(() => {
  mediaQuery?.removeEventListener('change', updateViewportState)
  if (healthTimer) clearInterval(healthTimer)
  if (costTimer) clearInterval(costTimer)
})

watch(isMobileLayout, (isMobile) => {
  if (!isMobile) {
    isMobileNavigationOpen.value = false
  }
})
</script>

<template>
  <div class="app-layout" :data-theme="resolvedTheme" :data-theme-mode="themeMode">
    <TopBar
      :backend-online="backendOnline"
      :cost="cost"
      :is-mobile="isMobileLayout"
      @open-navigation="openMobileNavigation"
    />
    <div class="app-body">
      <Sidebar
        :is-mobile="isMobileLayout"
        :is-open="!isMobileLayout || isMobileNavigationOpen"
        @close="closeMobileNavigation"
      />
      <MainContent :backend-online="backendOnline" />
    </div>
  </div>
</template>


