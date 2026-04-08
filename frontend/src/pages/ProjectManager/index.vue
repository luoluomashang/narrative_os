<template>
  <div class="pm-page">
    <div class="pm-header">
      <h2 class="pm-title">全部项目</h2>
      <div class="pm-header-right">
        <el-input
          v-model="searchQuery"
          placeholder="搜索项目名称"
          :prefix-icon="Search"
          style="width: 200px"
          clearable
        />
        <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">新建项目</el-button>
      </div>
    </div>

    <!-- Project card grid -->
    <div v-if="store.loading" class="pm-loading">
      <el-skeleton :rows="2" animated />
    </div>
    <el-empty v-else-if="filteredProjects.length === 0" description="暂无项目" />
    <div v-else class="project-grid">
      <el-card
        v-for="proj in filteredProjects"
        :key="proj.project_id"
        class="project-card"
        :class="{ 'project-card--active': store.projectId === proj.project_id }"
        shadow="hover"
        @click="openProject(proj.project_id)"
      >
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
      </el-card>
    </div>

    <!-- Create project dialog -->
    <el-dialog v-model="showCreateDialog" title="新建项目" width="480px" draggable>
      <el-form ref="createFormRef" :model="form" :rules="formRules" label-width="80px">
        <el-form-item label="项目 ID" prop="project_id">
          <el-input v-model="form.project_id" placeholder="英文/数字/连字符，如 my-novel" />
        </el-form-item>
        <el-form-item label="标题" prop="title">
          <el-input v-model="form.title" placeholder="小说标题（可选）" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="form.genre" placeholder="选择类型（可选）" clearable style="width: 100%">
            <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="一句话简介（可选）" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="creating" @click="handleCreate">创建</el-button>
      </template>
    </el-dialog>

    <!-- Edit dialog -->
    <el-dialog v-model="showEditDialog" title="编辑项目" width="480px" draggable>
      <el-form :model="editForm" label-width="80px">
        <el-form-item label="标题">
          <el-input v-model="editForm.title" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="editForm.genre" clearable style="width: 100%">
            <el-option v-for="g in genres" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="editForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showEditDialog = false">取消</el-button>
        <el-button type="primary" :loading="updating" @click="handleUpdate">保存</el-button>
      </template>
    </el-dialog>

    <!-- Chapter view dialog -->
    <el-dialog v-model="showChapterDialog" :title="`第${chapterModal.chapter}章`" width="720px">
      <div v-if="chapterModal.loading" style="padding: 24px; text-align: center">
        <el-skeleton :rows="6" animated />
      </div>
      <pre v-else class="chapter-text">{{ chapterModal.text }}</pre>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Plus, MoreFilled, View, Edit, Box, Delete } from '@element-plus/icons-vue'
import type { FormInstance, FormRules } from 'element-plus'
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
  display: flex;
  flex-direction: column;
  gap: 20px;
  max-width: 1100px;
  margin: 0 auto;
}

.pm-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.pm-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin: 0;
}

.pm-header-right {
  display: flex;
  gap: 12px;
  align-items: center;
}

.pm-loading {
  padding: 24px;
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
</style>
