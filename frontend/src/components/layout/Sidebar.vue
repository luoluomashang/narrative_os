<template>
  <aside class="sidebar" :class="{ 'sidebar--collapsed': isCollapsed }">
    <el-menu
      :default-active="activeMenu"
      :collapse="isCollapsed"
      :collapse-transition="false"
      class="sidebar-menu"
      router
    >
      <!-- 无项目上下文时：全局菜单 -->
      <template v-if="!store.projectId">
        <el-menu-item index="/projects">
          <el-icon><Folder /></el-icon>
          <template #title>全部项目</template>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <template #title>全局设置</template>
        </el-menu-item>
        <el-menu-item index="/plugins">
          <el-icon><Grid /></el-icon>
          <template #title>插件市场</template>
        </el-menu-item>
        <el-menu-item index="/cost">
          <el-icon><Coin /></el-icon>
          <template #title>消耗统计</template>
        </el-menu-item>
      </template>

      <!-- 有项目上下文时：完整创作流程菜单 -->
      <template v-else>
        <!-- 返回项目列表 -->
        <el-menu-item index="/projects">
          <el-icon><ArrowLeft /></el-icon>
          <template #title>全部项目</template>
        </el-menu-item>

        <!-- 项目主页 -->
        <el-menu-item :index="`/project/${store.projectId}`">
          <el-icon><House /></el-icon>
          <template #title>项目主页</template>
        </el-menu-item>

        <!-- 创作工作流 -->
        <el-sub-menu index="create">
          <template #title>
            <el-icon><Edit /></el-icon>
            <span>创作工作流</span>
          </template>
          <el-menu-item :index="`/project/${store.projectId}/worldbuilder`">
            <el-icon><Location /></el-icon>世界构建
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/concept`">
            <el-icon><Memo /></el-icon>故事概念
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/plot`">
            <el-icon><Connection /></el-icon>情节画布
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/write`">
            <el-icon><DocumentAdd /></el-icon>章节撰写
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/trpg`">
            <el-icon><Promotion /></el-icon>TRPG 互动
          </el-menu-item>
        </el-sub-menu>

        <!-- 数据管理 -->
        <el-sub-menu index="data">
          <template #title>
            <el-icon><DataAnalysis /></el-icon>
            <span>数据管理</span>
          </template>
          <el-menu-item :index="`/project/${store.projectId}/characters`">
            <el-icon><User /></el-icon>角色矩阵
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/memory`">
            <el-icon><Notebook /></el-icon>记忆系统
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/chapters`">
            <el-icon><Document /></el-icon>章节管理
          </el-menu-item>
        </el-sub-menu>

        <!-- 质量工具 -->
        <el-sub-menu index="tools">
          <template #title>
            <el-icon><Tools /></el-icon>
            <span>质量工具</span>
          </template>
          <el-menu-item :index="`/project/${store.projectId}/metrics`">
            <el-icon><TrendCharts /></el-icon>质量仪表盘
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/style`">
            <el-icon><MagicStick /></el-icon>风格控制台
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/check`">
            <el-icon><Checked /></el-icon>一致性检查
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/humanize`">
            <el-icon><StarFilled /></el-icon>去 AI 痕迹
          </el-menu-item>
          <el-menu-item :index="`/project/${store.projectId}/agents`">
            <el-icon><Cpu /></el-icon>Agent 工坊
          </el-menu-item>
        </el-sub-menu>

        <!-- 全局 -->
        <el-divider />
        <el-menu-item :index="`/project/${store.projectId}/settings`">
          <el-icon><Setting /></el-icon>
          <template #title>项目设置</template>
        </el-menu-item>
        <el-menu-item index="/cost">
          <el-icon><Coin /></el-icon>
          <template #title>消耗统计</template>
        </el-menu-item>
        <el-menu-item index="/plugins">
          <el-icon><Grid /></el-icon>
          <template #title>插件市场</template>
        </el-menu-item>
      </template>
    </el-menu>

    <!-- 收起/展开按钮 -->
    <button class="collapse-btn" @click="toggleCollapse">
      {{ isCollapsed ? '›' : '‹' }}
    </button>
  </aside>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  ArrowLeft,
  Checked,
  Coin,
  Connection,
  Cpu,
  DataAnalysis,
  Document,
  DocumentAdd,
  Edit,
  Folder,
  Grid,
  House,
  Location,
  MagicStick,
  Memo,
  Notebook,
  Promotion,
  Setting,
  StarFilled,
  Tools,
  TrendCharts,
  User,
} from '@element-plus/icons-vue'
import { useProjectStore } from '@/stores/projectStore'

const route = useRoute()
const store = useProjectStore()

// 收起状态持久化
const _storedCollapsed = localStorage.getItem('sidebar_collapsed')
const isCollapsed = ref(_storedCollapsed === 'true')

function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  localStorage.setItem('sidebar_collapsed', String(isCollapsed.value))
}

const activeMenu = computed(() => route.path)
</script>

<style scoped>
/* 透明背景覆盖 Element Plus 默认 */
:deep(.el-menu) {
  background: transparent;
}

:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  color: var(--color-text-secondary) !important;
}

:deep(.el-menu-item.is-active) {
  color: var(--el-color-primary) !important;
  background: var(--color-surface-l2) !important;
}

:deep(.el-menu-item:hover),
:deep(.el-sub-menu__title:hover) {
  background: var(--color-surface-l2) !important;
  color: var(--color-text-primary) !important;
}

:deep(.el-divider) {
  margin: 4px 12px;
  border-color: var(--color-surface-l2);
}

.collapse-btn {
  background: transparent;
  border: none;
  border-top: 1px solid var(--color-surface-l2);
  color: var(--color-text-secondary);
  padding: 8px;
  cursor: pointer;
  font-size: 18px;
  text-align: center;
  transition: color 150ms;
  width: 100%;
}
.collapse-btn:hover {
  color: var(--color-text-primary);
}
</style>

