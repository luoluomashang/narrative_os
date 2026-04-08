import { ref, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useBreathingLight(active: Ref<boolean>) {
  const opacity = ref(0.3)
  let rafId: number | null = null
  let startTime: number | null = null

  function animate(ts: number) {
    if (startTime == null) startTime = ts
    const elapsed = (ts - startTime) / 1000 // seconds
    // 2s sine wave — 30%→80%
    opacity.value = 0.3 + 0.5 * (0.5 + 0.5 * Math.sin((elapsed / 2) * 2 * Math.PI))
    if (active.value) {
      rafId = requestAnimationFrame(animate)
    } else {
      opacity.value = 0.3
      rafId = null
      startTime = null
    }
  }

  watch(
    active,
    (val) => {
      if (val && rafId == null) {
        startTime = null
        rafId = requestAnimationFrame(animate)
      }
    },
    { immediate: true }
  )

  onUnmounted(() => {
    if (rafId != null) cancelAnimationFrame(rafId)
  })

  return { opacity }
}
