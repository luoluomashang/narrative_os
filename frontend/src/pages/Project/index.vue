<template>
  <div class="project-page app-page-surface">
    <SystemPageHeader
      eyebrow="Project State Machine"
      :title="projectInfo?.project_name || projectId"
      :description="projectDescription"
    >
      <template #meta>
        <span class="project-page__pill">项目 {{ projectId }}</span>
        <span class="project-page__pill">世界 {{ projectInfo?.world_published ? '已发布' : '未发布' }}</span>
        <span class="project-page__pill project-page__pill--alert">待提交变更 {{ projectInfo?.pending_changes_count ?? 0 }}</span>
      </template>
      <template #actions>
        <SystemButton variant="primary" @click="go(`/project/${projectId}/write`)">继续撰写</SystemButton>
        <SystemButton variant="ghost" @click="go(`/project/${projectId}/worldbuilder`)">世界构建</SystemButton>
      </template>
    </SystemPageHeader>

    <SystemSection title="流程阶段" description="按阶段查看当前项目状态机，并直接跳转到下一步工作台。">
      <div class="workflow-strip">
        <SystemCard
          v-for="node in workflowNodes"
          :key="node.step_id"
          tag="button"
          interactive
          class="workflow-node"
          :class="`status-${node.status}`"
          @click="go(node.href)"
        >
          <span class="dot"></span>
          <strong>{{ node.label }}</strong>
          <small>{{ node.statistic }}</small>
        </SystemCard>
      </div>

      <section class="stats-grid">
        <SystemCard class="stat-card" tone="subtle">
          <span>角色总数</span>
          <strong>{{ projectInfo?.character_count ?? 0 }}</strong>
          <p>其中具备 Drive 层 {{ projectInfo?.characters_with_drive ?? 0 }} 个。</p>
        </SystemCard>
        <SystemCard class="stat-card" tone="subtle">
          <span>当前卷目标</span>
          <strong>{{ projectInfo?.current_volume_goal || '未设置' }}</strong>
          <p>Plot 节点状态会在章节完成后由 Maintenance 回写推进。</p>
        </SystemCard>
        <SystemCard class="stat-card" tone="subtle">
          <span>总字数</span>
          <strong>{{ projectInfo?.total_word_count ?? 0 }}</strong>
          <p>当前版本快照 {{ projectInfo?.versions?.length ?? 0 }} 个。</p>
        </SystemCard>
      </section>
    </SystemSection>

    <SystemSection title="建议动作" description="只保留一个主行动入口，其余入口降为辅助跳转。">
      <div class="action-focus-grid">
        <SystemCard class="action-focus-card" :title="recommendedAction.title" :description="recommendedAction.description">
          <div class="action-focus-actions">
            <SystemButton variant="primary" @click="go(recommendedAction.href)">{{ recommendedAction.cta }}</SystemButton>
            <SystemButton variant="ghost" @click="go(`/project/${projectId}/trace`)">查看执行链路</SystemButton>
          </div>
        </SystemCard>

        <SystemCard class="action-links-card" title="辅助入口" tone="subtle">
          <div class="action-links">
            <SystemButton size="sm" variant="ghost" @click="go(`/project/${projectId}/benchmark`)">Benchmark</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="go(`/project/${projectId}/worldbuilder`)">世界构建</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="go(`/project/${projectId}/characters`)">角色矩阵</SystemButton>
          </div>
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection title="最近活动" description="把最近章节、会话与异常收敛成二级浏览区，不和主流程阻塞抢首屏。">
      <div class="overview-grid">
        <SystemCard
          v-for="card in recentActivityCards"
          :key="card.key"
          class="overview-card"
          :title="card.title"
          :description="card.description"
          tone="subtle"
        >
          <strong class="overview-highlight">{{ card.value }}</strong>
          <p class="overview-copy">{{ card.detail }}</p>
          <template v-if="card.href" #actions>
            <SystemButton size="sm" variant="ghost" @click="go(card.href)">{{ card.cta }}</SystemButton>
          </template>
        </SystemCard>
      </div>
    </SystemSection>

    <SystemSection title="二级摘要" description="资产概览和质量摘要下沉为二级信息区，避免首页重新变成信息墙。">
      <div class="overview-grid">
        <SystemCard
          v-for="card in secondarySummaryCards"
          :key="card.key"
          class="overview-card"
          :title="card.title"
          :description="card.description"
          tone="subtle"
        >
          <strong class="overview-highlight">{{ card.value }}</strong>
          <p class="overview-copy">{{ card.detail }}</p>
          <template v-if="card.href" #actions>
            <SystemButton size="sm" variant="ghost" @click="go(card.href)">{{ card.cta }}</SystemButton>
          </template>
        </SystemCard>
      </div>
    </SystemSection>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
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

type OverviewCard = {
  key: string
  title: string
  description: string
  value: string | number
  detail: string
  href?: string
  cta?: string
}

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

const projectId = computed(() => route.params.id as string)
const projectInfo = computed(() => (store.projectInfo ?? null) as ProjectStatusPayload | null)
const workflowNodes = computed<WorkflowNode[]>(() => projectInfo.value?.workflow_nodes ?? [])
const projectDescription = computed(() => (
  `第 ${projectInfo.value?.current_chapter ?? 0} 章 · 卷 ${projectInfo.value?.current_volume ?? 1}，持续跟踪角色、世界与执行链路状态。`
))
const workflowProgress = computed(() => {
  const total = workflowNodes.value.length
  const completed = workflowNodes.value.filter((node) => node.status === 'completed').length
  return total ? `${completed}/${total}` : '0/0'
})
const driveCoverage = computed(() => {
  const total = projectInfo.value?.character_count ?? 0
  if (total === 0) return '0%'
  return `${Math.round(((projectInfo.value?.characters_with_drive ?? 0) / total) * 100)}%`
})
const recommendedAction = computed(() => {
  if (!projectInfo.value?.world_published) {
    return {
      title: '优先发布世界设定',
      description: '当前世界状态仍未发布，写作与链路校验会持续受到阻塞。',
      cta: '前往世界构建',
      href: `/project/${projectId.value}/worldbuilder`,
    }
  }

  if ((projectInfo.value?.pending_changes_count ?? 0) > 0) {
    return {
      title: '先处理待提交变更',
      description: '当前存在待确认变更，建议先审查执行链路和回写结果，再继续推进正文。',
      cta: '处理执行链路',
      href: `/project/${projectId.value}/trace`,
    }
  }

  return {
    title: '继续当前章节创作',
    description: '项目主链路已具备条件，可直接进入 Writing Workbench 继续章节生成。',
    cta: '进入 Writing',
    href: `/project/${projectId.value}/write`,
  }
})
const recentActivityCards = computed<OverviewCard[]>(() => [
  {
    key: 'chapter',
    title: '最近章节',
    description: '当前创作进度和最近主任务。',
    value: `第 ${projectInfo.value?.current_chapter ?? 0} 章`,
    detail: recommendedAction.value.description,
    href: `/project/${projectId.value}/write`,
    cta: '继续创作',
  },
  {
    key: 'changes',
    title: '最近异常',
    description: '待确认变更与执行链路提示。',
    value: `${projectInfo.value?.pending_changes_count ?? 0} 项`,
    detail: (projectInfo.value?.pending_changes_count ?? 0) > 0
      ? '当前存在待提交变更，建议优先回到执行链路核对。'
      : '当前没有待处理异常，主流程可继续推进。',
    href: `/project/${projectId.value}/trace`,
    cta: '查看链路',
  },
  {
    key: 'world',
    title: '最近会话',
    description: '世界状态与互动入口。',
    value: projectInfo.value?.world_published ? '世界已发布' : '世界待发布',
    detail: projectInfo.value?.world_published
      ? '可继续进入 TRPG 或 Writing，不再受世界发布阻塞。'
      : '当前仍建议先完成世界设定发布，再继续互动和生成。',
    href: projectInfo.value?.world_published
      ? `/project/${projectId.value}/trpg`
      : `/project/${projectId.value}/worldbuilder`,
    cta: projectInfo.value?.world_published ? '打开 TRPG' : '前往发布',
  },
])
const secondarySummaryCards = computed<OverviewCard[]>(() => [
  {
    key: 'workflow',
    title: '流程完成度',
    description: '当前主链路推进情况。',
    value: workflowProgress.value,
    detail: '流程完成度只作为二级摘要展示，不与阻塞区并列放大。',
  },
  {
    key: 'characters',
    title: '角色覆盖',
    description: 'Drive 层完善情况。',
    value: driveCoverage.value,
    detail: `${projectInfo.value?.characters_with_drive ?? 0} / ${projectInfo.value?.character_count ?? 0} 个角色已具备 Drive 层。`,
    href: `/project/${projectId.value}/characters`,
    cta: '查看角色',
  },
  {
    key: 'volume-goal',
    title: '当前卷目标',
    description: '卷级叙事目标。',
    value: projectInfo.value?.current_volume_goal || '未设置',
    detail: '卷目标下沉为二级摘要，避免首页首屏同时出现过多并列主入口。',
    href: `/project/${projectId.value}/plot`,
    cta: '查看剧情',
  },
])

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
  display: grid;
  gap: var(--spacing-5);
  min-height: 100%;
  align-content: start;
}

.project-page__pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.project-page__pill--alert {
  background: var(--color-danger-soft);
  color: var(--color-danger);
}

.workflow-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
}

.workflow-node {
  width: min(180px, 100%);
  text-align: left;
  display: grid;
  gap: 8px;
}

.workflow-node strong {
  color: var(--color-text-1);
}

.workflow-node small {
  color: var(--color-text-3);
  line-height: 1.5;
}

.dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-status-track);
}

.status-completed .dot {
  background: var(--color-success);
}

.status-in_progress .dot {
  background: var(--color-warning);
}

.status-pending .dot {
  background: var(--color-status-track);
}

.stats-grid,
.action-focus-grid {
  display: grid;
  gap: 16px;
}

.stats-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.stat-card,
.action-focus-card {
  width: 100%;
}

.action-focus-grid {
  grid-template-columns: minmax(0, 1.5fr) minmax(260px, 0.9fr);
}

.action-focus-actions,
.action-links {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.action-links-card :deep(.system-card__body) {
  gap: 12px;
}

.overview-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.overview-card :deep(.system-card__body) {
  gap: 12px;
}

.overview-highlight {
  display: block;
  color: var(--color-text-1);
  font-size: 1.1rem;
  line-height: 1.45;
}

.overview-copy {
  margin: 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.stat-card span {
  display: block;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  color: var(--color-text-3);
}

.stat-card strong,
.action-card strong {
  display: block;
  margin-top: 10px;
  font-size: 22px;
  color: var(--color-text-1);
}

.stat-card p,
.action-card p {
  margin: 10px 0 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.action-grid {
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.action-card {
  text-align: left;
}

.accent-write {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-accent-soft) 80%, transparent), color-mix(in srgb, var(--color-surface-1) 96%, transparent));
}

.accent-world {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-success-soft) 82%, transparent), color-mix(in srgb, var(--color-surface-1) 96%, transparent));
}

.accent-benchmark {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-warning-soft) 86%, transparent), color-mix(in srgb, var(--color-surface-1) 96%, transparent));
}

.accent-character {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-info-soft) 84%, transparent), color-mix(in srgb, var(--color-surface-1) 96%, transparent));
}

.accent-trace {
  background: linear-gradient(180deg, color-mix(in srgb, var(--color-surface-3) 90%, transparent), color-mix(in srgb, var(--color-surface-1) 96%, transparent));
}

@media (max-width: 1080px) {
  .overview-grid,
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

  .overview-grid,
  .action-grid {
    grid-template-columns: 1fr;
  }

  .workflow-node {
    width: 100%;
  }
}
</style>