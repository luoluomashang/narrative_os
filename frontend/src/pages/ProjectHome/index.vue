<template>
  <div class="project-home">
    <div class="project-home__header">
      <h1 class="project-home__title">{{ projectInfo?.project_name || projectId }}</h1>
      <p class="project-home__subtitle" v-if="projectInfo">
        第 {{ projectInfo.current_chapter }} 章 · 卷 {{ projectInfo.current_volume }}
      </p>
      <el-skeleton v-else :rows="1" animated />
    </div>

    <el-row :gutter="16" class="project-home__actions">
      <el-col :span="6">
        <el-button type="primary" size="large" @click="goTo('write')" block>
          ✍️ 继续撰写
        </el-button>
      </el-col>
      <el-col :span="6">
        <el-button size="large" @click="goTo('trpg')" block>
          🎲 开始 TRPG
        </el-button>
      </el-col>
      <el-col :span="6">
        <el-button size="large" @click="goTo('chapters')" block>
          📚 查看章节
        </el-button>
      </el-col>
      <el-col :span="6">
        <el-button size="large" @click="goTo('worldbuilder')" block>
          🌍 世界构建
        </el-button>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top:16px">
      <el-col :span="12">
        <el-card header="项目信息">
          <el-descriptions :column="2" v-if="projectInfo" border>
            <el-descriptions-item label="项目ID">{{ projectId }}</el-descriptions-item>
            <el-descriptions-item label="当前章节">{{ projectInfo.current_chapter }}</el-descriptions-item>
            <el-descriptions-item label="当前卷">{{ projectInfo.current_volume }}</el-descriptions-item>
            <el-descriptions-item label="版本快照">{{ projectInfo.versions?.length ?? 0 }}</el-descriptions-item>
          </el-descriptions>
          <el-skeleton v-else :rows="3" animated />
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card header="工作流进度">
          <el-steps direction="vertical" :active="workflowStep" finish-status="success">
            <el-step title="世界构建" description="设定世界观、角色和情节节点" />
            <el-step title="情节规划" description="章节大纲与钩子设计" />
            <el-step title="章节生成" :description="`已生成 ${projectInfo?.current_chapter ?? 0} 章`" />
            <el-step title="审核与导出" description="质量检查与全本导出" />
          </el-steps>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
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
}

.project-home__header {
  margin-bottom: 24px;
}

.project-home__title {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text-primary);
  margin: 0 0 4px;
}

.project-home__subtitle {
  color: var(--color-text-secondary);
  margin: 0;
}

.project-home__actions {
  margin-bottom: 8px;
}
</style>
