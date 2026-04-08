<template>
  <div class="profile-tab">
    <el-form label-position="top" size="small">
      <el-form-item label="别名 / 称号">
        <el-input v-model="aliasText" type="textarea" :rows="2" placeholder="每行一个别名" />
      </el-form-item>
      <el-form-item label="外貌 / 形象描述">
        <el-input v-model="localModel.description" type="textarea" :rows="4" placeholder="角色外貌特征" />
      </el-form-item>
      <el-form-item label="性格核心描述">
        <el-input v-model="localModel.personality" type="textarea" :rows="3" placeholder="角色性格概述" />
      </el-form-item>
      <el-form-item label="目标">
        <el-input v-model="localModel.goal" placeholder="角色核心目标" />
      </el-form-item>
      <el-form-item label="背景故事">
        <el-input v-model="localModel.backstory" type="textarea" :rows="5" placeholder="角色背景故事" />
      </el-form-item>
      <el-form-item label="语言风格">
        <el-input v-model="localModel.speech_style" placeholder="口癖、用词习惯等" />
      </el-form-item>
      <el-form-item label="口头禅（每行一条）">
        <el-input v-model="catchphrasesText" type="textarea" :rows="2" placeholder="如：绝不认输&#10;有趣" />
      </el-form-item>
      <el-form-item label="阵营">
        <el-input v-model="localModel.faction" placeholder="所属阵营" />
      </el-form-item>
    </el-form>
    <div class="profile-actions">
      <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
      <el-button type="danger" plain @click="handleDelete">删除角色</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { CharacterDetail } from '@/types/api'

const props = defineProps<{
  model: CharacterDetail
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'save', data: Partial<CharacterDetail>): void
  (e: 'delete'): void
}>()

const localModel = ref<Partial<CharacterDetail>>({})
const aliasText = ref('')
const catchphrasesText = ref('')

watch(() => props.model, (m) => {
  if (m) {
    localModel.value = {
      description: m.description ?? '',
      personality: m.personality ?? '',
      goal: m.goal ?? '',
      backstory: m.backstory ?? '',
      speech_style: m.speech_style ?? '',
      faction: m.faction ?? '',
    }
    aliasText.value = (m.alias ?? []).join('\n')
    catchphrasesText.value = (m.catchphrases ?? []).join('\n')
  }
}, { immediate: true })

function handleSave() {
  // Sync text fields back
  localModel.value.alias = aliasText.value.split('\n').map(s => s.trim()).filter(Boolean)
  localModel.value.catchphrases = catchphrasesText.value.split('\n').map(s => s.trim()).filter(Boolean)
  // Emit data upward for parent to merge (avoid direct prop mutation)
  emit('save', { ...localModel.value })
}

async function handleDelete() {
  try {
    await ElMessageBox.confirm(
      `确定删除角色「${props.model.name}」？此操作不可撤销。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
    emit('delete')
  } catch {
    // cancelled
  }
}
</script>

<style scoped>
.profile-tab { padding: 4px 0; }
.profile-actions {
  display: flex;
  gap: 12px;
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
