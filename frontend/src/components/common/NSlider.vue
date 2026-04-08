<template>
  <div class="n-slider">
    <input
      type="range"
      class="n-slider__input"
      :min="min"
      :max="max"
      :step="step"
      :value="modelValue"
      :style="gradient ? { '--slider-gradient': gradient } : {}"
      @input="emit('update:modelValue', Number(($event.target as HTMLInputElement).value))"
    />
    <div class="n-slider__labels">
      <span>{{ min }}</span>
      <span>{{ modelValue }}</span>
      <span>{{ max }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: number
  min?: number
  max?: number
  step?: number
  gradient?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', val: number): void
}>()
</script>

<style scoped>
.n-slider {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.n-slider__input {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  border-radius: 2px;
  background: var(--slider-gradient, linear-gradient(to right, #2ef2ff, #f5a623));
  outline: none;
  cursor: pointer;
}

.n-slider__input::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--color-text-primary);
  cursor: pointer;
}

.n-slider__labels {
  display: flex;
  justify-content: space-between;
  font-size: var(--text-caption);
  color: var(--color-text-secondary);
}
</style>
