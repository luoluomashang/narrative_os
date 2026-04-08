<script setup lang="ts">
import TopBar from '@/components/layout/TopBar.vue'
import Sidebar from '@/components/layout/Sidebar.vue'
import MainContent from '@/components/layout/MainContent.vue'
</script>

<template>
  <div class="app-layout">
    <TopBar />
    <div class="app-body">
      <Sidebar />
      <MainContent />
    </div>
  </div>
</template>

<style scoped>
.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  background: var(--color-base, #0a0a0b);
  color: var(--color-text-primary, #f2efe9);
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}
</style>


