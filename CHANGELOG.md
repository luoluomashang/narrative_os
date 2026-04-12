# Changelog

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