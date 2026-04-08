# 世界构建模块功能说明

## 1. 文档目的

本文档用于说明 世界构建（WorldBuilder）模块 的前端功能、交互流程、核心数据结构、接口能力、同步机制与测试建议。

适用对象：
- 产品经理：确认功能边界与交互闭环
- 前端/后端开发：对齐字段与行为约定
- 测试工程师：构建功能回归用例

---

## 2. 模块定位

世界构建模块是项目级世界观编辑中心，目标是让用户在一个可视化画布中完成以下任务：
- 编辑世界元信息（名称、类型、描述）
- 创建并维护地区节点
- 创建并维护势力节点
- 创建并维护力量体系
- 维护地区/势力之间的关系网络
- 将世界设定一次性写入知识库

页面路径：
- `/project/:id/worldbuilder`

---

## 3. 页面结构

页面采用三栏布局：

1. 左侧栏（控制区）
- 世界信息表单
- 节点操作区（+地区 / +势力 / +力量体系）
- 关系批量编辑区
- 实时统计卡（地区/势力/体系/关系）

2. 中央画布（Vue Flow）
- 节点可视化（地区、势力）
- 边关系可视化（source -> target）
- 交互能力：点击、连线、拖拽、缩放、平移

3. 右侧栏（详情区）
- 节点详情（地区或势力）
- 关系详情
- 力量体系列表与编辑面板

---

## 4. 核心功能说明

### 4.1 世界信息编辑

功能：
- 编辑 `world_name`
- 编辑 `world_type`
- 编辑 `world_description`
- 点击 保存世界信息 持久化

入口：左侧 世界信息 卡片

---

### 4.2 地区节点管理

功能：
- 通过弹窗创建地区（新建即支持详细字段）
- 在详情面板编辑地区全量字段
- 删除地区时自动清理相关关系边

地区关键字段（摘要）：
- 基础：name, region_type, x, y
- 地理：terrain, climate, special_features, landmarks
- 种族：primary_race, secondary_races, is_mixed, race_notes
- 文明：name, belief_system, culture_tags, govt_type
- 力量接入：inherits_global, custom_system_id, power_notes
- 关联：faction_ids, alignment, tags, notes

---

### 4.3 势力节点管理

功能：
- 通过弹窗创建势力
- 在详情面板编辑势力全量字段
- 删除势力时自动清理相关关系边

势力关键字段（摘要）：
- 基础：name, scope, description
- 领地：territory_region_ids
- 阵营：alignment
- 力量绑定：power_system_id
- 关系映射：relation_map
- 备注：notes

---

### 4.4 力量体系管理

功能：
- 创建力量体系（支持模板）
- 在右侧力量体系面板编辑：
  - 体系名称
  - 等级定义（可增删）
  - 规则（多行）
  - 资源（多行）
  - 备注
- 删除力量体系

关键字段（摘要）：
- name, template
- levels[{ name, description, requirements }]
- rules[]
- resources[]
- notes

---

### 4.5 力量体系“全局同步”能力（新增）

背景问题：
- 之前只能逐个节点手工修改，缺少“全局修改后可选同步”机制。

新增能力：
- 在力量体系编辑区增加开关：
  - `保存后同步到全局继承节点`

行为规则：
1. 不勾选：
- 仅保存当前力量体系本体，保持原行为

2. 勾选后保存：
- 同步地区：将所有 `power_access.inherits_global = true` 的地区，指向当前体系
- 同步势力：将 `power_system_id` 为空的势力，绑定到当前体系
- 保存完成后提示同步数量

说明：
- 这是“可选同步”，不会强制覆盖所有节点。
- 设计目标是兼顾批量效率与手工精细控制。

---

### 4.6 关系网络管理

功能：
- 通过画布拖拽连接句柄创建关系
- 关系详情面板支持编辑 relation_type / label / description
- 支持删除关系
- 支持批量关系编辑：
  - 按关系类型筛选
  - 批量改 relation_type
  - 批量加 label 前缀

关系关键字段：
- source_id, target_id
- relation_type
- label
- description

---

### 4.7 画布交互

支持：
- 节点点击打开详情
- 节点拖拽后自动保存坐标（地区）
- 边点击打开关系详情
- 连线手势创建关系
- 小地图、缩放、平移

---

### 4.8 完成世界设定（Finalize）

功能：
- 调用 finalize 接口
- 将地区/势力/力量体系/关系写入知识库
- 页面显示汇总结果（数量）

---

## 5. 前端数据结构（摘要）

主对象：`WorldSandboxData`
- world_name
- world_type
- world_description
- regions[]
- factions[]
- power_systems[]
- relations[]
- world_rules[]

前端 API 定义位置：
- `frontend/src/api/world.ts`

---

## 6. 后端接口能力（项目级）

接口前缀：
- `/projects/{project_id}/world`

核心接口分组：
- 世界：GET / PUT(meta)
- 地区：POST / GET(id) / PUT(id) / DELETE(id)
- 势力：POST / GET(id) / PUT(id) / DELETE(id)
- 力量体系：POST / GET(id) / PUT(id) / DELETE(id)
- 关系：GET(list) / GET(id) / POST / PUT(id) / DELETE(id)
- 工具：GET power-templates / POST finalize

接口定义位置：
- `narrative_os/interface/api.py`

---

## 7. 交互闭环（推荐验收路径）

1. 打开世界构建页
2. 创建地区（弹窗）
3. 创建势力（弹窗）
4. 编辑地区详情并保存
5. 编辑势力详情并保存
6. 连线创建关系
7. 编辑关系详情并保存
8. 使用批量关系编辑修改关系类型/标签
9. 创建力量体系
10. 在力量体系编辑区勾选“保存后同步到全局继承节点”并保存
11. 打开地区/势力详情，确认同步结果
12. 删除势力，确认关系联动删除
13. 点击 完成世界设定，确认写库汇总

---

## 8. 样式与可用性现状

已验证样式点：
- 创建弹窗层级、表单间距、按钮风格一致
- 三栏布局信息密度清晰
- 反馈提示（成功/信息）可见
- 详情面板分区明确，操作路径直观

注意事项：
- 小屏下仍有较高信息密度，建议后续迭代移动端专用布局（抽屉/分步表单）

---

## 9. 已知约束与建议

1. 同步策略当前为“继承全局地区 + 未绑定势力”
- 优点：避免误覆盖已经精调过的节点
- 建议：后续可加“强制覆盖模式”作为高级选项

2. 批量操作目前集中在关系层
- 建议后续补：地区/势力批量标签或阵营调整

3. 力量体系同步后可追溯性
- 建议后续记录同步操作日志（谁、何时、影响数量）

---

## 10. 代码入口索引

前端：
- `frontend/src/pages/WorldBuilder/index.vue`
- `frontend/src/pages/WorldBuilder/components/RegionDetailPanel.vue`
- `frontend/src/pages/WorldBuilder/components/FactionDetailPanel.vue`
- `frontend/src/pages/WorldBuilder/components/PowerSystemPanel.vue`
- `frontend/src/pages/WorldBuilder/components/PowerSystemDialog.vue`
- `frontend/src/pages/WorldBuilder/components/WorldNodeDialog.vue`
- `frontend/src/api/world.ts`

后端：
- `narrative_os/interface/api.py`
- `narrative_os/core/world_sandbox.py`

测试：
- `tests/test_api_data_access.py`（世界构建相关 API 用例）

---

## 11. 更新记录

- 2026-04-07：补充“力量体系全局同步（可选）”机制与文档。