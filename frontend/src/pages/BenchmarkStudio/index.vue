<template>
  <div class="benchmark-page app-page-surface">
    <SystemPageHeader
      eyebrow="Benchmark Studio"
      title="对标分析与作者蒸馏工作台"
      description="在同一底座上管理项目级 benchmark 与作者级长期 Skill，既能做当前书对标，也能蒸馏可复用的作者创作能力。"
    >
      <template #meta>
        <span class="benchmark-pill">项目 {{ projectId }}</span>
        <span class="benchmark-pill">当前 Benchmark {{ currentProfile?.status === 'active' ? '已激活' : currentProfile ? '待激活' : '未生成' }}</span>
        <span class="benchmark-pill">当前 Skill {{ activeSkill?.application_mode ?? '未应用' }}</span>
        <span class="benchmark-pill">Snippet {{ currentProfile?.snippet_count ?? snippetItems.length }}</span>
      </template>
    </SystemPageHeader>

    <div class="benchmark-layout">
      <SystemCard
        class="composer-shell"
        title="上传参考文本"
        description="选择工作流、参考模式与目标平台，生成 benchmark profile 或作者 Skill。"
      >
        <template #actions>
          <SystemButton size="sm" variant="ghost" @click="addReference">新增文本</SystemButton>
        </template>

        <div class="meta-form">
          <label class="field compact-field">
            <span>工作流</span>
            <select v-model="jobType">
              <option value="project_benchmark">项目级对标</option>
              <option value="author_distillation">作者蒸馏 Skill</option>
            </select>
          </label>
          <label class="field compact-field">
            <span>模式</span>
            <select v-model="mode">
              <option value="single_work">单作品对标</option>
              <option value="multi_work">多作品对标</option>
              <option value="scene">场景对标</option>
            </select>
          </label>
          <label class="field compact-field">
            <span>目标平台</span>
            <input v-model="targetPlatform" type="text" placeholder="tomato / general" />
          </label>
          <label v-if="jobType === 'author_distillation'" class="field compact-field">
            <span>作者名</span>
            <input v-model="authorName" type="text" placeholder="同一作者名" />
          </label>
          <label v-if="jobType === 'author_distillation'" class="field compact-field">
            <span>Corpus Group</span>
            <input v-model="corpusGroup" type="text" placeholder="author_x_corpus" />
          </label>
          <label class="field compact-field">
            <span>章节分隔正则</span>
            <input v-model="chapterSep" type="text" placeholder="留空则使用默认章节规则" />
          </label>
        </div>

        <article v-for="(item, index) in references" :key="item.id" class="reference-card">
          <div class="reference-head">
            <h3>参考文本 {{ index + 1 }}</h3>
            <SystemButton v-if="references.length > 1" size="sm" variant="ghost" @click="removeReference(item.id)">删除</SystemButton>
          </div>
          <label class="field compact-field">
            <span>标题</span>
            <input v-model="item.title" type="text" placeholder="例如：参考作品 A" />
          </label>
          <div class="row-two">
            <label class="field compact-field">
              <span>作者</span>
              <input v-model="item.author_name" type="text" placeholder="可选" />
            </label>
            <label class="field compact-field">
              <span>文件名</span>
              <input v-model="item.file_name" type="text" placeholder="可选" />
            </label>
          </div>
          <label class="field">
            <span>正文</span>
            <textarea
              v-model="item.text"
              rows="7"
              placeholder="粘贴参考文本片段或章节内容。Phase 2 默认使用文本直贴模式完成 ingest。"
            />
          </label>
        </article>

        <div class="action-zone">
          <p class="hint-copy">
            {{ jobType === 'author_distillation'
              ? `作者蒸馏要求同作者或同一稳定 corpus_group，且至少 3 部作品。当前已填写 ${filledReferenceCount} 部。`
              : '项目级 benchmark 会优先服务当前书的局部约束与回归评分。' }}
          </p>
          <SystemButton variant="primary" size="lg" block :disabled="creating || !canSubmit" :loading="creating" @click="createBenchmark">
            {{ creating ? '生成中…' : submitLabel }}
          </SystemButton>
        </div>

        <section v-if="jobDetail" class="job-shell">
          <div class="section-head compact">
            <h2>Job 状态</h2>
            <span class="status-chip">{{ jobDetail.run.status }}</span>
          </div>
          <p class="job-copy">{{ jobDetail.message }}</p>
          <div class="step-stack">
            <div v-for="step in jobDetail.run.steps" :key="step.step_id" class="step-row">
              <strong>{{ step.step_index + 1 }}. {{ step.agent_name }}</strong>
              <span>{{ step.status }}</span>
            </div>
          </div>
        </section>
      </SystemCard>

      <main class="insight-column">
        <SystemCard class="insight-nav-card" tone="subtle">
          <div class="insight-nav">
            <SystemButton size="sm" :variant="insightPanel === 'profile' ? 'primary' : 'ghost'" @click="insightPanel = 'profile'">Benchmark Profile</SystemButton>
            <SystemButton size="sm" :variant="insightPanel === 'skill' ? 'primary' : 'ghost'" @click="insightPanel = 'skill'">Author Skill</SystemButton>
            <SystemButton size="sm" :variant="insightPanel === 'snippets' ? 'primary' : 'ghost'" @click="insightPanel = 'snippets'">Scene Anchors</SystemButton>
          </div>
          <p class="insight-nav-copy">
            {{ insightPanel === 'profile'
              ? '优先查看当前 benchmark profile 的基线与 trait 聚合。'
              : insightPanel === 'skill'
                ? '作者蒸馏 Skill 改为按需展开，避免与 Benchmark 详情同屏竞争。'
                : 'Scene Anchors 收纳到第三面板，仅在检查片段质量时展开。'
            }}
          </p>
        </SystemCard>

        <SystemCard
          v-if="insightPanel === 'profile'"
          class="profile-shell"
          :title="currentProfile?.profile_name || '等待生成 profile'"
          description="查看当前 benchmark profile 的状态、特征簇和人味基线。"
        >
          <template #actions>
            <SystemButton
              v-if="currentProfile && currentProfile.status !== 'active'"
              variant="primary"
              :disabled="activating"
              :loading="activating"
              @click="activateCurrentProfile"
            >
              {{ activating ? '激活中…' : '激活当前 Profile' }}
            </SystemButton>
          </template>

          <div v-if="currentProfile" class="profile-meta-grid">
            <div class="meta-box">
              <span>状态</span>
              <strong>{{ currentProfile.status }}</strong>
            </div>
            <div class="meta-box">
              <span>来源数</span>
              <strong>{{ currentProfile.source_ids.length }}</strong>
            </div>
            <div class="meta-box">
              <span>Snippet 数</span>
              <strong>{{ currentProfile.snippet_count }}</strong>
            </div>
            <div class="meta-box">
              <span>目标平台</span>
              <strong>{{ String(currentProfile.humanness_baseline.target_platform || 'general') }}</strong>
            </div>
          </div>
          <p v-else class="empty-copy">当前项目还没有生成 benchmark profile。</p>

          <div v-if="currentProfile" class="trait-columns">
            <section>
              <h3>Stable Traits</h3>
              <article v-for="trait in currentProfile.stable_traits" :key="trait.name" class="trait-card trait-stable">
                <strong>{{ trait.name }}</strong>
                <p>{{ trait.summary }}</p>
              </article>
            </section>
            <section>
              <h3>Conditional Traits</h3>
              <article v-for="trait in currentProfile.conditional_traits" :key="trait.name" class="trait-card trait-conditional">
                <strong>{{ trait.name }}</strong>
                <p>{{ trait.summary }}</p>
              </article>
              <p v-if="currentProfile.conditional_traits.length === 0" class="empty-copy">当前没有提取出场景条件 trait。</p>
            </section>
            <section>
              <h3>Anti Traits</h3>
              <article v-for="trait in currentProfile.anti_traits" :key="trait.name" class="trait-card trait-anti">
                <strong>{{ trait.name }}</strong>
                <p>{{ trait.summary }}</p>
              </article>
            </section>
          </div>

          <div v-if="currentProfile" class="baseline-grid">
            <div v-for="item in baselineItems" :key="item.label" class="baseline-card">
              <span>{{ item.label }}</span>
              <strong>{{ item.value }}</strong>
            </div>
          </div>
        </SystemCard>

        <SystemCard
          v-else-if="insightPanel === 'skill'"
          class="skill-shell"
          :title="currentSkill?.skill_name || '等待作者蒸馏 Skill'"
          description="管理作者长期 Skill，查看规则结构并应用到当前项目。"
        >
          <template #actions>
            <SystemButton size="sm" variant="ghost" @click="loadSkills">刷新 Skill 列表</SystemButton>
          </template>

          <div class="skill-layout">
            <div class="skill-list">
              <article
                v-for="skill in skillItems"
                :key="skill.skill_id"
                class="skill-card"
                :class="{ selected: currentSkill?.skill_id === skill.skill_id }"
                @click="openSkill(skill.skill_id)"
              >
                <div class="snippet-topline">
                  <strong>{{ skill.skill_name }}</strong>
                  <span class="scene-pill">{{ skill.application_mode || '未应用' }}</span>
                </div>
                <p class="skill-copy">{{ skill.author_name || '未标记作者' }} · 来源 {{ skill.source_ids.length }} 篇</p>
                <div class="snippet-metrics">
                  <small>stable {{ skill.stable_rules.length }}</small>
                  <small>scene {{ Object.keys(skill.scene_patterns || {}).length }}</small>
                  <small>origin {{ skill.origin_project_id }}</small>
                </div>
              </article>
              <p v-if="skillItems.length === 0" class="empty-copy">当前还没有可用的作者 Skill。</p>
            </div>

            <div class="skill-detail">
              <template v-if="currentSkill">
                <div class="profile-meta-grid">
                  <div class="meta-box">
                    <span>作者</span>
                    <strong>{{ currentSkill.author_name || '未标记' }}</strong>
                  </div>
                  <div class="meta-box">
                    <span>来源项目</span>
                    <strong>{{ currentSkill.origin_project_id }}</strong>
                  </div>
                  <div class="meta-box">
                    <span>当前模式</span>
                    <strong>{{ currentSkill.application_mode || '未应用' }}</strong>
                  </div>
                  <div class="meta-box">
                    <span>Hook 模式数</span>
                    <strong>{{ currentSkill.chapter_hook_patterns.length }}</strong>
                  </div>
                </div>

                <div class="apply-bar">
                  <label class="field compact-field mode-picker">
                    <span>应用模式</span>
                    <select v-model="skillMode">
                      <option value="guide">guide</option>
                      <option value="hybrid">hybrid</option>
                      <option value="strict">strict</option>
                    </select>
                  </label>
                  <SystemButton variant="primary" :disabled="applyingSkill" :loading="applyingSkill" @click="applyCurrentSkill">
                    {{ applyingSkill ? '应用中…' : '应用到当前项目' }}
                  </SystemButton>
                </div>

                <div class="trait-columns skill-traits">
                  <section>
                    <h3>Stable Rules</h3>
                    <article v-for="rule in currentSkill.stable_rules" :key="rule.name" class="trait-card trait-stable">
                      <strong>{{ rule.name }}</strong>
                      <p>{{ rule.summary }}</p>
                    </article>
                  </section>
                  <section>
                    <h3>Conditional Rules</h3>
                    <article v-for="rule in currentSkill.conditional_rules" :key="rule.name" class="trait-card trait-conditional">
                      <strong>{{ rule.name }}</strong>
                      <p>{{ rule.summary }}</p>
                    </article>
                    <p v-if="currentSkill.conditional_rules.length === 0" class="empty-copy">当前没有额外条件规则。</p>
                  </section>
                  <section>
                    <h3>Anti Rules</h3>
                    <article v-for="rule in currentSkill.anti_rules" :key="rule.name" class="trait-card trait-anti">
                      <strong>{{ rule.name }}</strong>
                      <p>{{ rule.summary }}</p>
                    </article>
                  </section>
                </div>
              </template>
              <p v-else class="empty-copy">生成作者蒸馏 job 后，可在这里查看 Skill 详情并应用到当前项目。</p>
            </div>
          </div>
        </SystemCard>

        <SystemCard
          v-else
          class="snippet-shell"
          title="Scene Anchors"
          description="按场景类型查看当前 profile 提取出的锚点片段和质量指标。"
        >
          <template #actions>
            <div class="snippet-controls">
              <select v-model="sceneFilter" @change="loadSnippets">
                <option value="">全部场景</option>
                <option value="battle">battle</option>
                <option value="emotion">emotion</option>
                <option value="reveal">reveal</option>
                <option value="daily">daily</option>
                <option value="ensemble">ensemble</option>
                <option value="general">general</option>
              </select>
              <SystemButton size="sm" variant="ghost" @click="loadSnippets">刷新</SystemButton>
            </div>
          </template>

          <div v-if="snippetItems.length > 0" class="snippet-grid">
            <article v-for="snippet in snippetItems" :key="snippet.snippet_id" class="snippet-card">
              <div class="snippet-topline">
                <span class="scene-pill">{{ snippet.scene_type }}</span>
                <span>章 {{ snippet.chapter ?? '-' }}</span>
              </div>
              <p class="snippet-text">{{ snippet.text }}</p>
              <div class="snippet-metrics">
                <small>anchor {{ formatScore(snippet.anchor_score) }}</small>
                <small>purity {{ formatScore(snippet.purity_score) }}</small>
                <small>distinct {{ formatScore(snippet.distinctiveness_score) }}</small>
                <small>{{ snippet.source_hit_verified ? 'source ok' : 'source miss' }}</small>
              </div>
            </article>
          </div>
          <p v-else class="empty-copy">当前没有可展示 snippets。生成 profile 后会自动刷新。</p>
        </SystemCard>
      </main>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useRoute } from 'vue-router'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'

import {
  benchmark,
  type AuthorSkillProfile,
  type BenchmarkJobDetailResponse,
  type BenchmarkJobType,
  type BenchmarkProfile,
  type BenchmarkSkillApplyMode,
  type BenchmarkSnippet,
  type BenchmarkSourceInput,
} from '@/api/benchmark'

type ReferenceDraft = BenchmarkSourceInput & { id: string }

const route = useRoute()
const projectId = computed(() => route.params.id as string)

const jobType = ref<BenchmarkJobType>('project_benchmark')
const mode = ref<'single_work' | 'multi_work' | 'scene'>('multi_work')
const targetPlatform = ref('tomato')
const chapterSep = ref('')
const authorName = ref('')
const corpusGroup = ref('')
const sceneFilter = ref('')
const creating = ref(false)
const activating = ref(false)
const applyingSkill = ref(false)
const currentProfile = ref<BenchmarkProfile | null>(null)
const currentSkill = ref<AuthorSkillProfile | null>(null)
const jobDetail = ref<BenchmarkJobDetailResponse | null>(null)
const snippetItems = ref<BenchmarkSnippet[]>([])
const skillItems = ref<AuthorSkillProfile[]>([])
const skillMode = ref<BenchmarkSkillApplyMode>('hybrid')
const insightPanel = ref<'profile' | 'skill' | 'snippets'>('profile')
const references = ref<ReferenceDraft[]>([
  createReferenceDraft(),
  createReferenceDraft(),
  createReferenceDraft(),
])

const AUTHOR_DISTILLATION_MIN_SOURCES = 3

const filledReferenceCount = computed(() =>
  references.value.filter((item) => item.title.trim() && item.text.trim()).length,
)

const canSubmit = computed(() =>
  filledReferenceCount.value > 0
  && (
    jobType.value !== 'author_distillation'
    || (
      filledReferenceCount.value >= AUTHOR_DISTILLATION_MIN_SOURCES
      && Boolean(authorName.value.trim() || corpusGroup.value.trim())
    )
  ),
)

const submitLabel = computed(() =>
  jobType.value === 'author_distillation' ? '生成 Author Skill' : '生成 Benchmark Profile',
)

const activeSkill = computed(() =>
  skillItems.value.find((item) => item.applied) ?? (currentSkill.value?.applied ? currentSkill.value : null),
)

const baselineItems = computed(() => {
  if (!currentProfile.value) return []
  const baseline = currentProfile.value.humanness_baseline
  return [
    { label: '平均句长', value: formatMetric(baseline.avg_sentence_length) },
    { label: '平均段长', value: formatMetric(baseline.avg_paragraph_length) },
    { label: '对白密度', value: formatRatio(baseline.dialogue_ratio) },
    { label: '省略号密度', value: formatRatio(baseline.ellipsis_density) },
  ]
})

function createReferenceDraft(): ReferenceDraft {
  return {
    id: crypto.randomUUID(),
    title: '',
    file_name: '',
    text: '',
    author_name: '',
    corpus_group: '',
    chapter_sep: '',
  }
}

function addReference() {
  references.value.push(createReferenceDraft())
}

function removeReference(id: string) {
  references.value = references.value.filter((item) => item.id !== id)
}

async function createBenchmark() {
  const payloadSources = references.value
    .filter((item) => item.title.trim() && item.text.trim())
    .map((item) => ({
      title: item.title.trim(),
      file_name: item.file_name?.trim() || '',
      text: item.text.trim(),
      author_name: item.author_name?.trim() || null,
      corpus_group: item.corpus_group?.trim() || '',
      chapter_sep: item.chapter_sep?.trim() || null,
    }))

  if (payloadSources.length === 0) {
    ElMessage.warning('至少需要填写一份标题和正文都完整的参考文本。')
    return
  }

  creating.value = true
  try {
    const createResp = await benchmark.createJob(projectId.value, {
      job_type: jobType.value,
      mode: mode.value,
      sources: payloadSources,
      chapter_sep: chapterSep.value.trim() || null,
      extract_snippets: true,
      target_platform: targetPlatform.value.trim() || null,
      author_name: authorName.value.trim() || null,
      corpus_group: corpusGroup.value.trim() || null,
    })
    const runId = createResp.data.run_id
    const detailResp = await benchmark.getJob(projectId.value, runId)
    jobDetail.value = detailResp.data
    if (jobType.value === 'author_distillation') {
      currentSkill.value = detailResp.data.author_skill ?? createResp.data.author_skill ?? null
      skillMode.value = currentSkill.value?.application_mode ?? 'hybrid'
      insightPanel.value = 'skill'
      ElMessage.success('Author skill 已生成。')
      await loadSkills()
    } else {
      currentProfile.value = detailResp.data.profile ?? createResp.data.profile
      snippetItems.value = detailResp.data.snippets
      insightPanel.value = 'profile'
      ElMessage.success('Benchmark profile 已生成。')
      await loadSnippets()
    }
  } finally {
    creating.value = false
  }
}

async function loadCurrentProfile() {
  const resp = await benchmark.getProfile(projectId.value)
  currentProfile.value = resp.data
}

async function loadSnippets() {
  const resp = await benchmark.listSnippets(projectId.value, {
    profile_id: currentProfile.value?.profile_id,
    scene_type: sceneFilter.value || undefined,
    limit: 24,
  })
  if (resp.data.profile) {
    currentProfile.value = resp.data.profile
  }
  snippetItems.value = resp.data.items
}

async function loadSkills() {
  const resp = await benchmark.listSkills(projectId.value, { limit: 24 })
  skillItems.value = resp.data.items
  if (resp.data.active_mode) {
    skillMode.value = resp.data.active_mode
  }

  const preferredSkillId = currentSkill.value?.skill_id ?? resp.data.active_skill_id ?? resp.data.items[0]?.skill_id
  if (!preferredSkillId) {
    currentSkill.value = null
    return
  }

  const matched = resp.data.items.find((item) => item.skill_id === preferredSkillId) ?? null
  currentSkill.value = matched
}

async function openSkill(skillId: string) {
  const resp = await benchmark.getSkill(projectId.value, skillId)
  currentSkill.value = resp.data
  skillMode.value = resp.data.application_mode ?? 'hybrid'
  insightPanel.value = 'skill'
}

async function applyCurrentSkill() {
  if (!currentSkill.value) return
  applyingSkill.value = true
  try {
    const resp = await benchmark.applySkill(projectId.value, currentSkill.value.skill_id, skillMode.value)
    currentSkill.value = resp.data.skill
    await loadSkills()
    ElMessage.success(resp.data.message)
  } finally {
    applyingSkill.value = false
  }
}

async function activateCurrentProfile() {
  if (!currentProfile.value) return
  activating.value = true
  try {
    const resp = await benchmark.activateProfile(projectId.value, currentProfile.value.profile_id)
    currentProfile.value = resp.data
    insightPanel.value = 'profile'
    await loadSnippets()
    ElMessage.success('当前 benchmark profile 已激活。')
  } finally {
    activating.value = false
  }
}

function formatMetric(value: unknown) {
  if (typeof value === 'number') return Number.isInteger(value) ? String(value) : value.toFixed(2)
  return '-'
}

function formatRatio(value: unknown) {
  if (typeof value === 'number') return `${(value * 100).toFixed(1)}%`
  return '-'
}

function formatScore(value: number) {
  return value.toFixed(2)
}

onMounted(async () => {
  await loadCurrentProfile()
  await loadSnippets()
  await loadSkills()
})
</script>

<style scoped>
.benchmark-page {
  display: grid;
  gap: var(--spacing-5);
  align-content: start;
}

.benchmark-pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  border: 1px solid var(--color-border-subtle);
  color: var(--color-text-2);
  font-size: 0.9rem;
}

.section-head h2 {
  margin: 0;
  color: var(--color-text-1);
}

.hero-copy,
.hint-copy,
.job-copy,
.empty-copy {
  color: var(--color-text-2);
  line-height: 1.7;
}

.meta-box,
.baseline-card {
  border-radius: 18px;
  background: color-mix(in srgb, var(--color-surface-2) 92%, transparent);
  border: 1px solid var(--color-border-subtle);
  padding: 16px;
}

.meta-box span,
.baseline-card span {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-3);
}

.meta-box strong,
.baseline-card strong {
  font-size: 18px;
  color: var(--color-text-1);
}

.benchmark-layout {
  display: grid;
  grid-template-columns: 420px minmax(0, 1fr);
  gap: 16px;
}

.insight-column {
  display: grid;
  gap: 16px;
  align-content: start;
}

.insight-nav-card :deep(.system-card__body) {
  gap: 10px;
}

.insight-nav {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.insight-nav-copy {
  margin: 0;
  color: var(--color-text-3);
  line-height: 1.6;
}

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  margin-bottom: 18px;
}

.section-head.compact {
  margin-bottom: 12px;
}

.meta-form,
.row-two,
.profile-meta-grid,
.baseline-grid {
  display: grid;
  gap: 12px;
}

.meta-form,
.profile-meta-grid,
.baseline-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.row-two {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.field {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.field span {
  font-size: 13px;
  font-weight: 700;
  color: var(--color-text-3);
}

.field input,
.field textarea,
.snippet-controls select,
.field select {
  width: 100%;
  border: 1px solid var(--color-border-default);
  border-radius: 14px;
  padding: 12px 14px;
  background: var(--color-surface-1);
  color: var(--color-text-1);
  resize: vertical;
}

.reference-card {
  margin-top: 16px;
  padding: 18px;
  border-radius: 20px;
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  border: 1px solid var(--color-border-subtle);
}

.reference-head,
.snippet-topline,
.snippet-metrics,
.step-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.reference-head h3,
.trait-columns h3 {
  margin: 0 0 8px;
  color: var(--color-text-1);
}

.action-zone {
  display: grid;
  gap: 14px;
  margin-top: 18px;
}

.job-shell {
  margin-top: 18px;
  padding: 18px;
  border-radius: 20px;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-2) 92%, transparent);
}

.status-chip,
.scene-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
  font-weight: 700;
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent-soft) 68%, var(--color-surface-1));
}

.step-stack,
.trait-columns {
  display: grid;
  gap: 14px;
}

.trait-columns {
  grid-template-columns: repeat(3, minmax(0, 1fr));
  margin-top: 18px;
}

.trait-card,
.snippet-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid var(--color-border-subtle);
}

.trait-stable {
  background: color-mix(in srgb, var(--color-accent-soft) 42%, var(--color-surface-1));
}

.trait-conditional {
  background: color-mix(in srgb, var(--color-warning-soft) 54%, var(--color-surface-1));
}

.trait-anti {
  background: color-mix(in srgb, var(--color-danger-soft) 48%, var(--color-surface-1));
}

.trait-card strong,
.snippet-card p {
  color: var(--color-text-1);
}

.snippet-controls {
  display: flex;
  gap: 10px;
  align-items: center;
}

.snippet-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.skill-layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 16px;
}

.skill-list {
  display: grid;
  gap: 12px;
  align-content: start;
}

.skill-card {
  padding: 16px;
  border-radius: 18px;
  border: 1px solid var(--color-border-subtle);
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
  cursor: pointer;
}

.skill-card.selected {
  border-color: color-mix(in srgb, var(--color-accent) 42%, transparent);
  box-shadow: var(--shadow-md);
}

.skill-detail {
  display: grid;
  gap: 16px;
}

.apply-bar {
  display: flex;
  gap: 12px;
  align-items: end;
}

.mode-picker {
  flex: 1;
  margin-bottom: 0;
}

.skill-copy {
  color: var(--color-text-2);
  line-height: 1.6;
}

.skill-traits {
  margin-top: 0;
}

.snippet-card {
  background: color-mix(in srgb, var(--color-surface-1) 94%, transparent);
}

.snippet-text {
  min-height: 112px;
  line-height: 1.7;
}

.snippet-metrics small {
  color: var(--color-text-2);
}

@media (max-width: 1180px) {
  .benchmark-layout {
    grid-template-columns: 1fr;
  }

  .skill-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 820px) {
  .meta-form,
  .row-two,
  .profile-meta-grid,
  .baseline-grid,
  .trait-columns,
  .snippet-grid {
    grid-template-columns: 1fr;
  }

  .apply-bar,
  .snippet-controls,
  .reference-head,
  .snippet-topline,
  .snippet-metrics,
  .step-row,
  .section-head {
    align-items: flex-start;
    flex-direction: column;
  }
}
</style>