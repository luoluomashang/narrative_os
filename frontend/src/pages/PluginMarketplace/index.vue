<template>
  <div class="plugin-page">
    <div class="plugin-header">
      <span class="plugin-title">插件市场</span>
      <div class="plugin-filter">
        <button
          v-for="cat in categories"
          :key="cat"
          class="cat-btn"
          :class="{ active: activeCategory === cat }"
          @click="activeCategory = cat"
        >{{ cat }}</button>
      </div>
    </div>

    <div v-if="loading" class="plugin-loading">
      <el-skeleton :rows="3" animated />
    </div>

    <el-empty v-else-if="filteredPlugins.length === 0" description="暂无插件" />

    <div class="plugin-grid" v-else>
      <el-card
        v-for="plugin in filteredPlugins"
        :key="plugin.id"
        class="plugin-card"
        :class="{ enabled: plugin.enabled }"
        shadow="hover"
      >
        <div class="pc-header">
          <span class="pc-name">{{ plugin.name }}</span>
          <el-switch v-model="plugin.enabled" @change="() => togglePlugin(plugin)" />
        </div>
        <div class="pc-desc">{{ plugin.description }}</div>
        <div class="pc-meta">
          <el-tag size="small" type="info">v{{ plugin.version }}</el-tag>
          <el-tag v-for="tag in plugin.tags" :key="tag" size="small">{{ tag }}</el-tag>
        </div>
        <div class="pc-author">by {{ plugin.author }}</div>
      </el-card>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import axios from 'axios'

interface Plugin {
  id: string
  name: string
  description: string
  version: string
  author: string
  tags: string[]
  category: string
  enabled: boolean
}

const loading = ref(true)
const plugins = ref<Plugin[]>([])
const categories = ['全部', '风格', '后处理', '校验', '输出']
const activeCategory = ref('全部')

const filteredPlugins = computed(() =>
  activeCategory.value === '全部'
    ? plugins.value
    : plugins.value.filter(p => p.category === activeCategory.value)
)

async function loadPlugins() {
  loading.value = true
  try {
    const res = await axios.get('/api/plugins')
    plugins.value = Array.isArray(res.data) ? res.data : []
  } catch {
    // demo data
    plugins.value = [
      { id: 'humanizer', name: '去 AI 痕迹', description: '检测并软化 AI 写作模式', version: '1.2.0', author: 'system', tags: ['NLP'], category: '后处理', enabled: true },
      { id: 'consistency', name: '一致性检查器', description: '语义级角色与情节检查', version: '2.0.1', author: 'system', tags: ['LLM'], category: '校验', enabled: true },
      { id: 'style', name: '风格引擎', description: '5维风格参数提取与应用', version: '1.0.5', author: 'system', tags: ['NLP'], category: '风格', enabled: false },
      { id: 'export_epub', name: 'EPUB 导出', description: '导出为标准 EPUB 格式', version: '0.9.3', author: 'community', tags: ['导出'], category: '输出', enabled: false },
      { id: 'sentiment', name: '情绪分析', description: '章节情绪曲线可视化', version: '1.1.0', author: 'community', tags: ['分析'], category: '校验', enabled: false },
    ]
  } finally {
    loading.value = false
  }
}

async function togglePlugin(plugin: Plugin) {
  const prev = plugin.enabled
  try {
    const res = await axios.post(`/api/plugins/${plugin.id}/toggle`)
    if (res.data && typeof res.data.enabled === 'boolean') {
      plugin.enabled = res.data.enabled
    }
  } catch {
    // Rollback on failure
    plugin.enabled = prev
  }
}

onMounted(loadPlugins)
</script>

<style scoped>
.plugin-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  padding: var(--spacing-md);
  gap: var(--spacing-md);
  box-sizing: border-box;
}
.plugin-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}
.plugin-title { font-size: var(--text-h2); font-weight: var(--weight-h2); }
.plugin-filter { display: flex; gap: 4px; }
.cat-btn {
  background: var(--color-surface-l1);
  border: 1px solid var(--color-surface-l2);
  border-radius: var(--radius-btn);
  color: var(--color-text-primary);
  padding: 3px 10px;
  font-size: var(--text-caption);
  cursor: pointer;
  transition: background 150ms;
}
.cat-btn.active { background: var(--color-ai-active); color: var(--color-base); border-color: var(--color-ai-active); }

.plugin-loading { text-align: center; color: var(--color-text-secondary); font-size: 14px; margin-top: var(--spacing-xl); }

/* Grid */
.plugin-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  overflow-y: auto;
  align-content: start;
}

/* Plugin card */
.plugin-card {
  background: var(--color-surface-l1);
  border-radius: var(--radius-card);
  border: 1px solid var(--color-surface-l2);
  padding: var(--spacing-md);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
  transition: border-color 200ms;
}
.plugin-card.enabled { border-color: var(--color-success); }

.pc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pc-name { font-size: 14px; font-weight: 600; }

.pc-toggle {
  width: 36px;
  height: 20px;
  background: var(--color-surface-l2);
  border-radius: 10px;
  position: relative;
  cursor: pointer;
  transition: background 200ms;
  flex-shrink: 0;
}
.pc-toggle.on { background: var(--color-success); }
.pc-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 16px;
  height: 16px;
  background: var(--color-text-primary);
  border-radius: 50%;
  transition: transform 200ms;
}
.pc-toggle.on .pc-thumb { transform: translateX(16px); }

.pc-desc { font-size: 13px; color: var(--color-text-secondary); flex: 1; }
.pc-meta { display: flex; flex-wrap: wrap; gap: 4px; }
.pc-author { font-size: var(--text-caption); color: var(--color-text-secondary); }
</style>
