import { ref, watch, onUnmounted } from 'vue'
import type { Ref } from 'vue'

export function useTypewriter(text: Ref<string>, speed = 35) {
  const displayed = ref('')
  let timer: ReturnType<typeof setTimeout> | null = null
  let idx = 0

  function reset() {
    if (timer != null) clearTimeout(timer)
    timer = null
    displayed.value = ''
    idx = 0
    tick()
  }

  function tick() {
    if (idx >= text.value.length) return
    displayed.value += text.value[idx++]
    timer = setTimeout(tick, speed)
  }

  watch(text, reset, { immediate: true })

  onUnmounted(() => {
    if (timer != null) clearTimeout(timer)
  })

  return { displayed }
}
