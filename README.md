# Narrative OS

> 项目版本基线：v2.1.0
> 更新日期：2026-04-11

面向长篇小说创作的多智能体叙事操作系统。

从 prompts-only 流程升级为结构化工程化体系：
- 类型化数据模型（剧情/角色/世界/记忆）
- 多智能体编排（Planner/Writer/Critic/Editor/Maintenance）
- CLI + REST API + Web UI 三端一致
- TRPG 互动写作（终端与网页）
- 世界构建沙盘（可视化节点与关系编辑）

## v2.1.0 本次优化新增

- 新增 `Writing Workbench`：写作前置检查、WorldState 摘要、角色 Runtime、章节生成表单与 5 步 AgentRun 状态条集中在一个页面
- 新增项目首页状态机视图：`Concept → World → Characters → Plot → Chapter → Maintenance → Canon`
- 新增写作工作台上下文与 Trace API：`GET /projects/{project_id}/writing-context`、`GET /projects/{project_id}/runs`、`GET /runs/{run_id}/steps`
- Canon 变更流改为 `CANON_PENDING → approve/reject`，项目主页显示待提交变更数量
- Run / Step / Artifact 追踪链路补齐 5 Agent 树，支持重试原因、审批状态与回放
- 世界构建页补充显式“发布运行态”按钮，发布后项目首页与 Writing Workbench 会立即反映 `WorldState` 状态
- 项目首页 `Concept` 状态改为读取持久化概念数据，避免已保存概念仍显示“待补全概念”
- Writing Workbench 的 `地区 Top 5` 改为显示地区名称，不再暴露运行态 UUID

## v2.1.0 废弃与清理

- 废弃写作页与项目页中割裂的旧式入口，统一并入项目状态机与工作台
- 清理 Trace 列表在运行时 DB 切换场景下的落库漂移问题，避免 Run 列表与步骤树读取不同数据库
- 清理 `world_type` 枚举序列化漂移、非致命章节持久化 warning 与弃用的 422 常量，全量回归收敛为无 warning 通过

## 当前功能总览

### 1. 创作主链路
- 章节规划：自动生成章节骨架、节点和钩子建议
- 章节生成：完整执行 Planner -> Writer -> Critic -> Editor -> Maintenance
- 草稿快写：跳过规划快速出稿
- 质量评估：章节指标评分与一致性检查
- 去 AI 痕迹：Humanizer 后处理
- Governance 管线：PRE_RUN / POST_RUN / POST_COMMIT 钩子、HITL 暂停、RunTrace 持久化

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
- Publish：将当前沙盘编译并发布为 RuntimeWorldState，解除写作 / TRPG 前置阻塞

### 世界书能力说明（当前版本）
- 当前版本不单独提供“世界书”页面。
- 世界书能力由三部分组成：
	- WorldBuilder 结构化编辑（地区/势力/力量体系/关系/时间线）
	- `POST /projects/{project_id}/world/finalize` 写入 `knowledge_base.json`
	- MemorySystem 提供记忆检索与召回能力
- 推荐做法：将“世界书”视作现有能力组合，而非新增独立模块。

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
- **四档控制模式**：`user_driven / semi_agent / directed / director`，动态切换
- **SL 系统（存/读档）**：`SaveStore.create()` 手动存档 + `SoftRollback.restore()` 软回退，保留 memory_summary 防止完全失忆
- **防死锁**：`DeadlockBreaker.detect()` + `DeadlockBreaker.resolve()` 自动解套叙事

### 6. 世界发布管线（World Publish）
- `POST /projects/{project_id}/world/publish` — 沙盘 → WorldState 编译 + 持久化
- WorldValidator：校验世界逻辑一致性，输出错误/警告/建议三级报告
- WorldCompiler：将沙盘数据编译为可运行的 WorldState（地区、势力、力量体系、规则）
- WorldRepository：将 RuntimeWorldState 写入 DB + 文件系统

### 7. CanonCommit（正史提交管线）
- 三种提交模式：
  - `SESSION_ONLY` — 仅保留TRPG会话记录，不影响主线
	- `DRAFT_CHAPTER` — 生成草稿，进入待确认变更流
  - `CANON_CHAPTER` — 二次确认后直接提交正史
- 变更集 API：`GET /projects/{project_id}/changesets`、approve/reject 端点
- `CanonCommit.create_changeset()` → `WorldChangeSet`
- Maintenance 会自动生成 `CANON_PENDING` 变更集，审批通过后才写入知识库 / RuntimeWorldState

### 8. 可视化与运营面板
- 情节画布、角色矩阵、记忆系统、质量仪表盘、风格控制台
- Agent 工坊、消耗统计、插件市场、全局与项目设置
- 项目状态机首页、Writing Workbench、TraceInspector 回放

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

## 推荐工作流（含世界书）

1. 在故事概念页完成一句话/一段话设定（`/project/:id/concept`）。
2. 在世界构建页完善地区、势力、关系与时间线（`/project/:id/worldbuilder`）。
3. 点击世界构建中的“完成世界设定”，将结构化数据写入知识库。
4. 点击世界构建中的“发布运行态”，生成并持久化 `RuntimeWorldState`。
5. 进入角色矩阵补齐角色口吻、约束与动机（`/project/:id/characters`）。
6. 在章节撰写页使用 `Writing Workbench` 完成前置检查、生成与 Trace 追踪（`/project/:id/write`）。
7. 在项目首页或执行链路页审查待提交变更与 Run 树（`/project/:id`、`/project/:id/trace`）。
8. 批准 `CANON_PENDING` 变更后，再进入一致性检查与人味化质检（`/project/:id/check`、`/project/:id/humanize`）。

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
- `/project/:id/memory-search` 记忆检索
- `/project/:id/metrics` 质量仪表盘
- `/project/:id/style` 风格控制台
- `/project/:id/check` 一致性检查
- `/project/:id/humanize` 去 AI 痕迹
- `/project/:id/agents` Agent 工坊
- `/project/:id/trace` 执行链路
- `/project/:id/chapters` 章节管理
- `/project/:id/settings` 项目设置

## REST API 能力分组

### 核心生成
- `GET /health`
- `POST /chapters/run`
- `POST /chapters/plan`
- `GET /projects/{project_id}/writing-context`
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
- `GET /projects/{project_id}/runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/steps`
- `POST /runs/{run_id}/approve`
- `GET /projects/{project_id}/changesets`
- `GET /projects/{project_id}/changesets/{changeset_id}`
- `POST /projects/{project_id}/changesets/{changeset_id}/approve`
- `POST /projects/{project_id}/changesets/{changeset_id}/reject`
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

### 世界发布
- `POST /projects/{project_id}/world/publish` — 沙盘→WorldState 编译
- `GET /projects/{project_id}/world/overview` — 世界统计摘要

### 变更集
- `GET /projects/{project_id}/changesets` — 列出变更集
- `GET /projects/{project_id}/changesets/{cs_id}` — 变更集详情
- `POST /projects/{project_id}/changesets/{cs_id}/approve` — 批量审批 + 提交
- `POST /projects/{project_id}/changesets/{cs_id}/reject` — 驳回变更集
- `POST /projects/{project_id}/sessions/{session_id}/commit` — 会话结束时提交

### SL 存档
- `GET /projects/{project_id}/sessions/{session_id}/saves` — 存档列表
- `POST /projects/{project_id}/sessions/{session_id}/save` — 手动存档
- `POST /projects/{project_id}/sessions/{session_id}/saves/{save_id}/restore` — 读档回退

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
