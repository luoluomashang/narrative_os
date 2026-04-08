"""
skills/consistency.py — Phase 2: 一致性检查 Skill

检查生成文本在以下维度的一致性：
  1. 角色行为约束（BehaviorConstraint 引擎）
  2. 世界规则（WorldConsistencyChecker）
  3. 情节因果（PlotGraph 中已完成节点不可矛盾）
  4. 时序（章节编号与 timeline 不倒退）

输出结构化 ConsistencyReport，包含分类问题列表与修复建议。
注册到全局 SkillRegistry。

UI 映射：写作工作台"一致性检查"侧边栏 → 修复建议气泡
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Callable

from pydantic import BaseModel, Field

from narrative_os.skills.dsl import SkillRegistry, SkillRequest

if TYPE_CHECKING:
    from narrative_os.core.character import CharacterState
    from narrative_os.core.plot import PlotGraph
    from narrative_os.core.world import WorldState

_registry = SkillRegistry()

# ------------------------------------------------------------------ #
# LRU 缓存（模块级，所有实例共享）                                    #
# ------------------------------------------------------------------ #

_consistency_cache: "OrderedDict[str, Any]" = OrderedDict()
_CACHE_MAXSIZE = 100


def _cache_key(text: str, chapter: int, char_names: list[str]) -> str:
    payload = json.dumps(
        {"text": text[:500], "chapter": chapter, "chars": sorted(char_names)}
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class ConsistencyIssue(BaseModel):
    dimension: str          # "character" | "world" | "plot" | "timeline"
    severity: str           # "hard" | "soft" | "info"
    description: str
    suggestion: str = ""
    source_rule: str = ""
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)  # 0.0-1.0，低置信度降级为 info


class ConsistencyReport(BaseModel):
    passed: bool = True
    issues: list[ConsistencyIssue] = Field(default_factory=list)
    score: float = 1.0      # 0~1，无问题=1.0

    @property
    def hard_issues(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "hard"]

    @property
    def soft_issues(self) -> list[ConsistencyIssue]:
        return [i for i in self.issues if i.severity == "soft"]

    def summary(self) -> str:
        if self.passed:
            return f"✅ 一致性检查通过（得分 {self.score:.0%}）"
        hard_n = len(self.hard_issues)
        soft_n = len(self.soft_issues)
        return (
            f"❌ 发现 {hard_n} 个硬冲突 / {soft_n} 个软警告"
            f"（得分 {self.score:.0%}）"
        )


# ------------------------------------------------------------------ #
# ConsistencyChecker                                                    #
# ------------------------------------------------------------------ #

class ConsistencyChecker:
    """
    多维一致性检查器。

    用法：
        checker = ConsistencyChecker()
        report = checker.check(
            text="生成的场景文本...",
            characters=[hero],
            world=world_state,
            plot_graph=graph,
            chapter=3,
        )

    可接入 LLM 调用器（用于语义检查和测试 mock）：
        checker = ConsistencyChecker(llm_call=my_llm_fn)
    """

    def __init__(
        self,
        llm_call: Callable[[str], str] | None = None,
    ) -> None:
        # 默认：不调用 LLM（返回空字符串）
        self._llm_call: Callable[[str], str] = llm_call or (lambda _: "")

    # ---------------------------------------------------------------- #
    # 公共入口                                                         #
    # ---------------------------------------------------------------- #

    def check(
        self,
        text: str,
        characters: "list[CharacterState] | None" = None,
        world: "WorldState | None" = None,
        plot_graph: "PlotGraph | None" = None,
        chapter: int = 0,
    ) -> ConsistencyReport:
        char_names = [c.name for c in (characters or [])]

        # ── 缓存查找 ──────────────────────────────────────────────────
        key = _cache_key(text, chapter, char_names)
        if key in _consistency_cache:
            _consistency_cache.move_to_end(key)   # LRU 刺新
            return _consistency_cache[key]

        issues: list[ConsistencyIssue] = []

        # Dim 1: 角色行为约束（关键词快筛）
        if characters:
            issues.extend(self._check_characters(text, characters))

        # Dim 2: 世界规则
        if world is not None:
            issues.extend(self._check_world(text, world))

        # Dim 3: 情节因果（关键词预筛 → 可选 LLM）
        if plot_graph is not None:
            issues.extend(self._check_plot_semantic(text, plot_graph))

        # Dim 4: 时序（时间标记识别 → 可选 LLM）
        if chapter > 0:
            issues.extend(self._check_timeline_semantic(text, chapter))

        # ── 打分（仅计入 confidence >= 0.7 的问题） ────────────────────────
        confident_issues = [i for i in issues if i.confidence >= 0.7]
        hard_n = sum(1 for i in confident_issues if i.severity == "hard")
        soft_n = sum(1 for i in confident_issues if i.severity == "soft")
        score = max(0.0, 1.0 - hard_n * 0.3 - soft_n * 0.1)
        passed = hard_n == 0

        report = ConsistencyReport(passed=passed, issues=issues, score=round(score, 3))

        # ── 缓存写入 ──────────────────────────────────────────────────
        _consistency_cache[key] = report
        if len(_consistency_cache) > _CACHE_MAXSIZE:
            _consistency_cache.popitem(last=False)   # 移除最旧记录

        return report

    # ---------------------------------------------------------------- #
    # Dimension checkers                                                #
    # ---------------------------------------------------------------- #

    def _check_characters(
        self, text: str, characters: "list[CharacterState]"
    ) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        for char in characters:
            result = char.check_constraints(text)
            for v in result.violations:
                issues.append(ConsistencyIssue(
                    dimension="character",
                    severity=v.severity,
                    description=(
                        f"角色\u300c{char.name}\u300d行为违反约束"
                        f"\uff08'{v.rule}'\uff09\uff1a{v.action[:50]}"
                    ),
                    suggestion=v.suggestion or f"\u8bf7调整\u300c{char.name}\u300d在此处的行为\uff0c使其符合角色设定。",
                    source_rule=v.rule,
                ))
        return issues

    def _check_world(
        self, text: str, world: "WorldState"
    ) -> list[ConsistencyIssue]:
        issues: list[ConsistencyIssue] = []
        result = world.check_world_consistency(text)
        for violation_str in result.violations:
            issues.append(ConsistencyIssue(
                dimension="world",
                severity="soft",
                description=violation_str,
                suggestion="请检查与世界规则的冲突。",
                source_rule=violation_str[:50],
            ))
        return issues

    def _check_plot(
        self, text: str, graph: "PlotGraph"
    ) -> list[ConsistencyIssue]:
        """
        关键词预筛（快速，O(n)）。
        作为 _check_plot_semantic 的前置条件。
        """
        issues: list[ConsistencyIssue] = []
        NEGATION_WORDS = ["没有", "未", "不曾", "从未", "已经死去", "死了", "消失了"]

        for node_id, node in graph._nodes.items():
            if str(node.status) in ("completed", "EventStatus.completed"):
                for nw in NEGATION_WORDS:
                    for kw in node.summary.split()[:5]:
                        if len(kw) >= 2 and nw in text and kw in text:
                            text_lower = text
                            pos_nw = text_lower.find(nw)
                            pos_kw = text_lower.find(kw)
                            if 0 <= abs(pos_nw - pos_kw) < 15:
                                issues.append(ConsistencyIssue(
                                    dimension="plot",
                                    severity="soft",
                                    description=(
                                        f"文本可能与已完成情节节点「{node_id}」矛盾"
                                        f"（含否定词'{nw}'靠近关键词'{kw}'）"
                                    ),
                                    suggestion="请确认此处描述与已发生情节不冲突。",
                                    source_rule=node_id,
                                ))
                            break
        return issues

    def _check_plot_semantic(
        self, text: str, graph: "PlotGraph"
    ) -> list[ConsistencyIssue]:
        """
        关键词预筛 → LLM 语义检查（仅当预筛命中且存在已完成节点时）。
        """
        quick_hits = self._check_plot(text, graph)
        if not quick_hits:
            return []

        completed_nodes = [
            n for n in graph._nodes.values()
            if str(n.status) in ("completed", "EventStatus.completed")
        ]
        if not completed_nodes:
            return quick_hits  # 无已完成节点，跳过 LLM

        summaries = [n.summary for n in completed_nodes]
        prompt = (
            f"已完成的情节节点摘要：\n{summaries}\n\n"
            f"新生成文本：\n{text[:2000]}\n\n"
            "请检查新文本是否与已完成情节存在逻辑矛盾。\n"
            "返回 JSON 数组，每项："
            '{"description": "...", "severity": "hard|soft|info", '
            '"confidence": 0.0-1.0, "suggestion": ""}\n'
            "若无矛盾返回空数组 []."
        )
        raw_response = self._llm_call(prompt)
        semantic_issues = self._parse_llm_response(raw_response, "plot")
        return semantic_issues if semantic_issues else quick_hits

    def _check_timeline(self, text: str, chapter: int) -> list[ConsistencyIssue]:
        """关键词预筛：时序回退单词。"""
        issues: list[ConsistencyIssue] = []
        RETRO_PATTERNS = ["回到了", "时光倒流", "穿越回", "三年前的今天回来了"]
        for pat in RETRO_PATTERNS:
            if pat in text:
                issues.append(ConsistencyIssue(
                    dimension="timeline",
                    severity="soft",
                    description=f"文本含时序回退词汇'{pat}'，请确认是否为正常回忆/倒叙。",
                    suggestion="若为回忆场景，请在段首标注【回忆】以明确时序。",
                    source_rule="timeline_check",
                ))
        return issues

    def _check_timeline_semantic(
        self, text: str, chapter: int
    ) -> list[ConsistencyIssue]:
        """
        时间标记识别 → LLM 时序推理（仅当发现时间标记时）。
        """
        time_markers = re.findall(
            r'(?:\d+[\u5929\u6708\u5e74](?:\u524d|\u540e)?'
            r'|\u4e09\u5929\u540e|\u4e0a\u4e2a[\u6708\u5e74]|\u6628[\u5929\u65e5]'
            r'|\u660e[\u5929\u65e5]|\u540e\u5929|\u5927\u524d\u5929)',
            text,
        )
        if not time_markers:
            return self._check_timeline(text, chapter)

        prompt = (
            f"当前章节编号：{chapter}\n"
            f"文本中发现的时间标记：{time_markers}\n"
            f"文本片段：{text[:1500]}\n\n"
            "请判断时间标记是否形成前后矛盾。\n"
            "返回 JSON 数组，每项："
            '{"description": "...", "severity": "hard|soft|info", '
            '"confidence": 0.0-1.0, "suggestion": ""}\n'
            "若无矛盾返回 []"
        )
        raw_response = self._llm_call(prompt)
        return (
            self._parse_llm_response(raw_response, "timeline")
            or self._check_timeline(text, chapter)
        )

    # ---------------------------------------------------------------- #
    # LLM 响应解析                                                     #
    # ---------------------------------------------------------------- #

    def _parse_llm_response(
        self, response: str, dimension: str
    ) -> list[ConsistencyIssue]:
        """
        解析 LLM 返回的 JSON 字符串。
        非 JSON 时返回空列表（不抛异常）。
        低置信度 hard 问题自动降级为 info。
        """
        if not response or not response.strip():
            return []
        try:
            raw = json.loads(response.strip())
            if not isinstance(raw, list):
                return []
        except (json.JSONDecodeError, ValueError):
            return []

        issues: list[ConsistencyIssue] = []
        for item in raw:
            try:
                confidence = float(item.get("confidence", 1.0))
                severity = str(item.get("severity", "info"))
                if confidence < 0.7 and severity == "hard":
                    severity = "info"
                issues.append(ConsistencyIssue(
                    dimension=dimension,
                    severity=severity,
                    description=str(item.get("description", "")),
                    suggestion=str(item.get("suggestion", "")),
                    source_rule=f"{dimension}_llm",
                    confidence=confidence,
                ))
            except (KeyError, ValueError, TypeError):
                continue
        return issues


# ------------------------------------------------------------------ #
# SkillRegistry 注册                                                    #
# ------------------------------------------------------------------ #

_checker_instance = ConsistencyChecker()


def _consistency_handler(req: SkillRequest) -> dict[str, Any]:
    text: str = req.inputs.get("text", "")
    if not text:
        raise ValueError("consistency_check skill 需要 inputs.text")
    report = _checker_instance.check(
        text=text,
        characters=req.inputs.get("characters"),
        world=req.inputs.get("world"),
        plot_graph=req.inputs.get("plot_graph"),
        chapter=req.inputs.get("chapter", 0),
    )
    return report.model_dump()


_registry.register_fn("consistency_check", _consistency_handler)
