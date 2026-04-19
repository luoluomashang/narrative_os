<template>
  <div class="plugin-page">
    <SystemPageHeader
      eyebrow="Plugin Marketplace"
      title="插件市场"
      description="统一管理风格增强、后处理、校验与导出能力，保持工作台能力边界清晰。"
    >
      <template #meta>
        <span class="plugin-page__pill">已启用 {{ plugins.filter((plugin) => plugin.enabled).length }} 个插件</span>
      </template>
    </SystemPageHeader>

    <SystemSection>
      <template #actions>
        <div class="plugin-filter">
          <SystemButton
            v-for="cat in categories"
            :key="cat"
            size="sm"
            :variant="activeCategory === cat ? 'secondary' : 'ghost'"
            @click="activeCategory = cat"
          >
            {{ cat }}
          </SystemButton>
        </div>
      </template>

      <div v-if="loading" class="plugin-loading">
        <SystemSkeleton v-for="index in 3" :key="index" card show-header :rows="3" />
      </div>

      <SystemEmpty
        v-else-if="filteredPlugins.length === 0"
        title="当前分类暂无插件"
        description="切换筛选分类，或等待插件服务恢复后重新拉取列表。"
      >
        <template #action>
          <SystemButton @click="activeCategory = '全部'">查看全部插件</SystemButton>
        </template>
      </SystemEmpty>

      <div class="plugin-grid" v-else>
        <SystemCard
          v-for="plugin in filteredPlugins"
          :key="plugin.id"
          class="plugin-card"
          :class="{ enabled: plugin.enabled }"
          interactive
          @click="openPlugin(plugin)"
        >
          <div class="pc-header">
            <span class="pc-name">{{ plugin.name }}</span>
            <span class="pc-state" :class="{ 'pc-state--enabled': plugin.enabled }">
              {{ plugin.enabled ? '已启用' : '未启用' }}
            </span>
          </div>
          <div class="pc-desc">{{ plugin.description }}</div>
          <div class="pc-meta">
            <el-tag size="small" type="info">v{{ plugin.version }}</el-tag>
            <el-tag v-for="tag in plugin.tags" :key="tag" size="small">{{ tag }}</el-tag>
          </div>
          <div class="pc-footer">
            <div class="pc-author">by {{ plugin.author }}</div>
            <SystemButton size="sm" variant="secondary" @click.stop="openPlugin(plugin)">查看详情</SystemButton>
          </div>
        </SystemCard>
      </div>
    </SystemSection>

    <SystemDrawer
      v-model="pluginDrawerOpen"
      :title="selectedPlugin?.name || '插件详情'"
      description="插件详情与启用动作统一进入抽屉，避免浏览列表同时承载过多直接操作。"
      size="420px"
    >
      <div v-if="selectedPlugin" class="plugin-drawer">
        <SystemCard tone="subtle" :title="selectedPlugin.name" :description="selectedPlugin.description">
          <div class="pc-meta">
            <el-tag size="small" type="info">v{{ selectedPlugin.version }}</el-tag>
            <el-tag size="small">{{ selectedPlugin.category }}</el-tag>
            <el-tag v-for="tag in selectedPlugin.tags" :key="tag" size="small">{{ tag }}</el-tag>
          </div>
          <p class="plugin-drawer__desc">作者：{{ selectedPlugin.author }}</p>
        </SystemCard>

        <SystemCard title="启用状态" tone="subtle">
          <p class="plugin-drawer__desc">
            {{ selectedPlugin.enabled ? '当前插件已启用，会在对应工作流中提供能力支持。' : '当前插件未启用，需要手动打开后才会参与工作流。' }}
          </p>
          <template #actions>
            <el-switch
              :model-value="selectedPlugin.enabled"
              @change="handleSelectedPluginToggle"
            />
          </template>
        </SystemCard>
      </div>
    </SystemDrawer>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import axios from 'axios'
import SystemButton from '@/components/system/SystemButton.vue'
import SystemCard from '@/components/system/SystemCard.vue'
import SystemDrawer from '@/components/system/SystemDrawer.vue'
import SystemEmpty from '@/components/system/SystemEmpty.vue'
import SystemPageHeader from '@/components/system/SystemPageHeader.vue'
import SystemSection from '@/components/system/SystemSection.vue'
import SystemSkeleton from '@/components/system/SystemSkeleton.vue'

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
const pluginDrawerOpen = ref(false)
const selectedPlugin = ref<Plugin | null>(null)

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

async function setPluginEnabled(plugin: Plugin, nextEnabled: boolean) {
  const prev = plugin.enabled
  plugin.enabled = nextEnabled
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

function handleSelectedPluginToggle(value: boolean | string | number) {
  if (!selectedPlugin.value) {
    return
  }
  void setPluginEnabled(selectedPlugin.value, Boolean(value))
}

function openPlugin(plugin: Plugin) {
  selectedPlugin.value = plugin
  pluginDrawerOpen.value = true
}

onMounted(loadPlugins)

watch(pluginDrawerOpen, (open) => {
  if (!open) {
    selectedPlugin.value = null
  }
})
</script>

<style scoped>
.plugin-page {
  display: grid;
  gap: 16px;
  height: 100%;
  overflow: hidden;
  padding: var(--spacing-md);
  box-sizing: border-box;
}
.plugin-page__pill {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-2);
  font-size: 0.9rem;
}
.plugin-filter { display: flex; gap: 4px; }

.plugin-loading {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--spacing-md);
}

.plugin-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
  overflow-y: auto;
  align-content: start;
}

.plugin-card {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}
.plugin-card.enabled { border-color: var(--color-success); }

.pc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.pc-name { font-size: 14px; font-weight: 600; }

.pc-state {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 10px;
  border-radius: var(--radius-pill);
  background: var(--color-surface-2);
  color: var(--color-text-3);
  font-size: 12px;
  font-weight: 700;
}

.pc-state--enabled {
  background: var(--color-success-soft);
  color: var(--color-success);
}

.pc-desc { font-size: 13px; color: var(--color-text-secondary); flex: 1; }
.pc-meta { display: flex; flex-wrap: wrap; gap: 4px; }
.pc-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.pc-author { font-size: var(--text-caption); color: var(--color-text-secondary); }

.plugin-drawer {
  display: grid;
  gap: 14px;
}

.plugin-drawer__desc {
  margin: 0;
  color: var(--color-text-2);
  line-height: 1.6;
}

@media (max-width: 1080px) {
  .plugin-loading,
  .plugin-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .plugin-page {
    padding: 16px;
  }

  .plugin-filter {
    flex-wrap: wrap;
  }

  .plugin-loading,
  .plugin-grid {
    grid-template-columns: 1fr;
  }

  .pc-footer {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
