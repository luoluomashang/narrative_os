import { computed, ref } from 'vue'

export type ShellBannerTone = 'info' | 'warning' | 'danger'

export interface ShellBannerAction {
  label: string
  to?: string
}

export interface ShellBanner {
  id: string
  tone: ShellBannerTone
  title: string
  message: string
  action?: ShellBannerAction
}

const bannerMap = ref<Record<string, ShellBanner>>({})

export function useShellBanners() {
  const shellBanners = computed(() => Object.values(bannerMap.value))

  function setShellBanner(banner: ShellBanner) {
    bannerMap.value = {
      ...bannerMap.value,
      [banner.id]: banner,
    }
  }

  function clearShellBanner(bannerId: string) {
    if (!bannerMap.value[bannerId]) return
    const nextState = { ...bannerMap.value }
    delete nextState[bannerId]
    bannerMap.value = nextState
  }

  return {
    shellBanners,
    setShellBanner,
    clearShellBanner,
  }
}
