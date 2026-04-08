<template>
  <el-dialog
    :model-value="visible"
    title="新建角色"
    width="520px"
    destroy-on-close
    @close="$emit('close')"
  >
    <el-form label-position="top" size="small">
      <el-form-item label="角色名称（必填）">
        <el-input v-model="form.name" placeholder="输入角色名" />
      </el-form-item>
      <el-form-item label="特质标签（每行一条）">
        <el-input v-model="traitsText" type="textarea" :rows="2" placeholder="如：勇敢&#10;正义" />
      </el-form-item>
      <el-form-item label="目标">
        <el-input v-model="form.goal" placeholder="角色的核心目标" />
      </el-form-item>
      <el-form-item label="背景">
        <el-input v-model="form.backstory" type="textarea" :rows="3" placeholder="角色背景故事" />
      </el-form-item>
      <el-form-item label="阵营">
        <el-input v-model="form.faction" placeholder="所属阵营" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" @click="handleSubmit">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import type { CharacterDetail } from '@/types/api'

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'submit', data: Partial<CharacterDetail>): void
}>()

const form = ref({ name: '', goal: '', backstory: '', faction: '' })
const traitsText = ref('')

watch(() => props.visible, (v) => {
  if (v) {
    form.value = { name: '', goal: '', backstory: '', faction: '' }
    traitsText.value = ''
  }
})

function handleSubmit() {
  if (!form.value.name.trim()) {
    ElMessage.warning('请输入角色名称')
    return
  }
  const traits = traitsText.value.split('\n').map(s => s.trim()).filter(Boolean)
  emit('submit', { ...form.value, name: form.value.name.trim(), traits })
}
</script>
