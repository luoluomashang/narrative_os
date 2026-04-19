<template>
  <el-drawer
    class="system-drawer"
    :model-value="modelValue"
    :size="size"
    :direction="direction"
    :destroy-on-close="destroyOnClose"
    v-bind="$attrs"
    @update:model-value="emit('update:modelValue', $event)"
    @close="handleClose"
  >
    <template #header>
      <div class="system-drawer__header">
        <div>
          <h2 class="system-drawer__title">{{ title }}</h2>
          <p v-if="description" class="system-drawer__description">{{ description }}</p>
        </div>
      </div>
    </template>

    <div class="system-drawer__body">
      <slot />
    </div>

    <template v-if="$slots.footer" #footer>
      <div class="system-drawer__footer">
        <slot name="footer" />
      </div>
    </template>
  </el-drawer>
</template>

<script setup lang="ts">
defineOptions({ inheritAttrs: false })

withDefaults(
  defineProps<{
    modelValue: boolean
    title: string
    description?: string
    size?: string | number
    direction?: 'rtl' | 'ltr' | 'ttb' | 'btt'
    destroyOnClose?: boolean
  }>(),
  {
    description: '',
    size: '420px',
    direction: 'rtl',
    destroyOnClose: false,
  },
)

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'close'): void
}>()

function handleClose() {
  emit('update:modelValue', false)
  emit('close')
}
</script>

<style scoped>
.system-drawer__title {
  margin: 0;
  font-size: 1.1rem;
  color: var(--color-text-1);
}

.system-drawer__description {
  margin: 8px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.system-drawer__footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--spacing-2);
}

:deep(.system-drawer .el-drawer) {
  background: var(--color-surface-1);
}

:deep(.system-drawer .el-drawer__header) {
  margin-bottom: 0;
  padding: var(--spacing-6) var(--spacing-6) var(--spacing-4);
  border-bottom: 1px solid var(--color-border-subtle);
}

:deep(.system-drawer .el-drawer__body) {
  padding: var(--spacing-5) var(--spacing-6);
}

:deep(.system-drawer .el-drawer__footer) {
  padding: var(--spacing-4) var(--spacing-6) var(--spacing-6);
  border-top: 1px solid var(--color-border-subtle);
}
</style>
