<template>
  <div class="n-workflow-stepper">
    <div
      v-for="(step, i) in steps"
      :key="i"
      class="stepper-item"
      :class="step.status"
    >
      <div class="stepper-dot">
        <span v-if="step.status === 'done'">✓</span>
        <span v-else-if="step.status === 'active'">●</span>
        <span v-else>○</span>
      </div>
      <div class="stepper-connector" v-if="i < steps.length - 1" />
      <div class="stepper-label">{{ step.label }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  steps: Array<{ label: string; status: 'done' | 'active' | 'pending' }>
  current: number
}>()
</script>

<style scoped>
.n-workflow-stepper {
  display: flex;
  flex-direction: column;
  gap: 0;
}
.stepper-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  position: relative;
  padding-bottom: 16px;
}
.stepper-item:last-child {
  padding-bottom: 0;
}
.stepper-dot {
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
  background: var(--color-surface-l2);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-surface-l2);
}
.stepper-item.done .stepper-dot {
  background: var(--color-accent-soft);
  color: var(--color-ai-active);
  border-color: var(--color-ai-active);
}
.stepper-item.active .stepper-dot {
  background: var(--color-accent-soft-strong);
  color: var(--color-ai-active);
  border-color: var(--color-ai-active);
  box-shadow: 0 0 0 4px var(--color-accent-soft);
}
.stepper-connector {
  position: absolute;
  left: 9px;
  top: 20px;
  width: 2px;
  height: calc(100% - 4px);
  background: var(--color-surface-l2);
}
.stepper-item.done > .stepper-connector {
  background: var(--color-ai-active);
  opacity: 0.4;
}
.stepper-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  padding-top: 2px;
  line-height: 1.4;
}
.stepper-item.active .stepper-label {
  color: var(--color-text-primary);
  font-weight: 600;
}
.stepper-item.done .stepper-label {
  color: var(--color-text-secondary);
}
</style>
