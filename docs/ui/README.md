# Narrative OS — UI 设计规范总索引

> **Phase 6 交互规范** | 仅设计文档，不含前端代码实现
>
> 基础设计研究来源：`UI设计文档生成指南.md`

---

## 文档结构

| 文件 | 覆盖范围 | 对应后端阶段 |
|------|----------|------------|
| [01_global_visual_spec.md](01_global_visual_spec.md) | 全局视觉语言：色彩/排版/动效 | 跨模块 |
| [02_phase1_structure_ui.md](02_phase1_structure_ui.md) | Phase 1：剧情画布 / 角色矩阵 / 记忆系统 / Skill 积木 | `core/` |
| [03_phase2_scene_hitl_ui.md](03_phase2_scene_hitl_ui.md) | Phase 2：场景生成 IDE / Diff 视图 / HITL 拦截网 | `agents/` + `infra/` |
| [04_phase34_agent_telemetry_ui.md](04_phase34_agent_telemetry_ui.md) | Phase 3-4：智能体车间 / 深度追踪 / 资源遥测 | `orchestrator/` + `infra/` |
| [05_phase5_metrics_style_plugin_ui.md](05_phase5_metrics_style_plugin_ui.md) | Phase 5：叙事波形 / 风格控制台 / 插件集市 | `skills/` + `plugins/` |
| [06_trpg_ui.md](06_trpg_ui.md) | TRPG 互动专属 UI：PING_PONG 面板 / 帮回按钮 | `agents/interactive.py` |
| [08_phase56_workbench_trace_ui.md](08_phase56_workbench_trace_ui.md) | Phase 5-6：WritingWorkbench / 项目状态机 / Trace 回放 | `interface/routers/chapters.py` + `interface/routers/projects.py` + `interface/routers/traces.py` |

---

## 后端 API ↔ UI 组件全映射表

### REST 端点（`interface/api.py`）

| HTTP 端点 | UI 入口点 | 触发场景 |
|-----------|----------|---------|
| `GET  /health` | 顶部状态栏 · 系统灯 | 页面加载自检 |
| `POST /chapters/run` | 场景生成器 **生成** 按钮 | 用户点击"开始生成" |
| `POST /chapters/plan` | 剧情节点属性面板 **规划** 按钮 | 用户填写节点参数后提交 |
| `GET  /projects/{id}/status` | 项目状态侧栏 | 切换项目时自动拉取 |
| `GET  /cost` | 顶栏 Token 环形进度条 | 轮询（30s间隔） |
| `POST /metrics` | 叙事波形图 **分析** 触发 | 章节完成后自动触发 |

### 核心数据层（`core/`）

| 模块 | 关键类 | UI 组件 |
|------|--------|---------|
| `core/plot.py` | `PlotGraph`, `PlotNode`, `NodeStatus` | 无限画布剧情节点卡片 |
| `core/character.py` | `CharacterState`, `BehaviorConstraint`, `VoiceFingerprint` | 角色状态雷达图 + 行为约束引擎 |
| `core/memory.py` | `MemorySystem`, `MemoryRecord` | 三层记忆抽屉面板 |
| `core/state.py` | `StateManager` | 项目状态侧栏 |

### 智能体层（`agents/`）

| 模块 | 关键类/函数 | UI 组件 |
|------|------------|---------|
| `agents/planner.py` | `PlannerAgent.plan()` | 节点规划面板 |
| `agents/writer.py` | `WriterAgent.write()` | 场景生成器中栏 |
| `agents/critic.py` | `CriticAgent.critique()` | 右栏诊断卡片 |
| `agents/editor.py` | `EditorAgent.edit()` | Diff 视图补丁面板 |
| `agents/maintenance.py` | `MaintenanceAgent.maintain()` | 章末维护状态条 |
| `agents/interactive.py` | `InteractiveAgent`, `SessionPhase` | TRPG PING_PONG 面板 |

### 技能 / 插件层（`skills/`, `plugins/`）

| 模块 | 关键类 | UI 组件 |
|------|--------|---------|
| `skills/dsl.py` | `SkillRegistry`, `SkillSpec` | 技能积木库卡片 |
| `skills/metrics.py` | `NarrativeMetricsCalc` | 叙事波形时间线 |
| `skills/style_engine.py` | `StyleEngine` | 风格控制台滑块 |
| `plugins/registry.py` | `PluginRegistry` | 插件集市瀑布流 |

### 基础设施层（`infra/`）

| 模块 | 关键类 | UI 组件 |
|------|--------|---------|
| `infra/hitl.py` | `HITLManager.checkpoint()` | 阻塞式审批模态框 / 异步通知托盘 |
| `infra/hitl.py` | `HITLManager.approve()` / `.reject()` | 模态框操作按钮 |
| `infra/cost.py` | `CostController` | Token 环形进度条 + 堆叠柱状图 |

### 编排层（`orchestrator/`）

| 模块 | 关键类 | UI 组件 |
|------|--------|---------|
| `orchestrator/graph.py` | LangGraph 状态机 | 智能体车间泳道图 |
| `orchestrator/graph.py` | 节点路由逻辑 | 深度追踪执行树 |

---

## 设计约束速查

- **主题**：强制暗黑模式，拒绝纯黑 `#000`，基础背景 `#0a0a0b`
- **AI 活跃色**：`#2ef2ff`（电光青）
- **人工干预色**：`#ff2e88`（霓虹粉）
- **成功/记忆色**：`#3f5a48`（植物绿）
- **文本宽度**：每行约 75 字符，防阅读疲劳
- **等待动效**：呼吸灯光晕 + 滚动模糊日志流（禁止纯 Spinner）
- **破坏性操作**：必须触发 HITL 阻塞模态框，不得静默执行
