export type ShellWorkspaceId = 'overview' | 'creation' | 'asset' | 'diagnostic'

export interface ShellNavigationItem {
  id: string
  label: string
  description: string
  segment?: string
}

export interface ShellWorkspace {
  id: ShellWorkspaceId
  label: string
  description: string
  icon: 'House' | 'EditPen' | 'Collection' | 'DataAnalysis'
  items: ShellNavigationItem[]
}

export interface ShellPageDescriptor {
  workspaceId: ShellWorkspaceId | null
  itemId: string | null
  title: string
  description: string
}

const creationItems: ShellNavigationItem[] = [
  { id: 'worldbuilder', label: '世界构建', description: '管理世界节点、关系与发布状态。', segment: 'worldbuilder' },
  { id: 'concept', label: '故事概念', description: '沉淀故事一句话与一段式概念。', segment: 'concept' },
  { id: 'plot', label: '剧情画布', description: '组织情节结构、体量目标与关键节点。', segment: 'plot' },
  { id: 'write', label: '章节撰写', description: '进入章节生成、预检查与发布工作流。', segment: 'write' },
  { id: 'trpg', label: 'TRPG 互动', description: '管理会话状态、回合推进与干预动作。', segment: 'trpg' },
]

const assetItems: ShellNavigationItem[] = [
  { id: 'characters', label: '角色矩阵', description: '查看和维护角色四层状态与关系。', segment: 'characters' },
  { id: 'memory', label: '记忆系统', description: '浏览短中长期记忆快照与结构。', segment: 'memory' },
  { id: 'memory-search', label: '记忆检索', description: '执行检索并回看来源命中。', segment: 'memory-search' },
  { id: 'chapters', label: '章节管理', description: '管理章节列表、导出与归档。', segment: 'chapters' },
]

const diagnosticItems: ShellNavigationItem[] = [
  { id: 'benchmark', label: 'Benchmark', description: '运行评测任务并查看基准结果。', segment: 'benchmark' },
  { id: 'metrics', label: '质量仪表盘', description: '查看质量维度、波形与警告摘要。', segment: 'metrics' },
  { id: 'style', label: '风格控制台', description: '管理风格片段、命中率与策略。', segment: 'style' },
  { id: 'check', label: '一致性检查', description: '检查文本和设定之间的一致性问题。', segment: 'check' },
  { id: 'humanize', label: '去 AI 痕迹', description: '执行文本去模板化与风格收敛。', segment: 'humanize' },
  { id: 'agents', label: 'Agent 工坊', description: '查看 Agent 流程、泳道与执行状态。', segment: 'agents' },
  { id: 'trace', label: '执行链路', description: '检查调用轨迹、步骤与日志。', segment: 'trace' },
]

export const projectWorkspaces: ShellWorkspace[] = [
  {
    id: 'overview',
    label: '总览',
    description: '回到项目主页，聚焦整体进度、阻塞项和下一步动作。',
    icon: 'House',
    items: [
      { id: 'project-home', label: '项目主页', description: '查看项目驾驶舱与当前状态。' },
      { id: 'project-settings', label: '项目设置', description: '调整当前项目的生成参数、Prompt 覆盖与协同配置。', segment: 'settings' },
    ],
  },
  {
    id: 'creation',
    label: '创作',
    description: '进入世界、概念、情节、写作与互动等核心工作台。',
    icon: 'EditPen',
    items: creationItems,
  },
  {
    id: 'asset',
    label: '资产',
    description: '聚合角色、章节与记忆等可维护资产。',
    icon: 'Collection',
    items: assetItems,
  },
  {
    id: 'diagnostic',
    label: '诊断',
    description: '集中处理评测、质量、风格与链路诊断。',
    icon: 'DataAnalysis',
    items: diagnosticItems,
  },
]

export const globalNavigation: ShellNavigationItem[] = [
  { id: 'projects', label: '全部项目', description: '查看、创建和切换项目。', segment: 'projects' },
  { id: 'settings', label: '全局设置', description: '调整模型、代理与系统级配置。', segment: 'settings' },
  { id: 'plugins', label: '插件市场', description: '查看插件能力与启用状态。', segment: 'plugins' },
  { id: 'cost', label: '消耗统计', description: '查看 token 和成本使用情况。', segment: 'cost' },
]

const workspaceBySegment: Record<string, ShellWorkspaceId> = {
  '': 'overview',
  settings: 'overview',
  worldbuilder: 'creation',
  concept: 'creation',
  plot: 'creation',
  write: 'creation',
  trpg: 'creation',
  characters: 'asset',
  memory: 'asset',
  'memory-search': 'asset',
  chapters: 'asset',
  benchmark: 'diagnostic',
  metrics: 'diagnostic',
  style: 'diagnostic',
  check: 'diagnostic',
  humanize: 'diagnostic',
  agents: 'diagnostic',
  trace: 'diagnostic',
}

export function buildProjectPath(projectId: string, segment?: string) {
  return segment ? `/project/${projectId}/${segment}` : `/project/${projectId}`
}

export function getGlobalPath(item: ShellNavigationItem) {
  return item.segment ? `/${item.segment}` : '/projects'
}

export function getProjectWorkspace(workspaceId: ShellWorkspaceId | null) {
  return projectWorkspaces.find((workspace) => workspace.id === workspaceId) ?? null
}

export function getWorkspaceIdFromPath(path: string): ShellWorkspaceId | null {
  if (!path.startsWith('/project/')) return null
  const segments = path.split('/').filter(Boolean)
  const routeSegment = segments[2] ?? ''
  return workspaceBySegment[routeSegment] ?? 'overview'
}

export function getProjectPageDescriptor(path: string, title: string): ShellPageDescriptor {
  const workspaceId = getWorkspaceIdFromPath(path)
  if (!workspaceId) {
    return {
      workspaceId: null,
      itemId: null,
      title,
      description: '管理项目、系统配置与平台能力。',
    }
  }

  const workspace = getProjectWorkspace(workspaceId)
  const segments = path.split('/').filter(Boolean)
  const routeSegment = segments[2] ?? ''
  const matchedItem = workspace?.items.find((candidate) => (candidate.segment ?? '') === routeSegment) ?? null
  const item = routeSegment === '' ? workspace?.items[0] ?? null : matchedItem
  const resolvedTitle = item?.label ?? title
  const resolvedDescription = item?.description ?? workspace?.description ?? title

  return {
    workspaceId,
    itemId: item?.id ?? null,
    title: resolvedTitle,
    description: resolvedDescription,
  }
}

export function getSecondaryNavigation(projectId: string, workspaceId: ShellWorkspaceId | null) {
  const workspace = getProjectWorkspace(workspaceId)
  if (!workspace) return []

  return workspace.items.map((item) => ({
    ...item,
    to: buildProjectPath(projectId, item.segment),
  }))
}
