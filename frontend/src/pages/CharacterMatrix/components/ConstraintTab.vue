<template>
  <div class="constraint-tab">
    <!-- Constraint list -->
    <div class="section-title">行为约束列表</div>
    <div v-if="!localConstraints.length" class="empty-hint">暂无约束，点击下方"+ 添加约束"</div>
    <div v-for="(c, idx) in localConstraints" :key="idx" class="constraint-item">
      <div class="constraint-main">
        <span class="constraint-rule">{{ c.rule }}</span>
        <span class="constraint-badge" :class="c.severity">{{ c.severity }}</span>
        <button class="constraint-del" @click="removeConstraint(idx)">×</button>
      </div>
      <div v-if="c.context" class="constraint-context">{{ c.context }}</div>
    </div>

    <!-- Add constraint inline form -->
    <div class="add-constraint">
      <div class="add-constraint-row">
        <el-input v-model="newRule" placeholder="约束规则，如：不能主动认输" size="small" />
        <el-select v-model="newSeverity" size="small" style="width: 100px">
          <el-option label="hard" value="hard" />
          <el-option label="soft" value="soft" />
        </el-select>
      </div>
      <div class="add-constraint-row">
        <el-input v-model="newContext" placeholder="上下文（可选），如：战斗场景" size="small" />
        <el-button size="small" @click="addConstraint">+ 添加约束</el-button>
      </div>
    </div>

    <!-- Real-time test -->
    <div class="test-section">
      <div class="section-title">实时行为测试</div>
      <div class="test-row">
        <el-input v-model="testAction" placeholder="输入一段行为描述..." size="small" />
        <el-button size="small" type="primary" @click="runTest">测试</el-button>
      </div>
      <div v-if="testResult !== null" class="test-result" :class="testResult.length ? 'violation' : 'pass'">
        <template v-if="testResult.length">
          <div v-for="(v, i) in testResult" :key="i">❌ {{ v }}</div>
        </template>
        <template v-else>✅ 通过，无约束违反</template>
      </div>
    </div>

    <!-- Save button -->
    <div class="constraint-actions">
      <el-button type="primary" :loading="loading" @click="handleSave">保存</el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { CharacterDetail, BehaviorConstraintDetail } from '@/types/api'

const props = defineProps<{
  model: CharacterDetail
  loading: boolean
}>()

const emit = defineEmits<{
  (e: 'save', constraints: BehaviorConstraintDetail[]): void
}>()

const localConstraints = ref<BehaviorConstraintDetail[]>([])
const newRule = ref('')
const newSeverity = ref<'hard' | 'soft'>('hard')
const newContext = ref('')
const testAction = ref('')
const testResult = ref<string[] | null>(null)

watch(() => props.model, (m) => {
  if (m) {
    localConstraints.value = (m.behavior_constraints ?? []).map((c: BehaviorConstraintDetail | string) => {
      if (typeof c === 'string') return { rule: c, severity: 'soft' as const, context: '' }
      return { ...c }
    })
  }
}, { immediate: true })

function addConstraint() {
  if (!newRule.value.trim()) return
  localConstraints.value.push({
    rule: newRule.value.trim(),
    severity: newSeverity.value,
    context: newContext.value.trim(),
  })
  newRule.value = ''
  newContext.value = ''
}

function removeConstraint(idx: number) {
  localConstraints.value.splice(idx, 1)
}

function localCheckConstraint(action: string, constraints: BehaviorConstraintDetail[]): string[] {
  const violations: string[] = []
  for (const c of constraints) {
    // 移除否定词后，提取关键词
    const stripped = c.rule.replace(/不能|必须|不得|不可|禁止|严禁|不要|不/g, '').trim()
    if (!stripped) continue
    // 按标点/空格拆分
    const tokens = stripped.split(/[、，,\s]+/).filter((k: string) => k.length >= 2)
    // 对每个 token 额外生成 2 字子串（适配中文语义匹配）
    const keywords: string[] = []
    for (const t of tokens.length ? tokens : [stripped]) {
      keywords.push(t)
      if (t.length > 2) {
        for (let i = 0; i <= t.length - 2; i++) {
          keywords.push(t.slice(i, i + 2))
        }
      }
    }
    const hit = keywords.some(kw => action.includes(kw))
    if (hit) {
      violations.push(`违反约束「${c.rule}」(${c.severity})`)
    }
  }
  return violations
}

function runTest() {
  if (!testAction.value.trim()) return
  testResult.value = localCheckConstraint(testAction.value, localConstraints.value)
}

function handleSave() {
  emit('save', [...localConstraints.value])
}
</script>

<style scoped>
.constraint-tab { padding: 4px 0; }
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}
.empty-hint {
  color: var(--color-text-secondary);
  font-size: 13px;
  padding: 12px 0;
}
.constraint-item {
  padding: 8px 10px;
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  margin-bottom: 6px;
}
.constraint-main {
  display: flex;
  align-items: center;
  gap: 8px;
}
.constraint-rule { flex: 1; font-size: 13px; color: var(--color-text-primary); }
.constraint-badge {
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
}
.constraint-badge.hard { background: var(--color-danger-soft); color: var(--color-danger); }
.constraint-badge.soft { background: var(--color-warning-soft); color: var(--color-warning); }
.constraint-del {
  background: none;
  border: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
  padding: 0 4px;
}
.constraint-del:hover { color: var(--color-danger); }
.constraint-context {
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 4px;
}
.add-constraint {
  margin: 12px 0;
  padding: 10px;
  border: 1px dashed var(--color-surface-l2);
  border-radius: var(--radius-btn);
}
.add-constraint-row {
  display: flex;
  gap: 8px;
  margin-bottom: 6px;
}
.add-constraint-row:last-child { margin-bottom: 0; }
.test-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
.test-row {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.test-result {
  padding: 8px 12px;
  border-radius: var(--radius-btn);
  font-size: 13px;
}
.test-result.pass { background: var(--color-success-soft); color: var(--color-success); }
.test-result.violation { background: var(--color-danger-soft); color: var(--color-danger); }
.constraint-actions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-surface-l2);
}
</style>
