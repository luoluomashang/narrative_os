<template>
  <span class="n-typewriter">{{ displayed }}<span class="cursor">|</span></span>
</template>

<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{
  text: string
  speed?: number
}>()

const displayed = ref('')
let timer: ReturnType<typeof setTimeout> | null = null
let idx = 0

function reset() {
  if (timer) clearTimeout(timer)
  displayed.value = ''
  idx = 0
  tick()
}

function tick() {
  if (idx >= props.text.length) return
  displayed.value += props.text[idx++]
  timer = setTimeout(tick, props.speed ?? 35)
}

watch(() => props.text, reset, { immediate: true })

onUnmounted(() => {
  if (timer) clearTimeout(timer)
})
</script>

<style scoped>
.n-typewriter {
  font-family: inherit;
}
.cursor {
  animation: cursor-blink 1s step-start infinite;
  color: var(--color-ai-active);
}
</style>
