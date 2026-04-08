<template>
  <el-dialog
    :model-value="visible"
    title="新建力量体系"
    width="620px"
    @close="$emit('close')"
  >
    <el-form label-position="top">
      <el-form-item label="体系名称">
        <el-input v-model="name" placeholder="例如：灵纹共鸣体系" />
      </el-form-item>
      <el-form-item label="模板参考">
        <el-select v-model="template" style="width: 100%">
          <el-option label="自定义" value="custom" />
          <el-option
            v-for="t in templates"
            :key="t.template"
            :label="`${t.name}（${t.level_count}阶）`"
            :value="t.template"
          />
        </el-select>
      </el-form-item>
    </el-form>

    <el-alert
      v-if="selectedTemplate"
      type="info"
      :closable="false"
      show-icon
      :title="`预览阶层：${selectedTemplate.preview_levels.join(' / ')}`"
    />

    <template #footer>
      <el-button @click="$emit('close')">取消</el-button>
      <el-button type="primary" @click="confirmCreate">创建</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { PowerTemplateSummary } from '@/api/world'

const props = defineProps<{
  visible: boolean
  templates: PowerTemplateSummary[]
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'create', payload: { name: string; template: string }): void
}>()

const name = ref('')
const template = ref('custom')

watch(() => props.visible, (v) => {
  if (v) {
    name.value = '新力量体系'
    template.value = 'custom'
  }
})

const selectedTemplate = computed(() => props.templates.find((t) => t.template === template.value) || null)

function confirmCreate() {
  emit('create', { name: name.value.trim() || '新力量体系', template: template.value })
}
</script>
