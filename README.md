# Narrative OS

面向长篇小说创作的多智能体叙事操作系统。

从 prompts-only 流程升级为结构化工程化体系：
- 类型化数据模型（剧情/角色/世界/记忆）
- 多智能体编排（Planner/Writer/Critic/Editor/Maintenance）
- CLI + REST API + Web UI 三端一致
- TRPG 互动写作（终端与网页）
- 世界构建沙盘（可视化节点与关系编辑）

## 当前功能总览

### 1. 创作主链路
- 章节规划：自动生成章节骨架、节点和钩子建议
- 章节生成：完整执行 Planner -> Writer -> Critic -> Editor
- 草稿快写：跳过规划快速出稿
- 质量评估：章节指标评分与一致性检查
- 去 AI 痕迹：Humanizer 后处理

### 2. 项目与数据管理
- 项目管理：创建、编辑、归档、软删除
- 项目隔离：所有项目功能挂载在 `/project/:id/*`
- 章节管理：章节列表、详情读取、导出全书
- 设置分层：全局设置 + 项目覆盖
- LLM 设置：读取、更新、连通性测试

### 3. 世界构建（WorldBuilder 沙盘）
- 地区/势力/力量体系节点创建与删除
- 节点详细字段编辑（地区环境、势力治理、力量规则等）
- 关系连线创建、关系详情编辑、关系删除
- 批量关系编辑
- 图谱/地图/分层/星图多视图切换，支持主题切换
- 图谱模式支持双向拖拽连线（Loose Connection）
- 自动布局后自动 FitView，快速回到全局可见范围
- 底部时间线支持事件新增、浏览与删除
- 势力关系映射支持“按名称编辑 + 分值滑杆”，不再仅显示 UUID
- AI 建议关系按实体名称展示，便于阅读与采纳
- 逻辑校验面板 + AI 深度分析
- 力量体系保存时可选“同步到全局继承节点”
- Finalize：将世界设定写入知识库

详细说明见 [docs/ui/07_worldbuilder_module_spec.md](docs/ui/07_worldbuilder_module_spec.md)。

### 4. 角色矩阵（Character Matrix）
- 角色 CRUD：创建、查看、编辑、删除角色
- **档案 Tab**：基础信息编辑（名称、特质、目标、背景、外貌、性格、别名）
- **状态 Tab**：ECharts 雷达图展示 6 维属性 + 弧光阶段进度条
- **限制 Tab**：行为约束规则（rule / severity / context）可编辑，支持实时约束测试
- **关系 Tab**：D3 力导向关系图 + 关系列表编辑（角色名 + 好感度 -1~1）
- **对话口吻 Tab**：VoiceFingerprint 五维编辑 + speech_style + 口头禅 + Few-Shot 对话示例 + 口吻试戏面板
- **动机冲突 Tab**：Motivation（desire / fear / tension）可编辑 + 张力总览 + scenario_context / system_instructions
- Pipeline 集成：角色口吻和动机冲突自动注入 Writer/Planner/Critic/Maintenance Agent 提示词

### 5. TRPG 互动模式
- 会话创建、行动推进、帮回、回滚、结束摘要
- WebSocket 流式叙事
- 密度模式：dense / normal / sparse

### 6. 可视化与运营面板
- 情节画布、角色矩阵、记忆系统、质量仪表盘、风格控制台
- Agent 工坊、消耗统计、插件市场、全局与项目设置

## 快速开始

### 环境要求
- Python 3.11+
- Node.js 18+
- pnpm

### 安装

```bash
cd narrative_os
pip install -e ".[dev]"
```

### 配置

在项目根目录创建 `.narrative_os.env`：

```env
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434
DAILY_TOKEN_BUDGET=100000
CHROMA_DB_PATH=.narrative_db
LOG_LEVEL=INFO
STATE_DIR=.narrative_state
```

### 启动开发环境

```bash
narrative dev
```

默认启动：
- API: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`

### 典型命令

```bash
# 初始化项目（交互式）
narrative init --project my_novel

# 规划一章
narrative plan --chapter 1 --summary "主角踏入禁区"

# 生成一章
narrative run --chapter 1 --summary "主角踏入禁区" --project my_novel

# 启动 TRPG 终端互动
narrative interactive --project my_novel --density normal

# 一致性检查 + 去 AI 痕迹
narrative check --chapter 1 --draft chapter1.md
narrative humanize --input chapter1.md --output chapter1_human.md
```

## CLI 命令

- `narrative run` 完整章节生成
- `narrative plan` 仅规划章节
- `narrative write` 快速草稿生成
- `narrative init` 交互式项目初始化
- `narrative status` 查看项目状态
- `narrative rollback` 回滚项目章节状态
- `narrative cost` 查看 token 消耗
- `narrative metrics` 计算质量指标
- `narrative check` 一致性检查
- `narrative humanize` 去 AI 痕迹处理
- `narrative interactive` TRPG 终端模式
- `narrative dev` 一键启动前后端开发服务

## Web UI 路由（当前实现）

### 全局页面
- `/projects` 项目管理
- `/settings` 全局设置
- `/plugins` 插件市场
- `/cost` 全局消耗统计

### 项目页面
- `/project/:id` 项目主页
- `/project/:id/worldbuilder` 世界构建沙盘
- `/project/:id/concept` 故事概念
- `/project/:id/plot` 剧情画布
- `/project/:id/characters` 角色矩阵
- `/project/:id/write` 章节撰写
- `/project/:id/trpg` TRPG 互动
- `/project/:id/memory` 记忆系统
- `/project/:id/metrics` 质量仪表盘
- `/project/:id/style` 风格控制台
- `/project/:id/check` 一致性检查
- `/project/:id/humanize` 去 AI 痕迹
- `/project/:id/agents` Agent 工坊
- `/project/:id/chapters` 章节管理
- `/project/:id/settings` 项目设置

## REST API 能力分组

### 核心生成
- `GET /health`
- `POST /chapters/run`
- `POST /chapters/plan`
- `GET /projects/{project_id}/status`
- `GET /cost`
- `POST /metrics`

### TRPG
- `POST /sessions/create`
- `POST /sessions/{session_id}/step`
- `POST /sessions/{session_id}/interrupt`
- `POST /sessions/{session_id}/rollback`
- `POST /sessions/{session_id}/end`
- `GET /sessions/{session_id}/status`
- `WS /ws/sessions/{session_id}`

### 数据访问与扩展
- `GET /projects/{project_id}/plot`
- `GET /projects/{project_id}/characters`
- `GET /projects/{project_id}/characters/{name}`
- `GET /projects/{project_id}/memory`
- `GET /projects/{project_id}/memory/search`
- `GET /traces/{chapter_id}`
- `GET /plugins`
- `POST /plugins/{plugin_id}/toggle`
- `POST /style/extract`
- `GET /style/presets`
- `POST /consistency/check`

### 项目管理与设置
- `GET /projects`
- `POST /projects/init`
- `PUT /projects/{project_id}`
- `DELETE /projects/{project_id}`
- `POST /projects/{project_id}/archive`
- `GET /projects/{project_id}/chapters`
- `GET /projects/{project_id}/chapters/{chapter}`
- `GET /projects/{project_id}/export`
- `GET /settings`
- `PUT /settings`
- `GET /projects/{project_id}/settings`
- `PUT /projects/{project_id}/settings`
- `GET /settings/llm`
- `PUT /settings/llm`
- `POST /settings/llm/test`

### 概念与世界构建
- `GET /projects/{project_id}/concept`
- `PUT /projects/{project_id}/concept`
- `GET /projects/{project_id}/world`
- `PUT /projects/{project_id}/world/meta`
- `POST /projects/{project_id}/world/regions`
- `GET /projects/{project_id}/world/regions/{region_id}`
- `PUT /projects/{project_id}/world/regions/{region_id}`
- `DELETE /projects/{project_id}/world/regions/{region_id}`
- `POST /projects/{project_id}/world/factions`
- `GET /projects/{project_id}/world/factions/{faction_id}`
- `PUT /projects/{project_id}/world/factions/{faction_id}`
- `DELETE /projects/{project_id}/world/factions/{faction_id}`
- `POST /projects/{project_id}/world/power-systems`
- `GET /projects/{project_id}/world/power-systems/{ps_id}`
- `PUT /projects/{project_id}/world/power-systems/{ps_id}`
- `DELETE /projects/{project_id}/world/power-systems/{ps_id}`
- `GET /projects/{project_id}/world/relations`
- `GET /projects/{project_id}/world/relations/{relation_id}`
- `POST /projects/{project_id}/world/relations`
- `PUT /projects/{project_id}/world/relations/{relation_id}`
- `DELETE /projects/{project_id}/world/relations/{relation_id}`
- `GET /projects/{project_id}/world/power-templates`
- `POST /projects/{project_id}/world/finalize`

### 角色矩阵
- `GET /projects/{project_id}/characters` — 角色列表摘要
- `GET /projects/{project_id}/characters/{name}` — 角色详情
- `POST /projects/{project_id}/characters` — 创建角色
- `PUT /projects/{project_id}/characters/{name}` — 更新角色
- `DELETE /projects/{project_id}/characters/{name}` — 删除角色
- `POST /projects/{project_id}/characters/{name}/test-voice` — 口吻试戏

## 目录

- 主入口：`narrative_os/interface/cli.py`、`narrative_os/interface/api.py`
- 前端：`frontend/src/pages/`
- 设计文档：`docs/ui/`
- 测试：`tests/`

## 文档

- 中文使用手册：[使用手册.md](使用手册.md)
- UI 文档索引：[docs/ui/README.md](docs/ui/README.md)
- 世界构建模块规格：[docs/ui/07_worldbuilder_module_spec.md](docs/ui/07_worldbuilder_module_spec.md)
