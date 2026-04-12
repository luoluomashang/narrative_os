<template>
  <div class="runtime-tab">
    <div class="read-only-hint">
      <span>⚡ Runtime 层由系统在互动推进时自动更新，此处仅展示当前状态。</span>
    </div>

    <div class="grid-2">
      <div class="stat-block">
        <div class="stat-label">当前位置</div>
        <div class="stat-value">{{ rt.current_location || '—' }}</div>
      </div>
      <div class="stat-block">
        <div class="stat-label">行动意图</div>
        <div class="stat-value">{{ rt.current_agenda || '—' }}</div>
      </div>
    </div>

    <div class="stat-block">
      <div class="stat-label">当前压力值 <span class="pct">{{ ((rt.current_pressure ?? 0) * 100).toFixed(0) }}%</span></div>
      <div class="pressure-bar">
        <div class="pressure-fill" :style="{ width: (rt.current_pressure ?? 0) * 100 + '%', background: pressureColor }" />
      </div>
    </div>

    <div class="grid-2">
      <div class="stat-block">
        <div class="stat-label">同行人物</div>
        <div class="stat-value">{{ rt.current_companions?.length ? rt.current_companions.join('、') : '独行' }}</div>
      </div>
      <div class="stat-block">
        <div class="stat-label">情绪来源</div>
        <div class="stat-value">{{ rt.emotion_trigger_source || '—' }}</div>
      </div>
    </div>

    <div class="stat-block">
      <div class="stat-label">近期关键事件</div>
      <ul class="event-list">
        <li v-for="(ev, i) in rt.recent_key_events" :key="i">{{ ev }}</li>
        <li v-if="!rt.recent_key_events?.length" class="empty">暂无记录</li>
      </ul>
    </div>

    <div class="grid-2">
      <div class="stat-block">
        <div class="stat-label">姿态模式</div>
        <div class="badge" :class="rt.stance_mode">{{ stanceLabel }}</div>
      </div>
      <div class="stat-block">
        <div class="stat-label">可主动推进剧情</div>
        <div class="badge" :class="rt.can_advance_plot ? 'yes' : 'no'">{{ rt.can_advance_plot ? '是' : '否' }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CharacterDetail, CharacterRuntime } from '@/types/api'

const props = defineProps<{ model: CharacterDetail }>()

const rt = computed<CharacterRuntime>(() => props.model.runtime ?? ({
  current_location: '',
  current_companions: [],
  current_agenda: '',
  current_pressure: 0,
  emotion_trigger_source: '',
  recent_key_events: [],
  can_advance_plot: true,
  stance_mode: 'normal',
} as CharacterRuntime))

const pressureColor = computed(() => {
  const p = rt.value.current_pressure ?? 0
  if (p >= 0.8) return '#ef4444'
  if (p >= 0.5) return '#f59e0b'
  return '#22c55e'
})

const stanceMap: Record<string, string> = {
  normal: '正常', danger: '危险', stubborn: '固执', defensive: '防御',
}
const stanceLabel = computed(() => stanceMap[rt.value.stance_mode ?? 'normal'] ?? rt.value.stance_mode)
</script>

<style scoped>
.runtime-tab { display: flex; flex-direction: column; gap: 14px; padding: 4px; }
.read-only-hint { background: var(--color-bg-secondary, #f8f8f8); border-radius: 6px; padding: 8px 12px; font-size: 12px; color: var(--color-text-secondary); }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.stat-block { display: flex; flex-direction: column; gap: 4px; }
.stat-label { font-size: 12px; color: var(--color-text-secondary); font-weight: 500; display: flex; align-items: center; gap: 6px; }
.pct { font-weight: 700; color: var(--color-text); }
.stat-value { font-size: 14px; }
.pressure-bar { height: 8px; border-radius: 4px; background: var(--color-border); overflow: hidden; }
.pressure-fill { height: 100%; border-radius: 4px; transition: width 0.3s; }
.event-list { margin: 0; padding-left: 16px; }
.event-list li { font-size: 13px; margin-bottom: 2px; }
.event-list .empty { color: var(--color-text-secondary); list-style: none; padding-left: 0; }
.badge { display: inline-block; border-radius: 4px; padding: 2px 10px; font-size: 12px; font-weight: 600; }
.badge.normal { background: #d1fae5; color: #065f46; }
.badge.danger { background: #fee2e2; color: #991b1b; }
.badge.stubborn { background: #fef3c7; color: #92400e; }
.badge.defensive { background: #dbeafe; color: #1e40af; }
.badge.yes { background: #d1fae5; color: #065f46; }
.badge.no { background: #fee2e2; color: #991b1b; }
</style>
