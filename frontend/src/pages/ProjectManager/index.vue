<template>
  <div class="pm-page">
    <SystemPageHeader
      eyebrow="Projects"
      title="项目目录"
      description="集中查看、检索并维护当前工作区下的所有叙事项目。"
    >
      <template #meta>
        <span class="pm-meta-pill">项目数 {{ filteredProjects.length }}</span>
      </template>
    </SystemPageHeader>

    <SystemSection>
      <template #actions>
        <SystemFormField class="pm-search" label="检索项目" for-id="project-search">
          <el-input
            id="project-search"
            v-model="searchQuery"
            placeholder="搜索项目名称"
            :prefix-icon="Search"
            clearable
          />
        </SystemFormField>
        <SystemButton variant="primary" @click="showCreateDialog = true">
          <el-icon><Plus /></el-icon>
          <span>新建项目</span>
        </SystemButton>
      </template>

      <SystemErrorState
        v-if="store.error && !store.loading"
        :message="store.error"
        action-label="重新加载"
        @action="handleReloadProjects"
      />

      <div v-if="store.loading" class="pm-loading">
        <SystemSkeleton v-for="index in 3" :key="index" card show-header :rows="3" />
      </div>

      <SystemEmpty
        v-else-if="filteredProjects.length === 0"
        title="还没有项目"
        description="创建第一个项目后，这里会显示基础信息、最近更新时间和快捷操作。"
      >
        <template #action>
          <SystemButton variant="primary" @click="showCreateDialog = true">立即创建项目</SystemButton>
        </template>
      </SystemEmpty>

      <div v-else class="project-grid">
        <SystemCard
          v-for="proj in filteredProjects"
          :key="proj.project_id"
          class="project-card"
          :class="{ 'project-card--active': store.projectId === proj.project_id }"
          interactive
          @click="openProject(proj.project_id)"
        >
          <template #header>
            <div class="proj-header">
              <span class="proj-title">{{ proj.title || proj.project_id }}</span>
              <el-dropdown trigger="click" @command="(cmd: string) => handleCommand(cmd, proj.project_id)" @click.stop>
                <el-button :icon="MoreFilled" text circle size="small" @click.stop />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item command="view" :icon="View">查看项目</el-dropdown-item>
                    <el-dropdown-item command="edit" :icon="Edit">编辑信息</el-dropdown-item>
                    <el-dropdown-item command="archive" :icon="Box">归档</el-dropdown-item>
                    <el-dropdown-item command="delete" :icon="Delete" divided style="color: var(--el-color-danger)">删除</el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>

          <div class="proj-id">{{ proj.project_id }}</div>
          <div class="proj-tags">
            <el-tag v-if="(proj as ProjectListItemExt).genre" size="small" type="info">{{ (proj as ProjectListItemExt).genre }}</el-tag>
            <el-tag size="small" :type="(proj as ProjectListItemExt).status === 'active' ? 'success' : 'warning'">
              {{ (proj as ProjectListItemExt).status === 'active' ? '活跃' : (proj as ProjectListItemExt).status === 'archived' ? '已归档' : '活跃' }}
            </el-tag>
          </div>
          <div class="proj-meta">
            第{{ proj.chapter_count }}章 · {{ formatDate(proj.last_modified) }}
          </div>
        </SystemCard>
      </div>
    </SystemSection>

    <el-dialog v-model="showCreateDialog" title="新建项目" width="480px" draggable>
      <el-form ref="createFormRef" :model="form" :rules="formRules" label-width="0">
        <SystemFormField label="项目 ID" hint="仅支持英文、数字、下划线和连字符。" required>
          <el-form-item prop="project_id" class="pm-form-item">
            <el-input v-model="form.project_id" placeholder="英文/数字/连字符，如 my-novel" />
          </el-form-item>
        </SystemFormField>
        <SystemFormField label="标题">
          <el-form-item prop="title" class="pm-form-item">
            <el-input v-model="form.title" placeholder="小说标题（可选）" />
          </el-form-item>
        </SystemFormField>
        <SystemFormField label="类型">
          <el-form-item class="pm-form-item">
            <el-select v-model="form.genre" placeholder="选择类型（可选）" clearable style="width: 100%">
              <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
        </SystemFormField>
        <SystemFormField label="简介">
          <el-form-item class="pm-form-item">
            <el-input v-model="form.description" type="textarea" :rows="2" placeholder="一句话简介（可选）" />
          </el-form-item>
        </SystemFormField>
      </el-form>
      <template #footer>
        <SystemButton @click="showCreateDialog = false">取消</SystemButton>
        <SystemButton variant="primary" :loading="creating" @click="handleCreate">创建</SystemButton>
      </template>
    </el-dialog>

    <el-dialog v-model="showEditDialog" title="编辑项目" width="480px" draggable>
      <el-form :model="editForm" label-width="0">
        <SystemFormField label="标题">
          <el-form-item class="pm-form-item">
            <el-input v-model="editForm.title" />
          </el-form-item>
        </SystemFormField>
        <SystemFormField label="类型">
          <el-form-item class="pm-form-item">
            <el-select v-model="editForm.genre" clearable style="width: 100%">
              <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
        </SystemFormField>
        <SystemFormField label="简介">
          <el-form-item class="pm-form-item">
            <el-input v-model="editForm.description" type="textarea" :rows="2" />
          </el-form-item>
        </SystemFormField>
      </el-form>
      <template #footer>
        <SystemButton @click="showEditDialog = false">取消</SystemButton>
        <SystemButton variant="primary" :loading="updating" @click="handleUpdate">保存</SystemButton>
      </template>
    </el-dialog>

    <el-dialog v-model="showChapterDialog" :title="`第${chapterModal.chapter}章`" width="720px">
      <div v-if="chapterModal.loading" style="padding: 24px; text-align: center">
        <SystemSkeleton card :rows="6" />
      </div>
      <pre v-else class="chapter-text">{{ chapterModal.text }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElIcon, ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, MoreFilled, View, Edit, Box, Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemErrorState from '@/components/system/SystemErrorState.vue'
import SystemFormField from '@/components/system/SystemFormField.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import { useProjectStore } from '@/stores/projectStore'
import { projects } from '@/api'
import type { ProjectListItem } from '@/types/api'

interface ProjectListItemExt extends ProjectListItem {
  genre?: string
  status?: string
}

const router = useRouter()
const store = useProjectStore()

const searchQuery = ref('')
const showCreateDialog = ref(false)
const showEditDialog = ref(false)
const showChapterDialog = ref(false)
const creating = ref(false)
const updating = ref(false)
const editingProjectId = ref('')

const createFormRef = ref<FormInstance>()

const form = ref({ project_id: '', title: '', genre: '', description: '' })
const editForm = ref({ title: '', genre: '', description: '' })

const genres = ['仙侠', '玄幻', '都市', '科幻', '言情', '悬疑', '历史']

const formRules: FormRules = {
  project_id: [
    { required: true, message: '项目 ID 不能为空', trigger: 'blur' },
    { pattern: /^[a-zA-Z0-9_-]+$/, message: '只允许字母、数字、下划线和连字符', trigger: 'blur' },
  ],
}

const chapterModal = ref({ chapter: 0, loading: false, text: '' })

const filteredProjects = computed(() =>
  store.projectList.filter(p =>
    !searchQuery.value ||
    p.project_id.includes(searchQuery.value) ||
    (p.title || '').includes(searchQuery.value)
  )
)

function formatDate(iso: string): string {
  if (!iso) return '未知'
  try { return new Date(iso).toLocaleDateString('zh-CN') } catch { return iso }
}

function openProject(id: string) {
  store.selectProject(id).catch(() => {
    ElMessage.error('打开项目失败')
  })
  router.push(`/project/${id}`)
}

function handleReloadProjects() {
  store.loadProjects()
}

async function handleCommand(command: string, projectId: string) {
  if (command === 'view') {
    openProject(projectId)
  } else if (command === 'edit') {
    const proj = store.projectList.find(p => p.project_id === projectId) as ProjectListItemExt | undefined
    editingProjectId.value = projectId
    editForm.value = {
      title: proj?.title || '',
      genre: proj?.genre || '',
      description: '',
    }
    showEditDialog.value = true
  } else if (command === 'archive') {
    try {
      await projects.archive(projectId)
      ElMessage.success('项目已归档')
      await store.loadProjects()
    } catch {
      ElMessage.error('归档失败')
    }
  } else if (command === 'delete') {
    const proj = store.projectList.find(p => p.project_id === projectId) as ProjectListItemExt | undefined
    const displayName = proj?.title || projectId
    const chapterInfo = proj?.chapter_count ? `（已有 ${proj.chapter_count} 章）` : ''
    await ElMessageBox.confirm(
      `确认删除项目「${displayName}」${chapterInfo}？此操作不可逆。`,
      '删除确认',
      {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        confirmButtonClass: 'el-button--danger',
      },
    )
    try {
      await store.deleteProject(projectId)
      ElMessage.success('项目已删除')
    } catch {
      ElMessage.error('删除失败')
    }
  }
}

async function handleCreate() {
  if (!createFormRef.value) return
  await createFormRef.value.validate(async (valid) => {
    if (!valid) return
    creating.value = true
    try {
      await store.createProject(form.value)
      ElMessage.success(`项目 "${form.value.project_id}" 已创建`)
      showCreateDialog.value = false
      form.value = { project_id: '', title: '', genre: '', description: '' }
      createFormRef.value?.resetFields()
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      ElMessage.error(err.response?.data?.detail ?? '创建失败')
    } finally {
      creating.value = false
    }
  })
}

async function handleUpdate() {
  updating.value = true
  try {
    await projects.update(editingProjectId.value, editForm.value)
    await store.loadProjects()
    ElMessage.success('已保存')
    showEditDialog.value = false
  } catch {
    ElMessage.error('保存失败')
  } finally {
    updating.value = false
  }
}

onMounted(() => {
  store.loadProjects()
})
</script>

<style scoped>
.pm-page {
  padding: 24px;
  display: grid;
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
}

.pm-meta-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.pm-search {
  min-width: 240px;
}

.pm-loading {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.project-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.project-card {
  cursor: pointer;
  transition: border-color 150ms;
}

.project-card--active {
  border-color: var(--el-color-primary) !important;
}

.pm-form-item {
  margin-bottom: 0;
}

.pm-form-item :deep(.el-form-item__content) {
  display: block;
  line-height: normal;
}

.proj-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.proj-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.proj-id {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 8px;
  font-family: monospace;
}

.proj-tags {
  display: flex;
  gap: 6px;
  margin-bottom: 10px;
}

.proj-meta {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}

.chapter-text {
  white-space: pre-wrap;
  word-break: break-all;
  font-size: 14px;
  line-height: 1.8;
  color: var(--el-text-color-primary);
  font-family: inherit;
  max-height: 60vh;
  overflow-y: auto;
  margin: 0;
}

@media (max-width: 840px) {
  .pm-page {
    padding: 20px 16px;
  }

  .pm-search {
    min-width: 100%;
  }
}
</style>
