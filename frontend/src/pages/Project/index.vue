<template>
  <div class="project-page">
    <section class="project-hero shell">
      <div>
        <p class="eyebrow">Project State Machine</p>
        <h1>{{ projectInfo?.project_name || projectId }}</h1>
        <p class="subtitle">
          第 {{ projectInfo?.current_chapter ?? 0 }} 章 · 卷 {{ projectInfo?.current_volume ?? 1 }}
        </p>
      </div>
      <div class="hero-badges">
        <span class="badge">世界 {{ projectInfo?.world_published ? '已发布' : '未发布' }}</span>
        <span class="badge badge-alert">待提交变更 {{ projectInfo?.pending_changes_count ?? 0 }}</span>
      </div>
    </section>

    <section class="workflow-strip shell">
      <button
        v-for="node in workflowNodes"
        :key="node.step_id"
        class="workflow-node"
        :class="`status-${node.status}`"
        @click="go(node.href)"
      >
        <span class="dot"></span>
        <strong>{{ node.label }}</strong>
        <small>{{ node.statistic }}</small>
      </button>
    </section>

    <section class="stats-grid">
      <article class="stat-card shell">
        <span>角色总数</span>
        <strong>{{ projectInfo?.character_count ?? 0 }}</strong>
        <p>其中具备 Drive 层 {{ projectInfo?.characters_with_drive ?? 0 }} 个。</p>
      </article>
      <article class="stat-card shell">
        <span>当前卷目标</span>
        <strong>{{ projectInfo?.current_volume_goal || '未设置' }}</strong>
        <p>Plot 节点状态会在章节完成后由 Maintenance 回写推进。</p>
      </article>
      <article class="stat-card shell">
        <span>总字数</span>
        <strong>{{ projectInfo?.total_word_count ?? 0 }}</strong>
        <p>当前版本快照 {{ projectInfo?.versions?.length ?? 0 }} 个。</p>
      </article>
    </section>

    <section class="action-grid">
      <button class="action-card shell accent-write" @click="go(`/project/${projectId}/write`)">
        <strong>继续撰写</strong>
        <p>进入 Writing Workbench，查看运行链路和前置检查。</p>
      </button>
      <button class="action-card shell accent-benchmark" @click="go(`/project/${projectId}/benchmark`)">
        <strong>Benchmark Studio</strong>
        <p>上传参考文本、生成对标 profile，并激活当前项目基准。</p>
      </button>
      <button class="action-card shell accent-world" @click="go(`/project/${projectId}/worldbuilder`)">
        <strong>世界构建</strong>
        <p>发布 RuntimeWorldState，解除写作前的硬阻塞。</p>
      </button>
      <button class="action-card shell accent-character" @click="go(`/project/${projectId}/characters`)">
        <strong>角色矩阵</strong>
        <p>补齐 Persona / Drive / Social / Runtime 四层状态。</p>
      </button>
      <button class="action-card shell accent-trace" @click="go(`/project/${projectId}/trace`)">
        <strong>执行链路</strong>
        <p>审查 Run / Step / Artifact，处理 pending 变更。</p>
      </button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useProjectStore } from '@/stores/projectStore'

type WorkflowNode = {
  step_id: string
  label: string
  status: string
  href: string
  statistic: string
}

type ProjectStatusPayload = {
  project_name?: string
  current_chapter?: number
  current_volume?: number
  total_word_count?: number
  versions?: number[]
  world_published?: boolean
  character_count?: number
  characters_with_drive?: number
  pending_changes_count?: number
  current_volume_goal?: string
  workflow_nodes?: WorkflowNode[]
}

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const projectId = computed(() => route.params.id as string)
const projectInfo = computed(() => (store.projectInfo ?? null) as ProjectStatusPayload | null)
const workflowNodes = computed<WorkflowNode[]>(() => projectInfo.value?.workflow_nodes ?? [])

function go(path: string) {
  if (!path) return
  router.push(path)
}

onMounted(async () => {
  try {
    await store.loadProjectInfo(projectId.value)
  } catch {
    router.replace('/projects')
  }
})
</script>

<style scoped>
.project-page {
  padding: 24px;
  min-height: 100%;
  background:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.14), transparent 26%),
    linear-gradient(180deg, rgba(15, 23, 42, 0.02), rgba(15, 23, 42, 0.05));
}

.shell {
  border-radius: 24px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.08);
}

.project-hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  padding: 28px;
  margin-bottom: 18px;
}

.eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #b45309;
}

.project-hero h1 {
  margin: 0;
  font-size: 30px;
  color: #0f172a;
}

.subtitle {
  margin: 10px 0 0;
  color: #475569;
}

.hero-badges {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.badge {
  padding: 10px 14px;
  border-radius: 999px;
  background: #f8fafc;
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.badge-alert {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.workflow-strip {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  gap: 12px;
  padding: 18px;
  margin-bottom: 18px;
}

.workflow-node {
  border: none;
  border-radius: 20px;
  background: #f8fafc;
  padding: 16px 14px;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 8px;
}

.workflow-node strong {
  color: #0f172a;
}

.workflow-node small {
  color: #64748b;
  line-height: 1.5;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #cbd5e1;
}

.status-completed .dot {
  background: #10b981;
}

.status-in_progress .dot {
  background: #f59e0b;
}

.status-pending .dot {
  background: #cbd5e1;
}

.stats-grid,
.action-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-bottom: 18px;
}

.stat-card,
.action-card {
  padding: 22px;
}

.stat-card span {
  display: block;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: #64748b;
}

.stat-card strong,
.action-card strong {
  display: block;
  margin-top: 10px;
  font-size: 22px;
  color: #0f172a;
}

.stat-card p,
.action-card p {
  margin: 10px 0 0;
  color: #475569;
  line-height: 1.6;
}

.action-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.action-card {
  border: none;
  text-align: left;
  cursor: pointer;
}

.accent-write {
  background: linear-gradient(180deg, rgba(249, 115, 22, 0.12), rgba(255, 255, 255, 0.96));
}

.accent-world {
  background: linear-gradient(180deg, rgba(16, 185, 129, 0.12), rgba(255, 255, 255, 0.96));
}

.accent-benchmark {
  background: linear-gradient(180deg, rgba(217, 119, 6, 0.14), rgba(255, 251, 235, 0.98));
}

.accent-character {
  background: linear-gradient(180deg, rgba(59, 130, 246, 0.12), rgba(255, 255, 255, 0.96));
}

.accent-trace {
  background: linear-gradient(180deg, rgba(15, 23, 42, 0.08), rgba(255, 255, 255, 0.96));
}

@media (max-width: 1080px) {
  .workflow-strip,
  .action-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .stats-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .project-page {
    padding: 16px;
  }

  .project-hero,
  .workflow-strip,
  .action-grid {
    grid-template-columns: 1fr;
    display: grid;
  }

  .hero-badges {
    justify-content: flex-start;
  }
}
</style>