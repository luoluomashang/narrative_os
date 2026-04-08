"""
core/character.py — Phase 1: CharacterState（角色状态机）

核心特性：
  1. behavior_constraints 约束规则引擎（代码硬校验，不依赖 LLM）
  2. snapshot_history 版本控制（支持回滚）
  3. voice_fingerprint 人物口吻指纹（对话生成参考）
  4. arc_stage 弧光阶段追踪

UI 映射：雷达图 / Visual Rule Builder（IF-THEN-NEVER 约束面板）/ 关系力导向图
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

class ArcStage(str):
    """弧光阶段（来自 planning 模块 5 阶段弧线）。"""
    DEFENSIVE = "防御"        # 阶段1：防御/否认
    CRACKING = "裂缝"         # 阶段2：信念出现裂缝
    COMPENSATING = "代偿"     # 阶段3：代偿/挣扎
    ACCEPTING = "承认"        # 阶段4：承认/改变
    TRANSFORMED = "改变"      # 阶段5：完成转变


class BehaviorConstraint(BaseModel):
    """
    行为约束规则（硬约束，Critic Agent 必须校验）。

    示例：
        BehaviorConstraint(rule="不能主动认输", severity="hard")
        BehaviorConstraint(rule="必须保持高冷", severity="soft")
    """
    rule: str
    severity: str = "hard"   # "hard" | "soft"
    context: str = ""         # 适用上下文描述（如"战斗场景"）

    model_config = {"frozen": True}


class VoiceFingerprint(BaseModel):
    """
    角色口吻指纹 — 5 维（来自 kb_template.json character.voice_fingerprint）。
    用于对话生成时的风格约束。
    """
    under_pressure: str = ""      # 高压/被逼时的说话风格
    when_lying: str = ""          # 撒谎时的话语特征
    deflection: str = ""          # 回避话题时的习惯表达
    emotional_peak: str = ""      # 情绪高峰时的爆发模式
    default_length: str = "medium"  # short / medium / long


class MemoryEntry(BaseModel):
    """角色个人记忆条目。"""
    chapter: int
    event: str
    emotion: str = ""
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ------------------------------------------------------------------ #
# CharacterState                                                        #
# ------------------------------------------------------------------ #

class CharacterState(BaseModel):
    """
    角色状态机 Pydantic V2 模型。

    每章生成后通过 snapshot() 打版本号，存入 snapshot_history。
    """
    name: str
    traits: list[str] = Field(default_factory=list)
    goal: str = ""
    backstory: str = ""

    # 动态状态（可变）
    emotion: str = "平静"
    health: float = Field(default=1.0, ge=0.0, le=1.0)
    relationships: dict[str, float] = Field(default_factory=dict)  # {角色名: 好感度 -1~1}

    # 弧光阶段
    arc_stage: str = ArcStage.DEFENSIVE

    # 记忆（事件记录）
    memory: list[MemoryEntry] = Field(default_factory=list)

    # 约束规则引擎
    behavior_constraints: list[BehaviorConstraint] = Field(default_factory=list)

    # 口吻指纹
    voice_fingerprint: VoiceFingerprint = Field(default_factory=VoiceFingerprint)

    # 版本快照历史（每章一个）
    snapshot_history: list[dict[str, Any]] = Field(default_factory=list)

    # 元数据
    faction: str = ""
    is_alive: bool = True
    chapter_introduced: int = 1

    model_config = {"frozen": False}

    # ---------------------------------------------------------------- #
    # Mutations                                                         #
    # ---------------------------------------------------------------- #

    def update_emotion(self, emotion: str) -> None:
        """更新情绪状态。"""
        self.emotion = emotion

    def update_relationship(self, character_name: str, delta: float) -> None:
        """
        更新与另一角色的关系值（累加），钳制到 -1.0 ~ 1.0。
        """
        current = self.relationships.get(character_name, 0.0)
        self.relationships[character_name] = max(-1.0, min(1.0, current + delta))

    def record_event(self, chapter: int, event: str, emotion: str = "", importance: float = 0.5) -> None:
        """记录一条事件记忆。"""
        self.memory.append(
            MemoryEntry(chapter=chapter, event=event, emotion=emotion, importance=importance)
        )

    def set_arc_stage(self, stage: str) -> None:
        self.arc_stage = stage

    def kill(self) -> None:
        self.is_alive = False

    # ---------------------------------------------------------------- #
    # Constraint Engine (硬校验)                                       #
    # ---------------------------------------------------------------- #

    def check_constraints(self, action_description: str) -> "ConstraintCheckResult":
        """
        硬校验：给定一段行为描述，检查是否违反 behavior_constraints。

        Critic Agent 通过此方法进行 OOC 检测（不依赖 LLM 软判断）。
        返回 ConstraintCheckResult，包含违反列表。
        """
        violations: list[ConstraintViolation] = []
        for constraint in self.behavior_constraints:
            if constraint.severity == "hard":
                # 简单关键词匹配（Phase 2 接 LLM 后升级为语义匹配）
                rule_keywords = _extract_keywords(constraint.rule)
                action_lower = action_description.lower()
                if any(kw in action_lower for kw in rule_keywords):
                    violations.append(
                        ConstraintViolation(
                            rule=constraint.rule,
                            severity=constraint.severity,
                            action=action_description,
                            suggestion=f"请修改行为，不违反约束「{constraint.rule}」",
                        )
                    )
        # Also check soft constraints
        for constraint in self.behavior_constraints:
            if constraint.severity == "soft":
                rule_keywords = _extract_keywords(constraint.rule)
                action_lower = action_description.lower()
                if any(kw in action_lower for kw in rule_keywords):
                    violations.append(
                        ConstraintViolation(
                            rule=constraint.rule,
                            severity=constraint.severity,
                            action=action_description,
                            suggestion=f"建议修改行为，避免违反软约束「{constraint.rule}」",
                        )
                    )
        return ConstraintCheckResult(
            character=self.name,
            violations=violations,
            passed=len(violations) == 0,
        )

    # ---------------------------------------------------------------- #
    # Snapshot / Rollback                                               #
    # ---------------------------------------------------------------- #

    def snapshot(self, chapter: int) -> dict[str, Any]:
        """
        打版本快照（存入 snapshot_history）。
        每章生成完成后由 Maintenance Agent 调用。
        """
        snap = {
            "chapter": chapter,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "emotion": self.emotion,
            "health": self.health,
            "relationships": deepcopy(self.relationships),
            "arc_stage": self.arc_stage,
            "is_alive": self.is_alive,
            "memory_count": len(self.memory),
        }
        self.snapshot_history.append(snap)
        return snap

    def rollback_to_chapter(self, chapter: int) -> bool:
        """
        回滚到指定章节的快照状态。
        返回 True 表示回滚成功，False 表示未找到对应快照。
        """
        target = next((s for s in reversed(self.snapshot_history) if s["chapter"] == chapter), None)
        if target is None:
            raise KeyError(f"未找到第 {chapter} 章的快照")
        self.emotion = target["emotion"]
        self.health = target["health"]
        self.relationships = deepcopy(target["relationships"])
        self.arc_stage = target["arc_stage"]
        self.is_alive = target["is_alive"]
        # 截断 memory 到该章节
        self.memory = [m for m in self.memory if m.chapter <= chapter]
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
    def from_json(cls, path: str | Path) -> "CharacterState":
        return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))

    def advance_arc(self) -> None:
        """将弧光阶段推进到下一阶段。"""
        stages = [
            ArcStage.DEFENSIVE, ArcStage.CRACKING,
            ArcStage.COMPENSATING, ArcStage.ACCEPTING, ArcStage.TRANSFORMED,
        ]
        if self.arc_stage in stages:
            idx = stages.index(self.arc_stage)
            if idx < len(stages) - 1:
                self.arc_stage = stages[idx + 1]

    def get_arc_progression(self) -> dict[str, Any]:
        """返回弧光进展摘要（供 Planner Agent 参考）。"""
        stages = [
            ArcStage.DEFENSIVE, ArcStage.CRACKING,
            ArcStage.COMPENSATING, ArcStage.ACCEPTING, ArcStage.TRANSFORMED,
        ]
        idx = stages.index(self.arc_stage) if self.arc_stage in stages else 0
        return {
            "character": self.name,
            "current_stage": self.arc_stage,
            "current_stage_name": self.arc_stage,
            "progress_pct": round((idx + 1) / len(stages) * 100),
            "completed_stages": stages[:idx],
            "progress": f"{idx + 1}/5",
            "next_stage": stages[idx + 1] if idx < 4 else "完成",
        }

    def __repr__(self) -> str:
        return f"CharacterState(name={self.name!r}, emotion={self.emotion!r}, arc={self.arc_stage!r})"


# ------------------------------------------------------------------ #
# Constraint Check Result                                              #
# ------------------------------------------------------------------ #

class ConstraintViolation(BaseModel):
    rule: str
    severity: str
    action: str
    suggestion: str = ""


class ConstraintCheckResult(BaseModel):
    character: str
    violations: list[ConstraintViolation] = Field(default_factory=list)
    passed: bool = True

    @property
    def violated(self) -> bool:
        """True when at least one constraint was violated."""
        return not self.passed

    def to_issue_list(self) -> list[str]:
        return [f"[OOC][{v.severity}] {self.character}: 违反约束「{v.rule}」" for v in self.violations]


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

def _extract_keywords(rule: str) -> list[str]:
    """
    从规则文本提取匹配关键词（Phase 2 接 LLM 后替换为语义匹配）。
    示例："不能主动认输" → ["认输", "放弃", "投降"]
         "不出卖同伴"   → ["出卖", "出卖同伴", "背叛", "告密"]
         "无谓杀戮"     → ["杀戮", "乱杀", "滥杀"]
    """
    # 当前实现：简单分词 + 近义词映射（Phase 2 接 LLM 后替换为语义匹配）
    _synonyms: dict[str, list[str]] = {
        "认输": ["认输", "放弃", "投降", "服软", "妥协"],
        "高冷": ["卑微", "讨好", "殷勤", "热情过度"],
        "复仇": ["原谅", "放过", "善待"],
        "出卖": ["出卖", "背叛", "告密", "出售", "出卖同伴", "抛弃队友", "告知敌"],
        "同伴": ["同伴", "队友", "战友", "伙伴", "兄弟"],
        "杀戮": ["杀戮", "乱杀", "滥杀", "随意杀", "残杀"],
        "伤害": ["伤害", "攻击", "残害", "加害"],
        "怯懦": ["逃跑", "退缩", "临阵脱逃", "抛弃"],
        "抛弃": ["抛弃", "丢下", "遗弃", "放弃", "逃跑"],
    }
    keywords: list[str] = []
    for key, syns in _synonyms.items():
        if key in rule:
            keywords.extend(syns)
    if not keywords:
        # fallback: 去掉否定前缀词，提取核心关键词
        cleaned = rule
        for neg in ["不出卖", "不能", "必须", "不得", "不可", "禁止", "严禁"]:
            cleaned = cleaned.replace(neg, "")
        # 提取2字以上词组
        cleaned = cleaned.strip()
        if len(cleaned) >= 2:
            keywords.append(cleaned)
            # Also add 2-char substrings
            for i in range(len(cleaned) - 1):
                keywords.append(cleaned[i:i+2])
        # Direct action keywords from original rule (without negation prefix)
        original_stripped = rule
        for prefix in ["不出卖", "不能", "不得", "不可", "不"]:
            if original_stripped.startswith(prefix):
                original_stripped = original_stripped[len(prefix):]
                keywords.append(original_stripped)
                break
    return [kw.lower() for kw in keywords if kw]
