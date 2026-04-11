"""
core/world_validator.py — Phase 6 Stage 1: 发布前校验器

职责：
  - 校验 ID 引用完整性（地区/势力/关系/时间线实体）
  - 校验地区↔势力双向关系一致性
  - 校验 power_system 挂接合法性
  - 校验必填核心设定是否存在
  - 输出：ValidationReport(errors: list, warnings: list, suggestions: list)

作用：作为 Compile 前门禁，errors 非空时拒绝发布
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from narrative_os.core.world_sandbox import WorldSandboxData, ConceptData


# ------------------------------------------------------------------ #
# 输出数据模型                                                          #
# ------------------------------------------------------------------ #

class ValidationReport(BaseModel):
    """校验报告。errors 非空表示不可发布；warnings 为建议修复项；suggestions 为优化建议。"""
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        """无 errors 则可发布。"""
        return len(self.errors) == 0

    def add_error(self, msg: str) -> None:
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    def add_suggestion(self, msg: str) -> None:
        self.suggestions.append(msg)


# ------------------------------------------------------------------ #
# WorldValidator                                                       #
# ------------------------------------------------------------------ #

class WorldValidator:
    """
    世界数据发布前校验器。

    使用方式：
        validator = WorldValidator()
        report = validator.validate(sandbox=sandbox_data, concept=concept_data)
        if not report.is_valid:
            raise PublishError(report.errors)
    """

    def validate(
        self,
        sandbox: WorldSandboxData,
        concept: ConceptData | None = None,
    ) -> ValidationReport:
        """
        执行所有校验规则，返回 ValidationReport。

        Args:
            sandbox: 待校验的世界沙盘数据
            concept: 故事概念数据（可选，用于跨校验）

        Returns:
            ValidationReport
        """
        report = ValidationReport()

        self._check_basic_world_info(sandbox, report)
        self._check_duplicate_ids(sandbox, report)
        self._check_faction_region_refs(sandbox, report)
        self._check_relation_map_refs(sandbox, report)
        self._check_power_system_refs(sandbox, report)
        self._check_timeline_entity_refs(sandbox, report)
        self._check_bidirectional_consistency(sandbox, report)
        self._suggest_improvements(sandbox, concept, report)

        return report

    # ---------------------------------------------------------------- #
    # 校验规则                                                           #
    # ---------------------------------------------------------------- #

    def _check_basic_world_info(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """校验必填核心设定是否存在。"""
        if not sandbox.world_name or not sandbox.world_name.strip():
            report.add_error("世界名称（world_name）不能为空")

        if not sandbox.world_description or not sandbox.world_description.strip():
            report.add_warning("世界描述（world_description）为空，建议补充世界背景说明")

        if not sandbox.regions:
            report.add_warning("没有任何地区（regions），建议添加至少一个地区")

        if not sandbox.factions:
            report.add_warning("没有任何势力（factions），建议添加至少一个势力")

    def _check_duplicate_ids(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """校验 ID 唯一性。"""
        region_ids = [r.id for r in sandbox.regions]
        faction_ids = [f.id for f in sandbox.factions]
        ps_ids = [ps.id for ps in sandbox.power_systems]
        event_ids = [e.id for e in sandbox.timeline_events]

        for entity_list, entity_type in [
            (region_ids, "地区"),
            (faction_ids, "势力"),
            (ps_ids, "力量体系"),
            (event_ids, "时间线事件"),
        ]:
            seen: set[str] = set()
            for eid in entity_list:
                if eid in seen:
                    report.add_error(f"{entity_type} ID '{eid}' 重复，每个 {entity_type} 的 ID 必须唯一")
                seen.add(eid)

    def _check_faction_region_refs(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """
        校验势力的 territory_region_ids 引用完整性：
        每个引用的 region id 必须存在。
        """
        region_ids = {r.id for r in sandbox.regions}
        for faction in sandbox.factions:
            for rid in faction.territory_region_ids:
                if rid not in region_ids:
                    report.add_error(
                        f"势力 '{faction.name}'（ID: {faction.id}）的领土引用"
                        f"了不存在的地区 ID '{rid}'"
                    )

    def _check_relation_map_refs(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """
        校验势力 relation_map 中的目标 ID 是否存在。
        """
        faction_ids = {f.id for f in sandbox.factions}
        for faction in sandbox.factions:
            for target_id, value in faction.relation_map.items():
                if target_id not in faction_ids:
                    report.add_warning(
                        f"势力 '{faction.name}' 的关系图引用了不存在的势力 ID '{target_id}'，"
                        "该关系将在编译时被忽略"
                    )
                if not (-1.0 <= float(value) <= 1.0):
                    report.add_error(
                        f"势力 '{faction.name}' 对 '{target_id}' 的敌意值 {value} 超出 [-1, 1] 范围"
                    )

    def _check_power_system_refs(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """
        校验地区自定义力量体系引用合法性。
        若 region.power_access.inherits_global == False 且 custom_system_id 不为空，
        则该 ID 必须存在于 sandbox.power_systems。
        """
        ps_ids = {ps.id for ps in sandbox.power_systems}
        for region in sandbox.regions:
            if (
                not region.power_access.inherits_global
                and region.power_access.custom_system_id
            ):
                if region.power_access.custom_system_id not in ps_ids:
                    report.add_error(
                        f"地区 '{region.name}' 引用的自定义力量体系 ID "
                        f"'{region.power_access.custom_system_id}' 不存在"
                    )

    def _check_timeline_entity_refs(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """
        校验时间线事件的 linked_entity_id 引用合法性。
        linked_entity_id 应指向存在的 region.id 或 faction.id。
        """
        region_ids = {r.id for r in sandbox.regions}
        faction_ids = {f.id for f in sandbox.factions}
        valid_ids = region_ids | faction_ids

        for event in sandbox.timeline_events:
            if event.linked_entity_id and event.linked_entity_id not in valid_ids:
                report.add_warning(
                    f"时间线事件 '{event.title}'（ID: {event.id}）引用的实体 ID "
                    f"'{event.linked_entity_id}' 不存在，该关联将被忽略"
                )

    def _check_bidirectional_consistency(
        self, sandbox: WorldSandboxData, report: ValidationReport
    ) -> None:
        """
        校验地区↔势力的双向关系一致性。
        如果 region.faction_ids 包含某势力，则该势力的 territory_region_ids 应也包含该地区（反之亦然）。
        产生 warning（不是 error，编译时会自动补全）。
        """
        region_id_to_factions: dict[str, set[str]] = {}
        for region in sandbox.regions:
            region_id_to_factions[region.id] = set(region.faction_ids)

        for faction in sandbox.factions:
            for rid in faction.territory_region_ids:
                if rid in region_id_to_factions:
                    if faction.id not in region_id_to_factions[rid]:
                        report.add_warning(
                            f"势力 '{faction.name}' 声明领土包含地区 '{rid}'，"
                            f"但地区的 faction_ids 未包含该势力，编译时将自动补全"
                        )

        for region in sandbox.regions:
            for fid in region.faction_ids:
                faction = next((f for f in sandbox.factions if f.id == fid), None)
                if faction and region.id not in faction.territory_region_ids:
                    report.add_warning(
                        f"地区 '{region.name}' 声明属于势力 '{faction.name}'，"
                        f"但该势力的 territory_region_ids 未包含此地区，编译时将自动补全"
                    )

    def _suggest_improvements(
        self,
        sandbox: WorldSandboxData,
        concept: ConceptData | None,
        report: ValidationReport,
    ) -> None:
        """给出优化建议。"""
        if not sandbox.power_systems:
            report.add_suggestion(
                "未定义任何力量体系（power_systems），"
                "如果故事有修炼/魔法/异能系统，建议添加"
            )

        if not sandbox.world_rules:
            report.add_suggestion("未定义世界绝对规则（world_rules），建议补充至少 1-3 条世界基础法则")

        if len(sandbox.factions) > 0 and not any(
            f.relation_map for f in sandbox.factions
        ):
            report.add_suggestion("所有势力均未定义相互关系（relation_map），建议补充势力间的关系")

        if not sandbox.timeline_events:
            report.add_suggestion("未添加任何历史事件（timeline_events），建议补充世界历史背景")

        if concept and concept.one_sentence and not sandbox.world_name:
            # 已有概念但世界名为空是一种不一致，但 world_name 校验在 _check_basic_world_info 已处理
            pass
