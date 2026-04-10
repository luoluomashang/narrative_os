<template>
  <div class="consistency-panel">
    <div class="cp-header">
      <span>逻辑校验结果</span>
      <span class="cp-count">{{ issues.length }} 项</span>
    </div>
    <div v-if="issues.length === 0" class="cp-empty">
      ✅ 未发现一致性问题
    </div>
    <div v-else class="cp-list">
      <div
        v-for="issue in issues"
        :key="`${issue.nodeId}-${issue.message}`"
        class="cp-issue"
        :class="issue.severity"
      >
        <span class="cp-severity">{{ issue.severity === 'error' ? '❌' : '⚠️' }}</span>
        <span class="cp-message">{{ issue.message }}</span>
      </div>
    </div>

    <el-divider />
    <el-button type="warning" plain :loading="aiChecking" @click="runAiCheck">✦ AI 深度分析</el-button>
    <div v-if="aiIssues.length" class="cp-list" style="margin-top: 8px;">
      <div
        v-for="(issue, idx) in aiIssues"
        :key="idx"
        class="cp-issue"
        :class="issue.severity"
      >
        <span class="cp-severity">{{ issue.severity === 'error' ? '❌' : '⚠️' }}</span>
        <span class="cp-message"><strong>{{ issue.node_ref }}</strong>: {{ issue.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { WorldSandboxData } from '@/api/world'
import { world } from '@/api/world'

interface ConsistencyIssue {
  nodeId: string
  nodeType: 'region' | 'faction'
  severity: 'warning' | 'error'
  message: string
}

const props = defineProps<{
  worldData: WorldSandboxData
  projectId: string
}>()

function checkConsistency(data: WorldSandboxData): ConsistencyIssue[] {
  const issues: ConsistencyIssue[] = []

  // Rule 1: Faction power system mismatch with territory region
  data.factions.forEach(f => {
    if (!f.power_system_id) return
    const territories = data.regions.filter(r =>
      f.territory_region_ids?.includes(r.id)
    )
    territories.forEach(r => {
      if (
        r.power_access &&
        !r.power_access.inherits_global &&
        r.power_access.custom_system_id &&
        r.power_access.custom_system_id !== f.power_system_id
      ) {
        issues.push({
          nodeId: f.id,
          nodeType: 'faction',
          severity: 'warning',
          message: `势力「${f.name}」的力量体系与其所在地区「${r.name}」的自定义力量体系不匹配`,
        })
      }
    })
  })

  // Rule 2: Isolated region nodes (no relations)
  const connectedIds = new Set(
    data.relations.flatMap(r => [r.source_id, r.target_id])
  )
  data.regions.forEach(r => {
    if (!connectedIds.has(r.id)) {
      issues.push({
        nodeId: r.id,
        nodeType: 'region',
        severity: 'warning',
        message: `地区「${r.name}」没有任何关系连线，是否孤立节点？`,
      })
    }
  })

  // Rule 3: Isolated faction nodes
  data.factions.forEach(f => {
    if (!connectedIds.has(f.id)) {
      issues.push({
        nodeId: f.id,
        nodeType: 'faction',
        severity: 'warning',
        message: `势力「${f.name}」没有任何关系连线，是否孤立节点？`,
      })
    }
  })

  // Rule 4: Region references non-existent faction
  const factionIds = new Set(data.factions.map(f => f.id))
  data.regions.forEach(r => {
    if (r.faction_ids) {
      r.faction_ids.forEach(fid => {
        if (!factionIds.has(fid)) {
          issues.push({
            nodeId: r.id,
            nodeType: 'region',
            severity: 'error',
            message: `地区「${r.name}」引用了不存在的势力 ID: ${fid}`,
          })
        }
      })
    }
  })

  // Rule 5: Relation endpoints must reference existing region or faction
  const regionIds = new Set(data.regions.map(r => r.id))
  const validIds = new Set([...regionIds, ...factionIds])
  const nodeName = (id: string) => {
    const r = data.regions.find(r => r.id === id)
    if (r) return `地区「${r.name}」`
    const f = data.factions.find(f => f.id === id)
    if (f) return `势力「${f.name}」`
    return `节点(${id.slice(0, 8)}…)`
  }
  data.relations.forEach(rel => {
    if (!validIds.has(rel.source_id)) {
      issues.push({
        nodeId: rel.id,
        nodeType: 'region',
        severity: 'error',
        message: `关系「${rel.label || rel.id.slice(0, 8)}」的源节点 ID(${rel.source_id.slice(0, 8)}…) 未在已定义的地区或势力列表中出现`,
      })
    }
    if (!validIds.has(rel.target_id)) {
      issues.push({
        nodeId: rel.id,
        nodeType: 'region',
        severity: 'error',
        message: `关系「${rel.label || rel.id.slice(0, 8)}」的目标节点 ${nodeName(rel.target_id)} 未在已定义的地区或势力列表中出现`,
      })
    }
  })

  return issues
}

const issues = computed(() => checkConsistency(props.worldData))

const aiChecking = ref(false)
const aiIssues = ref<Array<{ severity: string; node_ref: string; message: string }>>([])

async function runAiCheck() {
  aiChecking.value = true
  aiIssues.value = []
  try {
    const res = await world.aiConsistencyCheck(props.projectId)
    aiIssues.value = res.data.issues || []
  } catch {
    aiIssues.value = []
  } finally {
    aiChecking.value = false
  }
}
</script>

<style scoped>
.consistency-panel {
  padding: 12px;
}

.cp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 14px;
  font-weight: 600;
  color: var(--wb-neon-cyan, #2ef2ff);
}

.cp-count {
  font-size: 12px;
  font-weight: 400;
  color: #888;
}

.cp-empty {
  text-align: center;
  color: #2eff8a;
  font-size: 13px;
  padding: 24px;
}

.cp-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.cp-issue {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #ccc;
}

.cp-issue.warning {
  background: rgba(255, 196, 46, 0.1);
  border: 1px solid rgba(255, 196, 46, 0.25);
}

.cp-issue.error {
  background: rgba(255, 64, 64, 0.1);
  border: 1px solid rgba(255, 64, 64, 0.25);
}

.cp-severity {
  flex-shrink: 0;
}

.cp-message {
  line-height: 1.5;
}
</style>
