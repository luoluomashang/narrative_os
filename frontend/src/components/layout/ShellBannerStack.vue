<template>
  <div v-if="banners.length" class="shell-banner-stack">
    <SystemStatusBanner
      v-for="banner in banners"
      :key="banner.id"
      :status="toneToStatus[banner.tone]"
      :title="banner.title"
      :message="banner.message"
      compact
    >
      <template v-if="banner.action" #actions>
        <el-button text class="shell-banner__action" @click="handleAction(banner.action.to)">
          {{ banner.action.label }}
        </el-button>
      </template>
    </SystemStatusBanner>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import type { ShellBanner } from '@/composables/useShellBanners'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'

const props = defineProps<{
  banners: ShellBanner[]
}>()

const router = useRouter()

const toneToStatus = {
  info: 'success',
  warning: 'blocking',
  danger: 'offline',
} as const

function handleAction(target?: string) {
  if (!target) return
  router.push(target)
}
</script>

<style scoped>
.shell-banner-stack {
  display: grid;
  gap: var(--spacing-3);
  margin-bottom: var(--spacing-4);
}

.shell-banner__action {
  flex-shrink: 0;
}
</style>
