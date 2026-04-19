<template>
  <div class="concept-page">
    <SystemPageHeader
      eyebrow="Story Concept"
      title="故事概念"
      description="先用引导卡收束题材、钩子和世界类型，再把一句话与一段话概念送入后续世界构建与章节写作。"
    >
      <template #meta>
        <span class="meta-pill">项目 {{ store.projectId || '未挂载' }}</span>
        <span class="meta-pill">世界 {{ worldTypeLabel(form.world_type) }}</span>
        <span class="meta-pill">标签 {{ form.genre_tags.length }}</span>
        <span class="meta-pill">完整度 {{ completionLabel }}</span>
      </template>
    </SystemPageHeader>

    <div v-if="loading" class="concept-loading">
      <SystemSkeleton :rows="10" show-header card />
    </div>

    <template v-else>
      <SystemStatusBanner
        v-if="reviewRequested"
        :status="reviewBanner.status"
        :title="reviewBanner.title"
        :message="reviewBanner.message"
        :description="reviewBanner.description"
      >
        <template #actions>
          <SystemButton v-if="reviewBanner.status !== 'success'" variant="ghost" @click="focusPrimaryGap">
            先补主缺口
          </SystemButton>
          <SystemButton variant="quiet" @click="runPrecheck">重新检查</SystemButton>
        </template>
      </SystemStatusBanner>

      <SystemSection
        title="概念引导卡"
        description="把题材模板、叙事钩子和世界类型建议前置到首屏，避免一上来就只剩空白表单。"
      >
        <div class="guide-grid">
          <SystemCard
            title="题材模板"
            :description="activeTemplate.summary"
            tone="subtle"
            class="guide-card"
          >
            <div class="guide-card__body">
              <div class="guide-pill-row">
                <span class="guide-pill">{{ activeTemplate.label }}</span>
                <span class="guide-pill guide-pill--muted">{{ worldTypeLabel(activeTemplate.worldType) }}</span>
              </div>
              <p class="guide-copy"><strong>一句话：</strong>{{ activeTemplate.oneSentence }}</p>
              <p class="guide-copy"><strong>展开提示：</strong>{{ activeTemplate.paragraphHint }}</p>
            </div>
            <template #footer>
              <SystemButton variant="secondary" size="sm" @click="applyTemplate">采用模板</SystemButton>
              <SystemButton variant="ghost" size="sm" @click="rotateTemplate">换一组</SystemButton>
            </template>
          </SystemCard>

          <SystemCard
            title="叙事钩子"
            :description="activeHook.summary"
            tone="subtle"
            class="guide-card"
          >
            <div class="guide-card__body">
              <div class="guide-pill-row">
                <span class="guide-pill">{{ activeHook.label }}</span>
              </div>
              <p class="guide-copy"><strong>推荐落点：</strong>{{ activeHook.paragraphLead }}</p>
              <p class="guide-copy"><strong>适配方式：</strong>先把冲突落在一段话简介里，再决定是否写进一句话概念。</p>
            </div>
            <template #footer>
              <SystemButton variant="secondary" size="sm" @click="applyHook">采用钩子</SystemButton>
              <SystemButton variant="ghost" size="sm" @click="rotateHook">换一组</SystemButton>
            </template>
          </SystemCard>

          <SystemCard
            title="世界类型建议"
            :description="activeWorldSuggestion.description"
            tone="subtle"
            class="guide-card"
          >
            <div class="guide-card__body">
              <div class="guide-pill-row">
                <span class="guide-pill">{{ activeWorldSuggestion.label }}</span>
                <span class="guide-pill guide-pill--muted">{{ worldTypeLabel(activeWorldSuggestion.worldType) }}</span>
              </div>
              <p class="guide-copy"><strong>适用题材：</strong>{{ activeWorldSuggestion.fit }}</p>
              <p class="guide-copy"><strong>会影响：</strong>{{ activeWorldSuggestion.impact }}</p>
            </div>
            <template #footer>
              <SystemButton variant="secondary" size="sm" @click="applyWorldSuggestion">采用建议</SystemButton>
              <SystemButton variant="ghost" size="sm" @click="rotateWorldSuggestion">换一组</SystemButton>
            </template>
          </SystemCard>
        </div>
      </SystemSection>

      <SystemCard class="concept-card" title="概念输入" description="中部仍然保留一句话与一段话输入，但把结构提示放在字段附近，而不是留给用户自行猜格式。">
        <el-form :model="form" label-position="top" class="concept-form">
          <el-form-item label="世界类型">
            <div class="field-stack">
              <el-select v-model="form.world_type" placeholder="选择世界类型" class="world-select">
                <el-option label="大陆流" value="continental" />
                <el-option label="位面/世界流" value="planar" />
                <el-option label="星际/宇宙流" value="interstellar" />
                <el-option label="多层世界" value="multi_layer" />
              </el-select>
              <p class="field-hint">世界类型会直接影响世界构建的默认结构与后续剧情组织方式。</p>
            </div>
          </el-form-item>

          <el-form-item label="一句话概念">
            <div class="field-stack">
              <div class="structure-hints">
                <span class="structure-chip">主角是谁</span>
                <span class="structure-chip">陷入什么处境</span>
                <span class="structure-chip">必须采取什么行动</span>
                <span class="structure-chip">失败代价是什么</span>
              </div>
              <el-input
                ref="oneSentenceRef"
                v-model="form.one_sentence"
                placeholder="例如：被逐出宗门的少年，为了夺回命格只能借系统一路逆推仙门秩序"
                maxlength="100"
                show-word-limit
                clearable
              />
            </div>
          </el-form-item>

          <el-form-item label="一段话简介">
            <div class="field-stack">
              <div class="outline-grid">
                <div class="outline-card">
                  <span>1</span>
                  <p>先交代世界背景和主角起点</p>
                </div>
                <div class="outline-card">
                  <span>2</span>
                  <p>再说触发事件和核心冲突</p>
                </div>
                <div class="outline-card">
                  <span>3</span>
                  <p>最后落到当前目标与推进方向</p>
                </div>
              </div>
              <el-input
                ref="oneParagraphRef"
                v-model="form.one_paragraph"
                type="textarea"
                :rows="6"
                placeholder="建议覆盖：世界背景、主角起点、触发事件、核心冲突、近期目标。"
                maxlength="500"
                show-word-limit
              />
            </div>
          </el-form-item>

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
              <SystemButton v-else variant="quiet" size="sm" @click="showTagInput">
                + 添加标签
              </SystemButton>
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

          <el-form-item>
            <div class="concept-actions">
              <SystemButton variant="secondary" @click="runPrecheck">生成前检查</SystemButton>
              <SystemButton variant="ghost" @click="resetDraft">重写草稿</SystemButton>
              <SystemButton variant="primary" :loading="saving" @click="handleSave">
                保存概念
              </SystemButton>
              <SystemButton variant="quiet" :disabled="hasBlockingGaps" @click="handleSaveAndGoWorld">
                保存并前往世界构建 →
              </SystemButton>
            </div>
          </el-form-item>
        </el-form>
      </SystemCard>

      <SystemSection
        title="下游影响摘要"
        description="“将影响的模块”改到页面下方摘要区，不再做成常驻右栏，避免概念页重新变成三栏布局。"
        dense
      >
        <div class="impact-grid">
          <SystemCard
            v-for="module in impactModules"
            :key="module.name"
            :title="module.name"
            :description="module.description"
            tone="subtle"
            class="impact-card"
          >
            <p class="impact-copy">{{ module.detail }}</p>
          </SystemCard>
        </div>
      </SystemSection>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { ElInput } from 'element-plus'

import { concept as conceptApi } from '@/api/world'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'
import SystemStatusBanner from '@/components/system/SystemStatusBanner.vue'
import { useProjectStore } from '@/stores/projectStore'
import type { ConceptData } from '@/api/world'

type ConceptTemplate = {
  id: string
  label: string
  summary: string
  oneSentence: string
  paragraphHint: string
  tags: string[]
  worldType: ConceptData['world_type']
}

type HookSuggestion = {
  id: string
  label: string
  summary: string
  paragraphLead: string
}

type WorldSuggestion = {
  id: string
  label: string
  worldType: ConceptData['world_type']
  description: string
  fit: string
  impact: string
  tags: string[]
}

const store = useProjectStore()
const router = useRouter()

const loading = ref(true)
const saving = ref(false)
const reviewRequested = ref(false)
const tagInputVisible = ref(false)
const tagInputValue = ref('')
const tagInputRef = ref<InstanceType<typeof ElInput>>()
const oneSentenceRef = ref<InstanceType<typeof ElInput>>()
const oneParagraphRef = ref<InstanceType<typeof ElInput>>()

const templateIndex = ref(0)
const hookIndex = ref(0)
const worldSuggestionIndex = ref(0)

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

const conceptTemplates: ConceptTemplate[] = [
  {
    id: 'rise-from-ash',
    label: '逆袭成长',
    summary: '适合主角起点很低、靠一次机会逆推秩序的男频主线。',
    oneSentence: '被逐出主流秩序的主角，为了夺回命运只能借一条禁忌路径向上逆袭。',
    paragraphHint: '先写主角为什么被压在底层，再写他抓到的唯一机会，最后落到他必须付出的代价和短期目标。',
    tags: ['热血', '逆袭', '系统'],
    worldType: 'continental',
  },
  {
    id: 'mystery-survival',
    label: '悬疑求生',
    summary: '适合谜团驱动、规则压力重、每章都需要强钩子的叙事。',
    oneSentence: '被卷入异常规则网络的主角，必须一边解谜一边活下来，才能接近真正的操盘者。',
    paragraphHint: '先交代异常发生方式，再落到主角为什么不能退出，最后给出第一阶段必须解开的核心问题。',
    tags: ['悬疑', '规则', '求生'],
    worldType: 'multi_layer',
  },
  {
    id: 'expansion-frontier',
    label: '开拓经营',
    summary: '适合世界展开面大、势力与地图会持续扩张的长线项目。',
    oneSentence: '拿到边缘领地的主角，必须在各方势力挤压下扩张地盘，才能守住自己和身后的人。',
    paragraphHint: '先说明资源和秩序有多稀缺，再写主角获得的根据地，最后明确第一阶段要稳住什么、对抗谁。',
    tags: ['经营', '势力', '地图'],
    worldType: 'planar',
  },
]

const hookSuggestions: HookSuggestion[] = [
  {
    id: 'identity-reveal',
    label: '身份反转',
    summary: '适合在概念层提前埋下“主角其实不是表面身份”的主冲突。',
    paragraphLead: '钩子方向：主角当前身份只是伪装，真正身份一旦暴露就会引发秩序层面的连锁反扑。',
  },
  {
    id: 'deadline-pressure',
    label: '倒计时压力',
    summary: '适合章节持续推进，需要稳定“下一步必须做什么”的结构。',
    paragraphLead: '钩子方向：主角只有极短时间解决眼前问题，否则个人命运和更大局势都会一起失控。',
  },
  {
    id: 'reward-before-fall',
    label: '先给机会再抬代价',
    summary: '适合爽点项目，让机会和反噬同时出现，避免概念过平。',
    paragraphLead: '钩子方向：主角刚拿到看似完美的机会，代价和敌意就立刻跟上，逼他提前进入主线。',
  },
]

const worldSuggestions: WorldSuggestion[] = [
  {
    id: 'continental-tiered',
    label: '大陆阶层压迫',
    worldType: 'continental',
    description: '把宗门、王朝、城池等级组织成清晰阶层，适合热血成长和打脸结构。',
    fit: '修真、玄幻、热血逆袭',
    impact: '世界构建会优先展开势力层级、地区等级和晋升通道。',
    tags: ['大陆', '阶层', '势力'],
  },
  {
    id: 'planar-frontier',
    label: '位面远征扩张',
    worldType: 'planar',
    description: '把目标拆成多个区域或位面，方便做中长线阶段推进和地图开拓。',
    fit: '经营、远征、地图成长',
    impact: '情节画布会更适合阶段泳道和据点推进结构。',
    tags: ['位面', '经营', '远征'],
  },
  {
    id: 'multi-layer-rules',
    label: '多层规则世界',
    worldType: 'multi_layer',
    description: '把现实层、异常层、权力层拆开，方便悬疑和规则求生并行推进。',
    fit: '悬疑、规则、异常调查',
    impact: '写作和 TRPG 会更依赖状态切换、危险升级和信息差设计。',
    tags: ['规则', '悬疑', '多层'],
  },
]

const activeTemplate = computed(() => conceptTemplates[templateIndex.value % conceptTemplates.length])
const activeHook = computed(() => hookSuggestions[hookIndex.value % hookSuggestions.length])
const activeWorldSuggestion = computed(() => worldSuggestions[worldSuggestionIndex.value % worldSuggestions.length])

const precheckItems = computed(() => {
  const oneSentenceLength = form.one_sentence.trim().length
  const oneParagraphLength = form.one_paragraph.trim().length

  return [
    {
      key: 'one-sentence',
      label: '一句话概念',
      passed: oneSentenceLength >= 18,
      severity: 'blocking',
      message: oneSentenceLength >= 18 ? '主角、处境和行动已经形成一句话概念。' : '一句话概念仍过短，建议至少写到“主角 + 处境 + 行动”完整。',
    },
    {
      key: 'one-paragraph',
      label: '一段话简介',
      passed: oneParagraphLength >= 80,
      severity: 'blocking',
      message: oneParagraphLength >= 80 ? '一段话简介已具备世界背景和冲突展开。' : '一段话简介信息量不足，建议补到世界背景、触发事件和近期目标。',
    },
    {
      key: 'world-type',
      label: '世界类型',
      passed: Boolean(form.world_type),
      severity: 'blocking',
      message: form.world_type ? `当前已选择 ${worldTypeLabel(form.world_type)}。` : '需要先选择世界类型，才能稳定影响世界构建与情节画布。',
    },
    {
      key: 'genre-tags',
      label: '类型标签',
      passed: form.genre_tags.length >= 2,
      severity: 'warning',
      message: form.genre_tags.length >= 2 ? '标签数量足够，后续 Benchmark 和风格约束更容易收束。' : '建议至少补 2 个标签，避免后续风格和世界类型过于松散。',
    },
    {
      key: 'hook-density',
      label: '冲突钩子',
      passed: /(必须|只能|否则|倒计时|暴露|反扑|失控|机会|代价|真相)/.test(form.one_paragraph),
      severity: 'warning',
      message: /(必须|只能|否则|倒计时|暴露|反扑|失控|机会|代价|真相)/.test(form.one_paragraph)
        ? '简介里已经有明确钩子或风险词，后续更容易长出章节推进。'
        : '当前简介仍偏静态，建议补一个倒计时、反转或代价类钩子。',
    },
  ]
})

const blockingChecks = computed(() => precheckItems.value.filter((item) => !item.passed && item.severity === 'blocking'))
const warningChecks = computed(() => precheckItems.value.filter((item) => !item.passed && item.severity === 'warning'))
const hasBlockingGaps = computed(() => blockingChecks.value.length > 0)
const completionLabel = computed(() => `${precheckItems.value.filter((item) => item.passed).length}/${precheckItems.value.length}`)

const reviewBanner = computed(() => {
  if (blockingChecks.value.length > 0) {
    return {
      status: 'blocking' as const,
      title: '概念仍未达成生成前最低要求',
      message: `还有 ${blockingChecks.value.length} 个阻塞项需要先补齐。`,
      description: blockingChecks.value[0]?.message ?? '请先补全一句话概念、一段话简介和世界类型。',
    }
  }
  if (warningChecks.value.length > 0) {
    return {
      status: 'partial-failure' as const,
      title: '概念已可保存，但仍建议继续收束',
      message: `当前还有 ${warningChecks.value.length} 个建议项。`,
      description: warningChecks.value[0]?.message ?? '建议再补充标签和冲突钩子，让后续模块接得更稳。',
    }
  }
  return {
    status: 'success' as const,
    title: '概念结构已经完整',
    message: '可以继续进入世界构建或后续章节规划。',
    description: '当前一句话、简介、标签和世界类型都已满足概念阶段的主要要求。',
  }
})

const impactModules = computed(() => [
  {
    name: '世界构建',
    description: '世界类型和一段话简介会直接决定世界沙盘的默认结构。',
    detail: form.world_type
      ? `当前会优先按 ${worldTypeLabel(form.world_type)} 的组织方式展开地区、势力和规则。`
      : '先确认世界类型，再决定后续世界沙盘是做阶层推进、位面扩张还是规则分层。',
  },
  {
    name: '情节画布',
    description: '一句话概念会影响剧情组织方式和阶段目标。',
    detail: form.one_sentence.trim()
      ? `当前主线可概括为：${form.one_sentence.trim()}`
      : '一句话概念还未稳定，情节画布暂时无法明确主线目标和推进节拍。',
  },
  {
    name: '章节撰写',
    description: '一段话简介决定首章起点、阻力和近期主任务。',
    detail: form.one_paragraph.trim()
      ? '当前简介已经能为首章生成提供背景、冲突与近期目标。'
      : '补完一段话简介后，章节撰写页才能更快判断“当前主任务”和“下一步动作”。',
  },
  {
    name: 'Benchmark / 风格约束',
    description: '标签和钩子会影响对标策略、风格约束和后续诊断。',
    detail: form.genre_tags.length
      ? `当前标签：${form.genre_tags.join(' / ')}`
      : '建议补足类型标签，让对标和风格约束不至于停留在泛化状态。',
  },
])

onMounted(async () => {
  if (!store.projectId) {
    loading.value = false
    return
  }

  try {
    const res = await conceptApi.get(store.projectId)
    Object.assign(form, res.data)
  } catch {
    // 新项目：使用默认空值
  } finally {
    loading.value = false
  }
})

async function handleSave(): Promise<boolean> {
  if (!store.projectId) {
    ElMessage.warning('当前没有可保存的项目上下文')
    return false
  }

  saving.value = true
  try {
    await conceptApi.update(store.projectId, { ...form })
    ElMessage.success('故事概念已保存')
    return true
  } finally {
    saving.value = false
  }
}

async function handleSaveAndGoWorld() {
  const saved = await handleSave()
  if (saved) {
    handleGoWorld()
  }
}

function handleGoWorld() {
  if (!store.projectId) {
    return
  }
  router.push(`/project/${store.projectId}/worldbuilder`)
}

function runPrecheck() {
  reviewRequested.value = true
  if (blockingChecks.value.length > 0) {
    ElMessage.warning(`还有 ${blockingChecks.value.length} 个阻塞项需要先补齐`)
    return
  }
  if (warningChecks.value.length > 0) {
    ElMessage.info(`当前可继续，但还有 ${warningChecks.value.length} 个建议项`)
    return
  }
  ElMessage.success('概念结构完整，可以继续进入世界构建')
}

function focusPrimaryGap() {
  const primaryGap = blockingChecks.value[0]?.key ?? warningChecks.value[0]?.key
  if (primaryGap === 'one-sentence') {
    oneSentenceRef.value?.focus()
    return
  }
  if (primaryGap === 'one-paragraph') {
    oneParagraphRef.value?.focus()
  }
}

function removeTag(tag: string) {
  const idx = form.genre_tags.indexOf(tag)
  if (idx >= 0) {
    form.genre_tags.splice(idx, 1)
  }
}

function showTagInput() {
  tagInputVisible.value = true
  nextTick(() => tagInputRef.value?.focus())
}

function addTag() {
  const val = tagInputValue.value.trim()
  if (val && !form.genre_tags.includes(val)) {
    form.genre_tags.push(val)
  }
  tagInputVisible.value = false
  tagInputValue.value = ''
}

function togglePreset(preset: string) {
  const idx = form.genre_tags.indexOf(preset)
  if (idx >= 0) {
    form.genre_tags.splice(idx, 1)
  } else {
    form.genre_tags.push(preset)
  }
}

function mergeTags(tags: string[]) {
  for (const tag of tags) {
    if (!form.genre_tags.includes(tag)) {
      form.genre_tags.push(tag)
    }
  }
}

function applyTemplate() {
  form.one_sentence = activeTemplate.value.oneSentence
  form.one_paragraph = activeTemplate.value.paragraphHint
  form.world_type = activeTemplate.value.worldType
  mergeTags(activeTemplate.value.tags)
  ElMessage.success(`已采用模板：${activeTemplate.value.label}`)
}

function applyHook() {
  const hookLead = activeHook.value.paragraphLead
  form.one_paragraph = form.one_paragraph.includes(hookLead)
    ? form.one_paragraph
    : [hookLead, form.one_paragraph].filter(Boolean).join('\n')
  ElMessage.success(`已采用钩子：${activeHook.value.label}`)
}

function applyWorldSuggestion() {
  form.world_type = activeWorldSuggestion.value.worldType
  mergeTags(activeWorldSuggestion.value.tags)
  if (!form.one_paragraph.trim()) {
    form.one_paragraph = activeWorldSuggestion.value.description
  }
  ElMessage.success(`已采用世界建议：${activeWorldSuggestion.value.label}`)
}

function rotateTemplate() {
  templateIndex.value = (templateIndex.value + 1) % conceptTemplates.length
}

function rotateHook() {
  hookIndex.value = (hookIndex.value + 1) % hookSuggestions.length
}

function rotateWorldSuggestion() {
  worldSuggestionIndex.value = (worldSuggestionIndex.value + 1) % worldSuggestions.length
}

function resetDraft() {
  form.one_sentence = ''
  form.one_paragraph = ''
  form.genre_tags.splice(0, form.genre_tags.length)
  form.world_type = 'continental'
  reviewRequested.value = false
  ElMessage.info('已清空当前概念草稿，可重新填写')
}

function worldTypeLabel(value: ConceptData['world_type']) {
  switch (value) {
    case 'planar':
      return '位面/世界流'
    case 'interstellar':
      return '星际/宇宙流'
    case 'multi_layer':
      return '多层世界'
    default:
      return '大陆流'
  }
}
</script>

<style scoped>
.concept-page {
  display: grid;
  gap: var(--spacing-6);
  max-width: 1080px;
  margin: 0 auto;
  padding: 32px 24px 48px;
}

.meta-pill,
.guide-pill,
.structure-chip {
  display: inline-flex;
  align-items: center;
  min-height: 30px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 12px;
}

.guide-pill--muted {
  background: color-mix(in srgb, var(--color-surface-3) 84%, transparent);
}

.guide-grid,
.impact-grid {
  display: grid;
  gap: var(--spacing-4);
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.guide-card,
.impact-card {
  min-width: 0;
}

.guide-card__body,
.field-stack,
.concept-form,
.impact-copy {
  display: grid;
  gap: 12px;
}

.guide-pill-row,
.structure-hints,
.tag-area,
.tag-presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.guide-copy,
.field-hint,
.impact-copy,
.preset-label {
  margin: 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

.world-select {
  width: 240px;
}

.outline-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.outline-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-2) 84%, transparent);
}

.outline-card span {
  width: 24px;
  height: 24px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-accent-soft);
  color: var(--color-accent);
  font-size: 12px;
  font-weight: 700;
}

.outline-card p {
  margin: 0;
  color: var(--color-text-2);
  line-height: 1.5;
}

.concept-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--spacing-3);
}

.genre-tag {
  cursor: default;
}

.tag-input {
  width: 108px;
}

.preset-tag {
  cursor: pointer;
}

@media (max-width: 1080px) {
  .guide-grid,
  .impact-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .concept-page {
    padding: 24px 16px 40px;
  }

  .outline-grid {
    grid-template-columns: 1fr;
  }

  .concept-actions {
    flex-direction: column;
  }

  .world-select {
    width: 100%;
  }
}
</style>
