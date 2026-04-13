"""
core/world_compiler.py — Phase 6 Stage 1: 编辑态编译器

职责：
  - 输入：ConceptData + WorldSandboxData + 可选历史 seed WorldState
  - 输出：标准 WorldState + PublishReport + PublishWarnings
  - 字段归一化：sandbox.Region/Faction → runtime.geography/FactionState
  - 引用补全：势力↔地区双向关系、power_system 引用合法性

说明：
  WorldSandboxData（编辑态）→ WorldCompiler → WorldState（运行态）
  这是从人工可编辑形式转换为运行时可消费形式的唯一标准路径。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.core.world import FactionState, PowerSystem, PowerLevel, WorldState
from narrative_os.core.world_sandbox import (
    ConceptData,
    Faction,
    Region,
    WorldSandboxData,
)


# ------------------------------------------------------------------ #
# 输出数据模型                                                          #
# ------------------------------------------------------------------ #

class PublishReport(BaseModel):
    """编译报告，描述从沙盘到运行态的转换摘要。"""
    factions_compiled: int = 0
    regions_compiled: int = 0
    power_systems_compiled: int = 0
    rules_compiled: int = 0
    timeline_events_compiled: int = 0
    relations_compiled: int = 0
    warnings: list[str] = Field(default_factory=list)
    world_version: str = "v1"

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


# ------------------------------------------------------------------ #
# WorldCompiler                                                        #
# ------------------------------------------------------------------ #

class WorldCompiler:
    """
    将编辑态（WorldSandboxData）编译为运行态（WorldState）。

    使用方式：
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=concept_data, sandbox=sandbox_data)
    """

    def compile(
        self,
        concept: ConceptData | None,
        sandbox: WorldSandboxData,
        seed_world: WorldState | None = None,
    ) -> tuple[WorldState, PublishReport]:
        """
        将沙盘数据编译为运行态 WorldState。

        Args:
            concept: 故事概念数据（可选，补充 genre_tags 等）
            sandbox: 世界沙盘数据（主要来源）
            seed_world: 旧版 WorldState（可选，用于保留历史快照、继承 timeline 等）

        Returns:
            (WorldState, PublishReport)
        """
        report = PublishReport()

        # ── 初始化 WorldState ────────────────────────────────────────
        world = WorldState()

        # 如果有 seed world，继承其 timeline 和 snapshot_history
        if seed_world is not None:
            world.timeline = list(seed_world.timeline)
            world.snapshot_history = list(seed_world.snapshot_history)
            world.current_chapter = seed_world.current_chapter
            world.current_volume = seed_world.current_volume

        # ── 1. 编译势力（Faction → FactionState） ───────────────────
        faction_id_map: dict[str, str] = {}  # sandbox faction.id → runtime faction.id

        for sb_faction in sandbox.factions:
            fs = self._compile_faction(sb_faction)
            world.factions[fs.id] = fs
            faction_id_map[sb_faction.id] = fs.id
            report.factions_compiled += 1

        # ── 2. 编译势力关系（relation_map） ─────────────────────────
        for sb_faction in sandbox.factions:
            fs = world.factions.get(faction_id_map.get(sb_faction.id, sb_faction.id))
            if fs is None:
                continue
            for target_id, value in sb_faction.relation_map.items():
                # 将 sandbox faction id 映射到 runtime id
                runtime_target = faction_id_map.get(target_id, target_id)
                if runtime_target in world.factions:
                    fs.hostility_map[runtime_target] = float(value)
                else:
                    report.add_warning(
                        f"势力 '{sb_faction.name}' 关系目标 '{target_id}' 未找到对应运行态势力，已跳过"
                    )

        # ── 3. 编译地理（Region → geography dict） ────────────────
        for sb_region in sandbox.regions:
            geo_entry = self._compile_region(sb_region, faction_id_map)
            world.geography[sb_region.id] = geo_entry
            report.regions_compiled += 1

        # ── 4. 编译力量体系（PowerSystem → runtime） ─────────────
        for sb_ps in sandbox.power_systems:
            ps = self._compile_power_system(sb_ps)
            world.power_system = ps  # 当前只支持单一力量体系，取最后一个
            report.power_systems_compiled += 1

        # 如果没有沙盘力量体系但 seed 有，保留 seed 的
        if report.power_systems_compiled == 0 and seed_world is not None:
            world.power_system = seed_world.power_system

        # ── 5. 编译世界规则 ──────────────────────────────────────
        seen_rules: set[str] = set(world.rules_of_world)
        for rule in sandbox.world_rules:
            if rule and rule not in seen_rules:
                world.rules_of_world.append(rule)
                seen_rules.add(rule)
                report.rules_compiled += 1

        # ── 6. 编译时间线事件 ────────────────────────────────────
        from narrative_os.core.world import TimelineEvent
        import uuid as _uuid
        existing_event_ids = {e.id for e in world.timeline}
        for sb_event in sandbox.timeline_events:
            if sb_event.id in existing_event_ids:
                continue
            te = TimelineEvent(
                id=sb_event.id or str(_uuid.uuid4()),
                chapter=0,  # 时间线事件不一定对应具体章节
                description=f"[{sb_event.year}] {sb_event.title}: {sb_event.description}",
                affected_factions=list(
                    faction_id_map.get(sb_event.linked_entity_id, sb_event.linked_entity_id or "")
                ) if sb_event.linked_entity_id else [],
            )
            world.timeline.append(te)
            report.timeline_events_compiled += 1

        # ── 7. 补全地区↔势力双向关系 ────────────────────────────
        self._complete_bidirectional_relations(world, sandbox, faction_id_map, report)

        # ── 8. 验证 power_system 引用合法性 ─────────────────────
        self._validate_power_system_refs(world, sandbox, faction_id_map, report)

        # ── 9. 计算衍生统计 ─────────────────────────────────────
        report.relations_compiled = sum(
            len(fs.hostility_map) for fs in world.factions.values()
        )

        return world, report

    def build_runtime_diff(
        self,
        sandbox: WorldSandboxData,
        world: WorldState,
    ) -> dict[str, Any]:
        """生成 sandbox -> runtime 的结构化 diff 预览。"""
        sections: list[dict[str, Any]] = []
        auto_fix_notes: list[str] = []

        geography_items: list[dict[str, str]] = []
        for region in sandbox.regions:
            runtime_region = world.geography.get(region.id, {})
            sandbox_factions = "、".join(region.faction_ids) if region.faction_ids else "无"
            runtime_factions_list = runtime_region.get("faction_ids", []) if isinstance(runtime_region, dict) else []
            runtime_factions = "、".join(runtime_factions_list) if runtime_factions_list else "无"
            effect = "地区已编译为运行态 geography"
            if set(runtime_factions_list) != set(region.faction_ids):
                effect = "编译时补全了地区与势力的双向归属"
                auto_fix_notes.append(
                    f"地区 '{region.name}' 的势力归属已由运行态自动补全为：{runtime_factions}"
                )
            geography_items.append(
                {
                    "target_id": region.id,
                    "target_name": region.name,
                    "change_type": "region_projection",
                    "before": f"沙盘势力：{sandbox_factions}",
                    "after": f"运行态势力：{runtime_factions}",
                    "effect": effect,
                    "note": runtime_region.get("terrain", "") if isinstance(runtime_region, dict) else "",
                }
            )
        if geography_items:
            sections.append({"key": "geography", "label": "地区投影", "items": geography_items})

        faction_items: list[dict[str, str]] = []
        for faction in sandbox.factions:
            runtime_faction = world.factions.get(faction.id)
            runtime_territory_list = list(runtime_faction.territory) if runtime_faction is not None else []
            sandbox_territory = "、".join(faction.territory_region_ids) if faction.territory_region_ids else "无"
            runtime_territory = "、".join(runtime_territory_list) if runtime_territory_list else "无"
            effect = "势力领地与敌意映射已编译到运行态"
            if set(runtime_territory_list) != set(faction.territory_region_ids):
                effect = "编译时根据地区反向声明补全了势力领地"
                auto_fix_notes.append(
                    f"势力 '{faction.name}' 的运行态领地已自动补全为：{runtime_territory}"
                )
            hostility_count = len(runtime_faction.hostility_map) if runtime_faction is not None else 0
            faction_items.append(
                {
                    "target_id": faction.id,
                    "target_name": faction.name,
                    "change_type": "faction_projection",
                    "before": f"沙盘领地：{sandbox_territory}",
                    "after": f"运行态领地：{runtime_territory}",
                    "effect": effect,
                    "note": f"敌意关系 {hostility_count} 条",
                }
            )
        if faction_items:
            sections.append({"key": "factions", "label": "势力投影", "items": faction_items})

        power_items: list[dict[str, str]] = []
        runtime_power_name = world.power_system.name if world.power_system is not None else "无"
        for index, power_system in enumerate(sandbox.power_systems):
            effect = "已映射为当前运行态主力量体系"
            if power_system.name != runtime_power_name:
                effect = "当前运行态仅保留单一主力量体系，沙盘条目未直接生效"
            power_items.append(
                {
                    "target_id": power_system.id,
                    "target_name": power_system.name,
                    "change_type": "power_projection",
                    "before": f"沙盘等级 {len(power_system.levels)} 层",
                    "after": f"运行态主体系：{runtime_power_name}",
                    "effect": effect,
                    "note": f"排序位置 {index + 1}",
                }
            )
        if power_items:
            sections.append({"key": "power", "label": "力量体系", "items": power_items})

        timeline_items: list[dict[str, str]] = []
        for event in sandbox.timeline_events:
            compiled = next(
                (
                    timeline_event.description
                    for timeline_event in world.timeline
                    if event.title and event.title in timeline_event.description
                ),
                "",
            )
            timeline_items.append(
                {
                    "target_id": event.id,
                    "target_name": event.title,
                    "change_type": "timeline_projection",
                    "before": f"沙盘事件：{event.year} {event.title}",
                    "after": compiled or "运行态描述待生成",
                    "effect": "时间线事件已折叠为运行态描述",
                    "note": event.event_type,
                }
            )
        if timeline_items:
            sections.append({"key": "timeline", "label": "时间线投影", "items": timeline_items})

        rule_items = [
            {
                "target_id": f"rule-{index}",
                "target_name": f"规则 {index + 1}",
                "change_type": "world_rule",
                "before": rule,
                "after": rule,
                "effect": "规则已同步到运行态",
                "note": "",
            }
            for index, rule in enumerate(sandbox.world_rules)
        ]
        if rule_items:
            sections.append({"key": "rules", "label": "世界规则", "items": rule_items})

        deduped_notes = list(dict.fromkeys(auto_fix_notes))
        return {"sections": sections, "auto_fix_notes": deduped_notes}

    # ---------------------------------------------------------------- #
    # 私有编译方法                                                        #
    # ---------------------------------------------------------------- #

    def _compile_faction(self, sb_faction: Faction) -> FactionState:
        """将沙盘 Faction 转换为运行态 FactionState。"""
        # 使用 name 作为 id 保证可读性（如 id 已是有意义字符串则直接用）
        faction_id = sb_faction.id or sb_faction.name
        return FactionState(
            id=faction_id,
            name=sb_faction.name,
            description=sb_faction.description,
            territory=list(sb_faction.territory_region_ids),
            hostility_map={},  # 在第二步再填充
            is_active=True,
        )

    def _compile_region(
        self, sb_region: Region, faction_id_map: dict[str, str]
    ) -> dict[str, Any]:
        """将沙盘 Region 转换为运行态 geography 条目。"""
        # 映射 faction_ids 到运行态 id
        runtime_faction_ids = [
            faction_id_map.get(fid, fid) for fid in sb_region.faction_ids
        ]
        return {
            "id": sb_region.id,
            "name": sb_region.name,
            "region_type": sb_region.region_type,
            "terrain": sb_region.geography.terrain,
            "climate": sb_region.geography.climate,
            "special_features": sb_region.geography.special_features,
            "landmarks": sb_region.geography.landmarks,
            "primary_race": sb_region.race.primary_race,
            "culture": sb_region.civilization.culture_tags,
            "faction_ids": runtime_faction_ids,
            "alignment": sb_region.alignment.value,
            "tags": sb_region.tags,
            "notes": sb_region.notes,
        }

    def _compile_power_system(self, sb_ps: "Any") -> PowerSystem:
        """将沙盘 PowerSystem 转换为运行态 PowerSystem。"""
        levels = [
            PowerLevel(
                rank=i + 1,
                name=lv.name,
                description=lv.description,
            )
            for i, lv in enumerate(sb_ps.levels)
        ]
        return PowerSystem(
            name=sb_ps.name,
            levels=levels,
            rules=list(sb_ps.rules),
            resources=list(sb_ps.resources),
        )

    def _complete_bidirectional_relations(
        self,
        world: WorldState,
        sandbox: WorldSandboxData,
        faction_id_map: dict[str, str],
        report: PublishReport,
    ) -> None:
        """
        补全势力↔地区的双向关系：
        - 如果势力的 territory_region_ids 包含一个 region，
          则该 region 的 faction_ids 也应包含该势力（反之亦然）。
        """
        # 从 sandbox 重建地区→势力的反向映射
        region_to_factions: dict[str, list[str]] = {}
        for sb_faction in sandbox.factions:
            runtime_fid = faction_id_map.get(sb_faction.id, sb_faction.id)
            for rid in sb_faction.territory_region_ids:
                if rid not in region_to_factions:
                    region_to_factions[rid] = []
                if runtime_fid not in region_to_factions[rid]:
                    region_to_factions[rid].append(runtime_fid)

        # 补全 geography 中各 region 的 faction_ids
        for region_id, faction_ids in region_to_factions.items():
            if region_id in world.geography:
                existing = world.geography[region_id].get("faction_ids", [])
                for fid in faction_ids:
                    if fid not in existing:
                        existing.append(fid)
                world.geography[region_id]["faction_ids"] = existing

        # 补全 FactionState.territory（来自 region.faction_ids 反向推导）
        for sb_region in sandbox.regions:
            if sb_region.id not in world.geography:
                continue
            for fid in sb_region.faction_ids:
                runtime_fid = faction_id_map.get(fid, fid)
                fs = world.factions.get(runtime_fid)
                if fs and sb_region.id not in fs.territory:
                    fs.territory.append(sb_region.id)

    def _validate_power_system_refs(
        self,
        world: WorldState,
        sandbox: WorldSandboxData,
        faction_id_map: dict[str, str],
        report: PublishReport,
    ) -> None:
        """校验 region 的 power_system_id 引用合法性，不合法时产生 warning。"""
        ps_ids = {ps.id for ps in sandbox.power_systems}
        for sb_region in sandbox.regions:
            if (
                not sb_region.power_access.inherits_global
                and sb_region.power_access.custom_system_id
                and sb_region.power_access.custom_system_id not in ps_ids
            ):
                report.add_warning(
                    f"地区 '{sb_region.name}' 引用的力量体系 ID "
                    f"'{sb_region.power_access.custom_system_id}' 不存在，将忽略自定义设置"
                )
