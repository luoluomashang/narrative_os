<template>
  <div class="project-home">
    <SystemPageHeader
      eyebrow="项目总览"
      :title="projectInfo?.project_name || projectId"
      :description="projectInfo ? `第 ${projectInfo.current_chapter} 章 · 卷 ${projectInfo.current_volume}` : '正在加载项目基础状态。'"
    >
      <template #meta>
        <span class="project-home__meta-pill">项目 {{ projectId }}</span>
      </template>
    </SystemPageHeader>

    <SystemSection title="当前建议动作" description="首页首屏只保留一个主任务入口，其他工作台降为辅助跳转。">
      <div class="project-home__focus">
        <SystemCard class="project-home__focus-card" title="继续当前阶段" description="根据项目状态自动推荐下一步，减少首页入口并列竞争。">
          <p class="project-home__focus-copy">{{ primaryAction.description }}</p>
          <div class="project-home__focus-actions">
            <SystemButton variant="primary" size="lg" @click="goTo(primaryAction.page)">{{ primaryAction.label }}</SystemButton>
            <SystemButton variant="ghost" @click="goTo('chapters')">查看章节</SystemButton>
          </div>
        </SystemCard>

        <SystemCard class="project-home__aux-card" title="辅助入口" tone="subtle">
          <div class="project-home__quick-links">
            <SystemButton size="sm" variant="ghost" @click="goTo('trpg')">TRPG 面板</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="goTo('worldbuilder')">世界构建</SystemButton>
            <SystemButton size="sm" variant="ghost" @click="goTo('benchmark')">Benchmark</SystemButton>
          </div>
        </SystemCard>
      </div>
    </SystemSection>

    <div class="project-home__grid">
      <SystemCard title="项目信息">
        <el-descriptions :column="2" v-if="projectInfo" border>
          <el-descriptions-item label="项目ID">{{ projectId }}</el-descriptions-item>
          <el-descriptions-item label="当前章节">{{ projectInfo.current_chapter }}</el-descriptions-item>
          <el-descriptions-item label="当前卷">{{ projectInfo.current_volume }}</el-descriptions-item>
          <el-descriptions-item label="版本快照">{{ projectInfo.versions?.length ?? 0 }}</el-descriptions-item>
        </el-descriptions>
        <SystemSkeleton v-else card :rows="3" />
      </SystemCard>

      <SystemCard title="工作流进度">
        <el-steps direction="vertical" :active="workflowStep" finish-status="success">
          <el-step title="世界构建" description="设定世界观、角色和情节节点" />
          <el-step title="情节规划" description="章节大纲与钩子设计" />
          <el-step title="章节生成" :description="`已生成 ${projectInfo?.current_chapter ?? 0} 章`" />
          <el-step title="审核与导出" description="质量检查与全本导出" />
        </el-steps>
      </SystemCard>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import { useProjectStore } from '@/stores/projectStore'
import type { ProjectStatusResponse } from '@/types/api'

const route = useRoute()
const router = useRouter()
const store = useProjectStore()

type ProjectHomeInfo = ProjectStatusResponse & {
  project_name?: string
}

const projectId = computed(() => route.params.id as string)
const projectInfo = computed<ProjectHomeInfo | null>(
  () => store.projectInfo as ProjectHomeInfo | null,
)

const workflowStep = computed(() => {
  const ch = projectInfo.value?.current_chapter ?? 0
  if (ch === 0) return 1
  if (ch < 3) return 2
  if (ch < 10) return 3
  return 4
})

const primaryAction = computed(() => {
  if (!projectInfo.value?.world_published) {
    return {
      page: 'worldbuilder',
      label: '先发布世界设定',
      description: '当前 RuntimeWorldState 仍未发布，优先完成世界设定发布，避免后续写作被硬阻塞。',
    }
  }

  if ((projectInfo.value?.current_chapter ?? 0) === 0) {
    return {
      page: 'benchmark',
      label: '准备首章基准',
      description: '先配置对标和作者风格基准，再进入首章生成，可以减少起步阶段的风格漂移。',
    }
  }

  return {
    page: 'write',
    label: `继续第 ${projectInfo.value?.current_chapter ?? 1} 章`,
    description: '项目已具备写作条件，直接进入主工作台继续当前章节生成与链路检查。',
  }
})

function goTo(page: string) {
  router.push(`/project/${projectId.value}/${page}`)
}

onMounted(() => {
  if (projectId.value) {
    store.loadProjectInfo(projectId.value)
  }
})
</script>

<style scoped>
.project-home {
  padding: 24px;
  max-width: 1200px;
  display: grid;
  gap: 20px;
}

.project-home__meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.project-home__focus {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(260px, 0.9fr);
  gap: 16px;
}

.project-home__focus-copy {
  margin: 0;
  color: var(--color-text-2);
  line-height: 1.7;
}

.project-home__focus-actions,
.project-home__quick-links {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}

.project-home__focus-actions {
  margin-top: 16px;
}

.project-home__aux-card :deep(.system-card__body) {
  gap: 12px;
}

.project-home__actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.project-home__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

@media (max-width: 960px) {
  .project-home {
    padding: 20px 16px;
  }

  .project-home__focus,
  .project-home__grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .project-home__focus,
  .project-home__grid {
    grid-template-columns: 1fr;
  }
}
</style>
