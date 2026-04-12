import { createRouter, createWebHistory } from 'vue-router'
import { useProjectStore } from '@/stores/projectStore'

const routes = [
  // 默认重定向到项目列表
  { path: '/', redirect: '/projects' },

  // 全局页面（无需项目上下文）
  {
    path: '/projects',
    component: () => import('@/pages/ProjectManager/index.vue'),
    meta: { title: '项目列表' },
  },
  {
    path: '/settings',
    component: () => import('@/pages/Settings/index.vue'),
    meta: { title: '全局设置' },
  },
  {
    path: '/plugins',
    component: () => import('@/pages/PluginMarketplace/index.vue'),
    meta: { title: '插件市场' },
  },
  {
    path: '/cost',
    component: () => import('@/pages/CostDashboard/index.vue'),
    meta: { title: '消耗统计' },
  },

  // 项目级页面（需要项目上下文）
  {
    path: '/project/:id',
    component: () => import('@/pages/Project/index.vue'),
    meta: { title: '项目主页', requiresProject: true },
  },
  {
    path: '/project/:id/worldbuilder',
    component: () => import('@/pages/WorldBuilder/index.vue'),
    meta: { title: '世界构建', requiresProject: true },
  },
  {
    path: '/project/:id/concept',
    component: () => import('@/pages/StoryConceptPage/index.vue'),
    meta: { title: '故事概念', requiresProject: true },
  },
  {
    path: '/project/:id/plot',
    component: () => import('@/pages/PlotCanvas/index.vue'),
    meta: { title: '剧情画布', requiresProject: true },
  },
  {
    path: '/project/:id/characters',
    component: () => import('@/pages/CharacterMatrix/index.vue'),
    meta: { title: '角色矩阵', requiresProject: true },
  },
  {
    path: '/project/:id/write',
    component: () => import('@/pages/Writing/index.vue'),
    meta: { title: '章节撰写', requiresProject: true },
  },
  {
    path: '/project/:id/trpg',
    component: () => import('@/pages/TRPGPanel/index.vue'),
    meta: { title: 'TRPG 互动', requiresProject: true },
  },
  {
    path: '/project/:id/memory',
    component: () => import('@/pages/MemorySystem/index.vue'),
    meta: { title: '记忆系统', requiresProject: true },
  },
  {
    path: '/project/:id/memory-search',
    component: () => import('@/pages/MemorySearch/index.vue'),
    meta: { title: '记忆检索', requiresProject: true },
  },
  {
    path: '/project/:id/metrics',
    component: () => import('@/pages/MetricsDashboard/index.vue'),
    meta: { title: '质量仪表盘', requiresProject: true },
  },
  {
    path: '/project/:id/trace',
    component: () => import('@/pages/TraceInspectorPage/index.vue'),
    meta: { title: '执行链路', requiresProject: true },
  },
  {
    path: '/project/:id/style',
    component: () => import('@/pages/StyleConsole/index.vue'),
    meta: { title: '风格控制台', requiresProject: true },
  },
  {
    path: '/project/:id/check',
    component: () => import('@/pages/ConsistencyChecker/index.vue'),
    meta: { title: '一致性检查', requiresProject: true },
  },
  {
    path: '/project/:id/humanize',
    component: () => import('@/pages/HumanizeStudio/index.vue'),
    meta: { title: '去 AI 痕迹', requiresProject: true },
  },
  {
    path: '/project/:id/agents',
    component: () => import('@/pages/AgentWorkshop/index.vue'),
    meta: { title: 'Agent 工坊', requiresProject: true },
  },
  {
    path: '/project/:id/chapters',
    component: () => import('@/pages/ChapterManager/index.vue'),
    meta: { title: '章节管理', requiresProject: true },
  },
  {
    path: '/project/:id/settings',
    component: () => import('@/pages/Settings/index.vue'),
    meta: { title: '项目设置', requiresProject: true },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() {
    return { top: 0 }
  },
})

// 路由守卫：从路由参数自动同步 projectStore
router.beforeEach(async (to) => {
  const projectId = to.params.id as string | undefined
  if (projectId) {
    try {
      const store = useProjectStore()
      if (store.projectId !== projectId) {
        store.setProjectId(projectId)
        try {
          await store.loadProjectInfo(projectId)
        } catch {
          // 项目不存在时跳转到项目列表
          return '/projects'
        }
      }
    } catch {
      // pinia 尚未初始化时忽略
    }
  }
})

export default router

