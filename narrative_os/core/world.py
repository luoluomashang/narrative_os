"""
core/world.py — Phase 1: WorldState（世界状态系统）

一级核心模块（与 CharacterState 平级，不附属于 Memory）。

核心特性：
  1. FactionState — 势力状态（含 hidden_plans，Sandbox Backend）
  2. WorldState — 世界状态（势力/力量体系/地理/时间线/规则）
  3. advance_timeline() — 时间轴推进
  4. get_sandbox_backend() — 推演离屏势力行动（反派未出现时的幕后行动）
  5. check_world_consistency() — 世界观一致性校验

UI 映射：世界观拓扑 + 星空图（向量设定沉淀）
"""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


# ------------------------------------------------------------------ #
# Sub-models                                                            #
# ------------------------------------------------------------------ #

class TimelineEvent(BaseModel):
    """世界时间线上的一个事件。"""
    id: str
    chapter: int
    description: str
    affected_factions: list[str] = Field(default_factory=list)
    affected_characters: list[str] = Field(default_factory=list)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class PowerLevel(BaseModel):
    """力量等级体系的一个层级（如：炼气期 / 筑基期 / 金丹期）。"""
    rank: int                 # 等级数字（越大越强）
    name: str                 # 等级名称
    description: str = ""


class PowerSystem(BaseModel):
    """世界力量体系（仅在含修炼/异能/科幻时初始化）。"""
    name: str = ""
    levels: list[PowerLevel] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)  # 力量规则（如"气血耗尽则死"）
    resources: list[str] = Field(default_factory=list)  # 资源（丹药/法宝/能源）


class FactionState(BaseModel):
    """
    势力状态 Pydantic V2 模型。

    hostility_map: {faction_id: -1.0(盟友) ~ 1.0(死敌)} 
    hidden_plans: Sandbox Backend — 离屏行动计划（反派/势力的幕后操作）
    """
    id: str
    name: str
    description: str = ""
    leader: str = ""
    members: list[str] = Field(default_factory=list)
    hostility_map: dict[str, float] = Field(default_factory=dict)
    territory: list[str] = Field(default_factory=list)
    resources: dict[str, float] = Field(default_factory=dict)
    hidden_plans: list[str] = Field(default_factory=list)   # Sandbox Backend
    is_active: bool = True

    model_config = {"frozen": False}

    def update_hostility(self, target_faction_id: str, value: float) -> None:
        """设置对另一势力的敌意值（钳制到 -1~1）。"""
        self.hostility_map[target_faction_id] = max(-1.0, min(1.0, value))

    def add_hidden_plan(self, plan: str) -> None:
        """Sandbox Backend：添加离屏行动计划。"""
        self.hidden_plans.append(plan)

    def pop_hidden_plans(self) -> list[str]:
        """取出并清空所有离屏计划（触发 Maintenance Agent 执行）。"""
        plans = list(self.hidden_plans)
        self.hidden_plans.clear()
        return plans


# ------------------------------------------------------------------ #
# WorldState                                                            #
# ------------------------------------------------------------------ #

class WorldState(BaseModel):
    """
    世界状态 Pydantic V2 模型。

    rules_of_world: 世界绝对规则（如"法术在结界内无效"）
    — 用于 Consistency Checker 的硬校验
    """
    factions: dict[str, FactionState] = Field(default_factory=dict)
    power_system: PowerSystem = Field(default_factory=PowerSystem)
    geography: dict[str, Any] = Field(default_factory=dict)
    timeline: list[TimelineEvent] = Field(default_factory=list)
    resources: dict[str, Any] = Field(default_factory=dict)
    rules_of_world: list[str] = Field(default_factory=list)  # 绝对规则（硬约束）
    current_chapter: int = 0
    current_volume: int = 1

    # 版本快照历史
    snapshot_history: list[dict[str, Any]] = Field(default_factory=list)

    model_config = {"frozen": False}

    # ---------------------------------------------------------------- #
    # Mutations                                                         #
    # ---------------------------------------------------------------- #

    def add_faction(
        self,
        faction_or_name: "FactionState | str",
        *,
        hostility_map: dict[str, float] | None = None,
        **kwargs: Any,
    ) -> "FactionState":
        """
        添加势力。支持两种调用方式:
          world.add_faction(FactionState(...))               → 对象方式
          world.add_faction("九天宗", hostility_map={...})  → 工厂方式
        """
        if isinstance(faction_or_name, str):
            faction = FactionState(
                id=faction_or_name,
                name=faction_or_name,
                hostility_map=hostility_map or {},
                **kwargs,
            )
        else:
            faction = faction_or_name
        if faction.id in self.factions:
            raise ValueError(f"Faction '{faction.id}' 已存在")
        self.factions[faction.id] = faction
        return faction

    def update_faction(self, faction_id: str, **kwargs: Any) -> None:
        """更新势力属性。"""
        if faction_id not in self.factions:
            raise KeyError(f"Faction '{faction_id}' not found")
        faction = self.factions[faction_id]
        for k, v in kwargs.items():
            if hasattr(faction, k):
                setattr(faction, k, v)

    def advance_timeline(
        self,
        event_or_chapter: "TimelineEvent | int",
        event: str = "",
        **kwargs: Any,
    ) -> "TimelineEvent":
        """
        推进时间轴，记录一个世界事件。支持两种调用方式:
          world.advance_timeline(TimelineEvent(...))         → 对象方式
          world.advance_timeline(chapter=1, event="...")    → 工厂方式
        """
        import uuid as _uuid
        if isinstance(event_or_chapter, int):
            te = TimelineEvent(
                id=str(_uuid.uuid4()),
                chapter=event_or_chapter,
                description=event,
                **kwargs,
            )
        else:
            te = event_or_chapter
        self.timeline.append(te)
        self.current_chapter = max(self.current_chapter, te.chapter)
        return te

    def add_world_rule(self, rule: str) -> None:
        """添加世界绝对规则（供 Consistency Checker 硬校验）。"""
        if rule not in self.rules_of_world:
            self.rules_of_world.append(rule)

    # ---------------------------------------------------------------- #
    # Sandbox Backend — 离屏势力推演                                   #
    # ---------------------------------------------------------------- #

    def get_sandbox_backend(self) -> dict[str, list[str]]:
        """
        返回所有势力的离屏行动计划（Sandbox Backend）。
        Maintenance Agent 在每章末尾调用，推演反派/势力的幕后操作。

        示例返回：
            {"dark_sect": ["暗中联络境外势力", "派刺客潜入主角所在城市"]}
        """
        return {
            fid: faction.hidden_plans
            for fid, faction in self.factions.items()
            if faction.hidden_plans
        }

    def execute_sandbox_plans(self, faction_id: str) -> list[str]:
        """执行并清空某势力的离屏计划（返回计划列表）。"""
        if faction_id not in self.factions:
            return []
        return self.factions[faction_id].pop_hidden_plans()

    # ---------------------------------------------------------------- #
    # Consistency Check                                                 #
    # ---------------------------------------------------------------- #

    def check_world_consistency(self, event_description: str) -> "WorldConsistencyResult":
        """
        检查事件描述是否违反世界绝对规则。
        Consistency Checker 调用此方法进行硬校验。
        """
        violations: list[str] = []
        event_lower = event_description.lower()
        for rule in self.rules_of_world:
            # 提取规则中明确禁止的关键词（简单关键词匹配，Phase 2 升级到语义匹配）
            rule_keywords = _extract_rule_keywords(rule)
            if rule_keywords and any(kw in event_lower for kw in rule_keywords):
                violations.append(f"违反世界规则：{rule}")
        return WorldConsistencyResult(violations=violations, passed=len(violations) == 0)

    # ---------------------------------------------------------------- #
    # Snapshot / Rollback                                               #
    # ---------------------------------------------------------------- #

    def snapshot(self, chapter: int) -> dict[str, Any]:
        """打版本快照，每章由 Maintenance Agent 调用。"""
        snap = {
            "chapter": chapter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "faction_count": len(self.factions),
            "timeline_length": len(self.timeline),
            "current_volume": self.current_volume,
            "timeline_snapshot": deepcopy(self.timeline),
            "faction_hostilities": {
                fid: deepcopy(f.hostility_map)
                for fid, f in self.factions.items()
            },
        }
        self.snapshot_history.append(snap)
        return snap

    def rollback_to_chapter(self, chapter: int) -> bool:
        """
        回滚到指定章节快照（时光倒流）。
        恢复 timeline 和 faction hostilities。
        """
        target = next((s for s in reversed(self.snapshot_history) if s["chapter"] == chapter), None)
        if target is None:
            raise KeyError(f"未找到第 {chapter} 章的世界快照")
        # 恢复 timeline
        self.timeline = deepcopy(target.get("timeline_snapshot", []))
        # 恢复 faction hostilities
        for fid, hostility_map in target.get("faction_hostilities", {}).items():
            if fid in self.factions:
                self.factions[fid].hostility_map = deepcopy(hostility_map)
        # 截断快照历史
        self.snapshot_history = [s for s in self.snapshot_history if s["chapter"] <= chapter]
        return True

    # ---------------------------------------------------------------- #
    # Serialization                                                      #
    # ---------------------------------------------------------------- #

    def to_json(self, path: str | Path | None = None) -> str:
        s = self.model_dump_json(indent=2)
        if path:
            Path(path).write_text(s, encoding="utf-8")
        return s

    @classmethod
    def from_json(cls, path: str | Path) -> "WorldState":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def to_dict(self) -> dict[str, Any]:
        return json.loads(self.model_dump_json())

    def __repr__(self) -> str:
        return (
            f"WorldState(factions={len(self.factions)}, "
            f"timeline={len(self.timeline)}, chapter={self.current_chapter})"
        )


# ------------------------------------------------------------------ #
# Consistency Check Result                                             #
# ------------------------------------------------------------------ #

class WorldConsistencyResult(BaseModel):
    violations: list[str] = Field(default_factory=list)
    passed: bool = True

    @property
    def consistent(self) -> bool:
        """Alias for `passed` — True when no violations found."""
        return self.passed


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _extract_rule_keywords(rule: str) -> list[str]:
    """
    从世界规则文本中提取关键词，用于简单违规检测。
    例：「修士不得伤害凡人」→ ["伤害", "凡人"]
    Phase 2 升级为 LLM 语义理解。
    简化策略：去除常见规范性词汇后，提取剩余的有意义词组。
    """
    stop_words = {"修士", "不得", "不能", "禁止", "必须", "不可", "严禁",
                  "应当", "需要", "不", "得", "应", "须", "的", "了", "是",
                  "在", "与", "和", "之", "对", "等", "及", "将", "已", "宜"}
    # 逐步替换停用词为空格，将规则分割为关键词
    cleaned = rule
    for sw in sorted(stop_words, key=len, reverse=True):  # 先替换长词
        cleaned = cleaned.replace(sw, " ")
    # 提取2字以上的词段
    keywords = [t.strip() for t in cleaned.split() if len(t.strip()) >= 1]
    # 也提取原规则中2字组合
    for i in range(len(rule) - 1):
        bigram = rule[i:i+2]
        skip = any(bigram == sw or any(c in sw for c in bigram for sw in stop_words) for sw in stop_words)
        if not skip and bigram not in stop_words:
            keywords.append(bigram)
    # Deduplicate
    seen: set[str] = set()
    result = []
    for kw in keywords:
        if kw and kw not in seen:
            seen.add(kw)
            result.append(kw)
    return result
