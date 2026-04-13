<template>
  <div class="concept-page">
    <div class="concept-header">
      <h2 class="concept-title">故事概念</h2>
      <p class="concept-subtitle">一句话 / 一段话描述你的故事核心</p>
    </div>

    <div v-if="loading" class="concept-loading">
      <el-skeleton :rows="6" animated />
    </div>

    <el-form v-else :model="form" label-position="top" class="concept-form">
      <!-- 世界类型 -->
      <el-form-item label="世界类型">
        <el-select v-model="form.world_type" placeholder="选择世界类型" style="width: 240px">
          <el-option label="大陆流" value="continental" />
          <el-option label="位面/世界流" value="planar" />
          <el-option label="星际/宇宙流" value="interstellar" />
          <el-option label="多层世界" value="multi_layer" />
        </el-select>
      </el-form-item>

      <!-- 一句话概念 -->
      <el-form-item label="一句话概念">
        <el-input
          v-model="form.one_sentence"
          placeholder="用一句话概括故事核心，例如：穿越修仙世界的少年逆天崛起"
          maxlength="100"
          show-word-limit
          clearable
        />
      </el-form-item>

      <!-- 一段话概念 -->
      <el-form-item label="一段话简介">
        <el-input
          v-model="form.one_paragraph"
          type="textarea"
          :rows="5"
          placeholder="用一段话描述故事背景、主角、核心冲突和目标..."
          maxlength="500"
          show-word-limit
        />
      </el-form-item>

      <!-- 类型标签 -->
      <el-form-item label="类型标签">
        <div class="tag-area">
          <el-tag
            v-for="tag in form.genre_tags"
            :key="tag"
            closable
            type="primary"
            class="genre-tag"
            @close="removeTag(tag)"
          >
            {{ tag }}
          </el-tag>
          <el-input
            v-if="tagInputVisible"
            ref="tagInputRef"
            v-model="tagInputValue"
            size="small"
            class="tag-input"
            maxlength="12"
            @keyup.enter="addTag"
            @blur="addTag"
          />
          <el-button v-else size="small" plain @click="showTagInput">
            + 添加标签
          </el-button>
        </div>
        <div class="tag-presets">
          <span class="preset-label">常用：</span>
          <el-tag
            v-for="preset in presetTags"
            :key="preset"
            size="small"
            class="preset-tag"
            :effect="form.genre_tags.includes(preset) ? 'dark' : 'plain'"
            @click="togglePreset(preset)"
          >
            {{ preset }}
          </el-tag>
        </div>
      </el-form-item>

      <!-- 操作按钮 -->
      <el-form-item>
        <el-button type="primary" :loading="saving" @click="handleSave">
          保存概念
        </el-button>
        <el-button plain @click="handleGoWorld">
          前往世界构建 →
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/projectStore'
import { concept as conceptApi } from '@/api/world'
import type { ConceptData } from '@/api/world'

const store = useProjectStore()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref<InstanceType<typeof import('element-plus')['ElInput']>>()

const form = reactive<ConceptData>({
  one_sentence: '',
  one_paragraph: '',
  genre_tags: [],
  world_type: 'continental',
})

const presetTags = [
  '修真', '玄幻', '系统', '斗气', '魔法', '异能',
  '星际', '末世', '都市', '历史', '热血', '悬疑',
]

onMounted(async () => {
  if (!store.projectId) return
  try {
    const res = await conceptApi.get(store.projectId)
    Object.assign(form, res.data)
  } catch {
    // 新项目：使用默认空值
  } finally {
    loading.value = false
  }
})

async function handleSave() {
  if (!store.projectId) return
  saving.value = true
  try {
    await conceptApi.update(store.projectId, { ...form })
    ElMessage.success('故事概念已保存')
  } finally {
    saving.value = false
  }
}

function handleGoWorld() {
  router.push(`/project/${store.projectId}/worldbuilder`)
}

function removeTag(tag: string) {
  const idx = form.genre_tags.indexOf(tag)
  if (idx >= 0) form.genre_tags.splice(idx, 1)
}

function showTagInput() {
  tagInputVisible.value = true
  nextTick(() => tagInputRef.value?.focus())
}

function addTag() {
  const val = tagInputValue.value.trim()
  if (val && !form.genre_tags.includes(val)) form.genre_tags.push(val)
  tagInputVisible.value = false
  tagInputValue.value = ''
}

function togglePreset(preset: string) {
  const idx = form.genre_tags.indexOf(preset)
  if (idx >= 0) form.genre_tags.splice(idx, 1)
  else form.genre_tags.push(preset)
}
</script>

<style scoped>
.concept-page {
  max-width: 720px;
  margin: 0 auto;
  padding: 32px 24px;
}

.concept-header {
  margin-bottom: 32px;
}

.concept-title {
  font-size: 24px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 4px;
}

.concept-subtitle {
  color: var(--el-text-color-secondary);
  font-size: 14px;
}

.concept-loading {
  padding: 24px 0;
}

.concept-form {
  background: var(--el-bg-color);
  border-radius: 8px;
  padding: 24px;
  box-shadow: var(--el-box-shadow-light);
}

.tag-area {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
}

.genre-tag {
  cursor: default;
}

.tag-input {
  width: 100px;
}

.tag-presets {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.preset-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.preset-tag {
  cursor: pointer;
}
</style>
