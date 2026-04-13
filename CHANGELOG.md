# Changelog

## v2.1.1 - 2026-04-12

- 统一 `narrative_os.__version__` 为版本真相源，并同步主 API、包元数据与前端包版本
- 将 `api_legacy.py` 收敛为兼容入口，避免继续维护重复的 FastAPI 路由定义
- 将前端 OpenAPI 生成脚本改为跨平台实现，移除 Windows 专用 Python 路径依赖
- 将 `frontend/src/api/world.ts` 的世界模型类型切换为直接复用 `api.gen.ts`
- 修复 Writing Workbench 在“本章摘要”为空时仍可发起规划/生成的问题，改为前端必填校验并阻止错误请求
- 修复 TRPG 面板对 LLM 原始 Markdown 强调符的展示污染，统一清洗流式叙事、历史记录与决策选项文本，并统一存档/读档回合显示与回滚弹窗默认选中逻辑
- 修复 WorldBuilder 图例仅能高亮不能编辑的问题，点击势力图例项即可稳定打开右侧详情面板
- 修复缺失项目路由的异常提示，将对象型后端错误解析为可读文案，并在项目不存在时自动回退到项目列表
- 统一 Plot Canvas 与 Character Matrix 的页头视觉层级，角色矩阵首屏改为默认选中首个角色，减少空白态和旧样式割裂感
- 修复 Writing Workbench “仅规划”结果直接输出原始 JSON 的问题，改为结构化展示剧情骨架、规划节点、Hook 与张力曲线
- 修复 TRPG 着陆阶段把决策选项混入章节预览、会话摘要与下章钩子的问题，归档预览与会话总结改为只保留 DM 叙事主体
- 修复旧运行时 SQLite 缺少 benchmark / author skill 列导致 `POST /projects/{project_id}/benchmark/jobs` 500 的问题，启动时会自动补齐兼容列
- 补齐 `Benchmark Studio` 的侧边栏入口，并将作者蒸馏前端校验改为至少 3 部作品后才允许提交
- Writing Workbench 补充 active author skill 展示，已应用 Skill 的 scene hints 与 anti-rules 会与 benchmark 一起显示
- 修复 Writing Workbench 在 `WorldState` 未发布时仍允许发起章节生成的问题，前端现在会按前置检查直接阻断该路径

## v2.1.0 - 2026-04-11

- 完成七阶段升级闭环，统一主工作流为 `Concept → World → Characters → Plot → Write → Maintenance → Canon`
- 新增 `Writing Workbench` 与项目状态机首页，补齐写作前置检查、角色 Runtime 展示与待提交变更提示
- 补齐 Run / Step / Artifact 追踪、HITL 审批、Changeset 审批流与 Trace 回放能力
- 阶段六验收通过：三条 E2E 用例、性能基准、全量测试与文档同步完成
- 发布后完成 warning 清理：修复 `world_type` 枚举序列化漂移、移除弃用 422 常量，并将非致命持久化异常改为结构化日志

## v2.0.0 - 2026-04-11

- 新增记忆检索与执行链路页面
- Metrics / Agent 页面切换为真实数据驱动
- 世界构建、角色矩阵与 Trace 空态体验完成清理