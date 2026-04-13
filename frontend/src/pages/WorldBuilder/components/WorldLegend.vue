<template>
  <div class="world-legend">
    <div class="legend-header" @click="collapsed = !collapsed">
      <span class="legend-title">势力图例</span>
      <span class="legend-toggle">{{ collapsed ? '▸' : '▾' }}</span>
    </div>
    <transition name="legend-slide">
      <div v-if="!collapsed" class="legend-body">
        <div
          v-for="item in legendItems"
          :key="item.id"
          class="legend-item"
          :class="{ active: highlightFactionId === item.id, dimmed: highlightFactionId && highlightFactionId !== item.id }"
          @click="selectLegendItem(item.id)"
        >
          <span class="legend-swatch" :style="{ background: item.color }"></span>
          <span class="legend-name">{{ item.name }}</span>
          <span class="legend-count">{{ item.regionCount }}</span>
        </div>
        <div
          v-if="unaffiliatedCount > 0"
          class="legend-item"
          :class="{ active: highlightFactionId === '__none__', dimmed: highlightFactionId && highlightFactionId !== '__none__' }"
          @click="toggleHighlight('__none__')"
        >
          <span class="legend-swatch" :style="{ background: '#666' }"></span>
          <span class="legend-name">无归属</span>
          <span class="legend-count">{{ unaffiliatedCount }}</span>
        </div>
        <div v-if="highlightFactionId" class="legend-reset" @click="clearHighlight">
          清除筛选
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Faction, Region } from '@/api/world'

const props = defineProps<{
  factions: Faction[]
  regions: Region[]
}>()

const emit = defineEmits<{
  (e: 'highlight', factionId: string | null): void
  (e: 'select', factionId: string): void
}>()

const collapsed = ref(false)
const highlightFactionId = ref<string | null>(null)

const legendItems = computed(() =>
  props.factions.map((f) => ({
    id: f.id,
    name: f.name,
    color: f.color || '#4d7cff',
    // Count regions that list this faction in either direction
    regionCount: props.regions.filter(
      (r) => f.territory_region_ids.includes(r.id) || (r.faction_ids ?? []).includes(f.id)
    ).length,
  }))
)

const affiliatedRegionIds = computed(() => {
  const ids = new Set<string>()
  props.factions.forEach((f) => {
    f.territory_region_ids.forEach((rid) => ids.add(rid))
    props.regions.forEach((r) => {
      if ((r.faction_ids ?? []).includes(f.id)) ids.add(r.id)
    })
  })
  return ids
})

const unaffiliatedCount = computed(
  () => props.regions.filter((r) => !affiliatedRegionIds.value.has(r.id)).length
)

function toggleHighlight(id: string) {
  highlightFactionId.value = highlightFactionId.value === id ? null : id
  emit('highlight', highlightFactionId.value)
}

function selectLegendItem(id: string) {
  toggleHighlight(id)
  emit('select', id)
}

function clearHighlight() {
  highlightFactionId.value = null
  emit('highlight', null)
}
</script>

<style scoped>
.world-legend {
  position: absolute;
  bottom: 12px;
  left: 12px;
  z-index: 10;
  min-width: 140px;
  max-width: 220px;
  background: rgba(0, 0, 0, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 8px;
  backdrop-filter: blur(8px);
  font-size: 12px;
  color: #ccc;
  user-select: none;
}

.legend-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  cursor: pointer;
}

.legend-title {
  font-weight: 600;
  letter-spacing: 0.5px;
}

.legend-toggle {
  font-size: 10px;
  opacity: 0.5;
}

.legend-body {
  padding: 0 10px 8px;
  max-height: calc(40vh - 40px);
  overflow-y: auto;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s, opacity 0.2s;
}

.legend-item:hover {
  background: rgba(255, 255, 255, 0.06);
}

.legend-item.active {
  background: rgba(46, 242, 255, 0.1);
}

.legend-item.dimmed {
  opacity: 0.35;
}

.legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.legend-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.legend-count {
  font-size: 10px;
  color: #888;
  min-width: 14px;
  text-align: right;
}

.legend-reset {
  margin-top: 4px;
  padding: 3px 6px;
  text-align: center;
  font-size: 11px;
  color: #2ef2ff;
  cursor: pointer;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.legend-reset:hover {
  text-decoration: underline;
}

.legend-slide-enter-active,
.legend-slide-leave-active {
  transition: max-height 0.25s ease, opacity 0.2s ease;
  overflow: hidden;
}

.legend-slide-enter-from,
.legend-slide-leave-to {
  max-height: 0;
  opacity: 0;
}

.legend-slide-enter-to,
.legend-slide-leave-from {
  max-height: 400px;
  opacity: 1;
}
</style>
