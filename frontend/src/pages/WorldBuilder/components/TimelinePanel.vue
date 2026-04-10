<template>
  <div class="timeline-container" :class="{ open: timelineOpen }">
    <div class="timeline-toggle" @click="timelineOpen = !timelineOpen">
      <span>{{ timelineOpen ? '▼' : '▲' }} 年表</span>
    </div>
    <div v-if="timelineOpen" class="timeline-content">
      <div class="timeline-toolbar">
        <button class="tl-btn add" @click="showAddDialog = true">+ 添加事件</button>
      </div>
      <div class="timeline-scroll">
        <div class="timeline-axis"></div>
        <div
          v-for="event in sortedEvents"
          :key="event.id"
          class="timeline-event"
          :class="event.event_type"
          :style="{ left: `${getEventOffset(event.year)}px` }"
        >
          <div class="event-year">{{ event.year }}</div>
          <div class="event-card">
            <div class="event-title">{{ event.title }}</div>
            <div v-if="event.description" class="event-desc">{{ event.description }}</div>
            <button class="event-delete" @click="removeEvent(event.id)">×</button>
          </div>
        </div>
        <div v-if="sortedEvents.length === 0" class="timeline-empty">
          暂无事件，点击"+ 添加事件"开始编年
        </div>
      </div>
    </div>

    <!-- Add event dialog — teleport to body to avoid stacking context issues -->
    <Teleport to="body">
    <div v-if="showAddDialog" class="tl-dialog-overlay" @click.self="showAddDialog = false">
      <div class="tl-dialog">
        <div class="tl-dialog-title">添加年表事件</div>
        <div class="tl-dialog-body">
          <label>
            年份
            <input v-model.number="newEvent.year" type="number" placeholder="如：1000" />
          </label>
          <label>
            标题
            <input v-model="newEvent.title" type="text" placeholder="事件名称" />
          </label>
          <label>
            描述
            <textarea v-model="newEvent.description" rows="2" placeholder="简要描述"></textarea>
          </label>
          <label>
            类型
            <select v-model="newEvent.event_type">
              <option value="historical">历史</option>
              <option value="conflict">冲突</option>
              <option value="growth">发展</option>
              <option value="general">通用</option>
              <option value="custom">自定义</option>
            </select>
          </label>
        </div>
        <div class="tl-dialog-actions">
          <button class="tl-btn" @click="showAddDialog = false">取消</button>
          <button class="tl-btn confirm" @click="addEvent">确认</button>
        </div>
      </div>
    </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { world } from '@/api/world'
import type { TimelineSandboxEvent } from '@/api/world'
import { ElMessage } from 'element-plus'

interface TimelineEvent {
  id: string
  year: number
  title: string
  description: string
  linkedEntityId?: string
  event_type: string
}

const props = defineProps<{
  projectId: string
}>()

const timelineOpen = ref(false)
const showAddDialog = ref(false)
const events = ref<TimelineEvent[]>([])
const loading = ref(false)

const newEvent = ref({
  year: 1,
  title: '',
  description: '',
  event_type: 'historical',
})

function toLocalEvent(e: TimelineSandboxEvent): TimelineEvent {
  return {
    id: e.id,
    year: parseInt(e.year) || 0,
    title: e.title,
    description: e.description || '',
    linkedEntityId: e.linked_entity_id || undefined,
    event_type: e.event_type || 'historical',
  }
}

async function loadEvents() {
  if (!props.projectId) return
  loading.value = true
  try {
    const res = await world.listTimeline(props.projectId)
    events.value = res.data.map(toLocalEvent)
  } catch {
    // Fallback: try localStorage for migration
    const saved = localStorage.getItem(`wb-timeline-${props.projectId}`)
    if (saved) {
      try { events.value = JSON.parse(saved) } catch { /* ignore */ }
    }
  } finally {
    loading.value = false
  }
}

onMounted(loadEvents)

watch(() => props.projectId, loadEvents)

const sortedEvents = computed(() =>
  [...events.value].sort((a, b) => a.year - b.year)
)

function getEventOffset(year: number): number {
  if (sortedEvents.value.length <= 1) return 40
  const minYear = sortedEvents.value[0].year
  const maxYear = sortedEvents.value[sortedEvents.value.length - 1].year
  const range = maxYear - minYear || 1
  return 40 + ((year - minYear) / range) * 600
}

async function addEvent() {
  if (!newEvent.value.title.trim() || !props.projectId) return
  try {
    const res = await world.createTimelineEvent(props.projectId, {
      year: String(newEvent.value.year),
      title: newEvent.value.title.trim(),
      description: newEvent.value.description.trim(),
      event_type: newEvent.value.event_type,
    })
    events.value.push(toLocalEvent(res.data))
    newEvent.value = { year: 1, title: '', description: '', event_type: 'historical' }
    showAddDialog.value = false
  } catch {
    ElMessage.error('添加事件失败，请稍后重试')
  }
}

async function removeEvent(id: string) {
  if (!props.projectId) return
  try {
    await world.deleteTimelineEvent(props.projectId, id)
    events.value = events.value.filter(e => e.id !== id)
  } catch {
    ElMessage.error('删除事件失败，请稍后重试')
  }
}
</script>

<style scoped>
.timeline-container {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  z-index: 10;
  transition: height 0.3s ease;
  pointer-events: none; /* 容器本身不拦截鼠标事件，防止遮挡画布下层交互 */
}

.timeline-container:not(.open) {
  height: 32px;
}

.timeline-container.open {
  height: 180px;
}

.timeline-toggle {
  display: flex;
  justify-content: center;
  padding: 6px 0;
  cursor: pointer;
  background: rgba(0, 0, 0, 0.7);
  border-top: 1px solid var(--wb-glass-border, rgba(255,255,255,0.08));
  color: var(--wb-neon-cyan, #2ef2ff);
  font-size: 12px;
  backdrop-filter: blur(8px);
  pointer-events: auto;
  user-select: none;
}

.timeline-toggle:hover {
  background: rgba(0, 0, 0, 0.85);
}

.timeline-content {
  height: 148px;
  background: rgba(8, 8, 16, 0.9);
  backdrop-filter: blur(10px);
  padding: 8px 16px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  pointer-events: auto;
}

.timeline-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 4px;
}

.timeline-scroll {
  position: relative;
  flex: 1;
  overflow-x: auto;
  overflow-y: hidden;
  min-width: 100%;
}

.timeline-axis {
  position: absolute;
  top: 50%;
  left: 0;
  right: 0;
  height: 2px;
  background: rgba(46, 242, 255, 0.2);
  min-width: 720px;
}

.timeline-event {
  position: absolute;
  bottom: 50%;
  margin-bottom: 4px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.event-year {
  font-size: 10px;
  color: #888;
  margin-bottom: 2px;
}

.event-card {
  padding: 4px 8px;
  border-radius: 6px;
  font-size: 11px;
  white-space: nowrap;
  position: relative;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-event.historical .event-card {
  background: rgba(77, 124, 255, 0.2);
  border: 1px solid rgba(77, 124, 255, 0.4);
  color: #8ab4ff;
}

.timeline-event.conflict .event-card {
  background: rgba(255, 64, 64, 0.2);
  border: 1px solid rgba(255, 64, 64, 0.4);
  color: #ff8080;
}

.timeline-event.growth .event-card {
  background: rgba(46, 255, 138, 0.2);
  border: 1px solid rgba(46, 255, 138, 0.4);
  color: #80ffb0;
}

.timeline-event.custom .event-card {
  background: rgba(180, 80, 255, 0.2);
  border: 1px solid rgba(180, 80, 255, 0.4);
  color: #c090ff;
}

.event-title {
  font-weight: 600;
}

.event-desc {
  font-size: 10px;
  color: #777;
  margin-top: 2px;
}

.event-delete {
  position: absolute;
  top: -4px;
  right: -4px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: none;
  background: rgba(255, 64, 64, 0.5);
  color: white;
  cursor: pointer;
  font-size: 10px;
  line-height: 14px;
  padding: 0;
  opacity: 0.5;
  transition: opacity 0.15s;
}

.event-card:hover .event-delete {
  opacity: 1;
}

.timeline-empty {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  color: #555;
  font-size: 12px;
}

.tl-btn {
  padding: 4px 10px;
  border: 1px solid var(--wb-glass-border, rgba(255,255,255,0.08));
  border-radius: 5px;
  background: rgba(0, 0, 0, 0.4);
  color: #aaa;
  cursor: pointer;
  font-size: 11px;
  transition: all 0.2s;
}

.tl-btn:hover {
  color: var(--wb-neon-cyan, #2ef2ff);
  border-color: var(--wb-neon-cyan, #2ef2ff);
}

.tl-btn.add {
  color: var(--wb-neon-cyan, #2ef2ff);
}

.tl-btn.confirm {
  background: rgba(46, 242, 255, 0.15);
  color: var(--wb-neon-cyan, #2ef2ff);
  border-color: var(--wb-neon-cyan, #2ef2ff);
}

/* Dialog */
.tl-dialog-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
}

.tl-dialog {
  background: #1a1a2e;
  border: 1px solid var(--wb-glass-border, rgba(255,255,255,0.08));
  border-radius: 12px;
  padding: 20px;
  min-width: 320px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.4);
}

.tl-dialog-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--wb-neon-cyan, #2ef2ff);
  margin-bottom: 16px;
}

.tl-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tl-dialog-body label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #aaa;
}

.tl-dialog-body input,
.tl-dialog-body textarea,
.tl-dialog-body select {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 6px;
  padding: 6px 10px;
  color: #e0e0e0;
  font-size: 12px;
}

.tl-dialog-body input:focus,
.tl-dialog-body textarea:focus,
.tl-dialog-body select:focus {
  outline: none;
  border-color: var(--wb-neon-cyan, #2ef2ff);
}

.tl-dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 16px;
}
</style>
