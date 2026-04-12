# 08 — Phase 5-6：WritingWorkbench / 项目状态机 / Trace 回放

> **Step 6.3** | 对应后端 Phase 5-6（写作主工作流固化 + 最终验收）
>
> 核心后端模块：`interface/routers/chapters.py` · `interface/routers/projects.py` · `interface/routers/traces.py`
>
> API 端点：`GET /projects/{project_id}/writing-context` · `GET /projects/{project_id}/status` · `GET /projects/{project_id}/runs` · `GET /runs/{run_id}/steps`

---

## 1. Writing Workbench

目标：让章节生成前的前置检查、上下文确认、生成控制和运行链路出现在同一页面，减少作者在世界、角色、Plot、Trace 之间来回跳转。

### 1.1 页面结构

```
┌── Hero 区 ─────────────────────────────────────────────────────────────┐
│  创作主工作台 · 项目ID · 待确认变更计数                                │
└───────────────────────────────────────────────────────────────────────┘

┌── 左侧上下文栏 ────────────────┬── 中部生成主区 ───────────────────────┐
│  前置检查卡片                  │  章节号 / 目标字数 / 本章摘要         │
│  WorldState Top5 摘要          │  上一章 Hook / 当前卷目标             │
│  角色 Runtime 卡片             │  仅规划 / 开始生成 / 强制生成         │
│                                │  生成结果输出面板                     │
└───────────────────────────────┴───────────────────────────────────────┘

┌── 底部状态栏 ─────────────────────────────────────────────────────────┐
│  Planner → Writer → Critic → Editor → Maintenance                    │
│  每步显示状态 / token_in / token_out / 当前 run_id                    │
└───────────────────────────────────────────────────────────────────────┘
```

### 1.2 前置检查规则

- WorldState 未发布：显示 warning 卡片，按钮跳转到 `/project/:id/worldbuilder`
- 角色缺少 Drive 层：显示 warning 卡片，按钮跳转到 `/project/:id/characters`
- Plot 无当前卷目标：显示 warning 卡片，按钮跳转到 `/project/:id/plot`
- warning 不阻断生成，但必须提供“强制生成”开关，提醒用户当前写作包可能不完整

### 1.3 数据映射

`GET /projects/{project_id}/writing-context` 返回：

- `prechecks[]`：前置检查卡片
- `world.published / factions / regions / rules`：左栏世界摘要
- `characters[]`：角色 Runtime 卡片（位置 / agenda / pressure / recent_key_events）
- `previous_hook`：中栏提示条
- `current_volume_goal`：中栏提示条

`POST /chapters/run` 返回：

- `run_id`：底部状态栏轮询键
- `final_text` / `draft_text`：生成结果面板内容源

### 1.4 交互约束

- 点击“开始生成”后，按钮进入 `生成中…` 状态，直到 run 进入 `completed / failed / paused`
- run 建立后，每 1-2 秒轮询 `GET /runs/{run_id}/steps`
- 页面顶部待确认变更计数需要与项目状态接口一致，不自行本地估算

---

## 2. 项目状态机首页

目标：让项目首页变成“当前主线推进到哪里”的单一事实面板，而不是松散的导航聚合页。

### 2.1 状态机条

```
[Concept] → [World] → [Characters] → [Plot] → [Chapter N] → [Maintenance] → [Canon]
   completed     completed        completed      completed    in_progress    pending      pending
```

每个节点必须同时显示：

- `label`
- `status`：`completed | in_progress | pending`
- `statistic`：例如“世界已发布”“Drive 完整 4/5”“待提交变更 2”
- `href`：点击后跳转对应页面

### 2.2 顶部统计卡

- 角色总数 / Drive 覆盖数
- 当前卷目标
- 总字数 / 版本快照数量
- 待提交变更计数

### 2.3 项目动作卡

- 继续撰写：进入 `Writing Workbench`
- 世界构建：补齐或重新发布 RuntimeWorldState
- 角色矩阵：修复 Drive / Runtime 缺口
- 执行链路：复盘 Run、处理审批与 pending 变更

---

## 3. TraceInspector 回放说明

目标：让 Run 回放从“查看原始日志”升级为“按 5 步 Agent 树复盘”。

### 3.1 数据来源

- `GET /projects/{project_id}/runs`：获取项目 Run 列表
- `GET /runs/{run_id}`：获取单个 Run 概览
- `GET /runs/{run_id}/steps`：获取完整 `Run → Step → Artifact` 树
- `POST /runs/{run_id}/approve`：处理 HITL 暂停

### 3.2 卡片内容

每个 Step 卡片必须显示：

- `agent_name`
- `status`
- `input_summary`
- `output_content`
- `quality_scores`
- `token_in / token_out`
- `retry_count / retry_reason`

标准顺序固定为：

1. Planner
2. Writer
3. Critic
4. Editor
5. Maintenance

### 3.3 回放与审批

- Run 状态为 `paused` 时，界面需要高亮审批检查点并显示 approve / reject / retry 操作
- Writer 重试场景必须保留上一轮 `retry_reason`
- Maintenance 卡片要能显示本章生成后的记忆锚点、变更集和 Hook 回写结果摘要

---

## 4. 文档对齐结论

- WritingWorkbench 已是主写作入口，不再把生成、上下文、追踪拆散到多个页面
- 项目首页以工作流状态机为中心，而非静态概览卡堆叠
- TraceInspector 以真实 Run/Step/Artifact 数据驱动，不再使用占位链路