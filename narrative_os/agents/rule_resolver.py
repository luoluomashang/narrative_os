"""
agents/rule_resolver.py — Phase 3: 世界裁定层

玩家行动经三层校验后再生成 DM 回应：
  1. 世界规则检查（力量体系等级/禁忌/地区限制）
  2. 角色状态校验（体力/情绪/位置可行性）
  3. 势力关系影响预估（此行动的势力后果）

输出 RuleResolutionResult：
  allowed: bool — 是否允许执行
  modified_action: str — 修正后的行动描述（与原文不同时表示规则调整）
  world_consequence: str — 世界后果预估
  warnings: list[str] — 提示用户的警告信息
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from narrative_os.execution.prompt_utils import json_object_contract, parse_json_response

if TYPE_CHECKING:
    from narrative_os.core.character import CharacterState
    from narrative_os.core.world import WorldState


# ------------------------------------------------------------------ #
# 输出模型                                                               #
# ------------------------------------------------------------------ #

class RuleResolutionResult(BaseModel):
    """裁定结果。"""
    allowed: bool = True
    modified_action: str = ""          # 修正后的行动（与原 user_action 不同则说明规则调整了）
    world_consequence: str = ""        # 世界后果预估（1-2 句）
    warnings: list[str] = Field(default_factory=list)
    blocked_reason: str = ""           # 被阻止时的原因（allowed=False）


# ------------------------------------------------------------------ #
# RuleResolver                                                         #
# ------------------------------------------------------------------ #

class RuleResolver:
    """
    世界裁定器。
    调用 resolve() 对玩家行动进行三层校验。
    优先使用 LLM 校验，失败时降级为规则关键词匹配。
    """

    async def resolve(
        self,
        user_action: str,
        actor_character: "CharacterState",
        world_state: "WorldState | None",
        lorebook: list | None = None,
    ) -> RuleResolutionResult:
        """
        执行三层规则校验。

        Args:
            user_action: 玩家的行动描述
            actor_character: 执行角色（CharacterState）
            world_state: 当前世界状态
            lorebook: 世界书条目（Phase 4 接入，此阶段为 None）

        Returns:
            RuleResolutionResult
        """
        # Layer 1: 角色约束硬校验（不依赖 LLM）
        constraint_result = actor_character.check_constraints(user_action)
        if not constraint_result.passed:
            hard_violations = [v for v in constraint_result.violations if v.severity == "hard"]
            if hard_violations:
                return RuleResolutionResult(
                    allowed=False,
                    modified_action=user_action,
                    world_consequence="",
                    warnings=[v.suggestion for v in hard_violations],
                    blocked_reason=f"角色约束阻止：{hard_violations[0].rule}",
                )

        # Layer 2: 世界规则检查（LLM 优先，关键词降级）
        world_check = self._check_world_rules(user_action, world_state)
        if world_check is not None:
            return world_check

        # Layer 3: LLM 综合裁定（势力关系+规则+修正）
        try:
            return await self._llm_resolve(user_action, actor_character, world_state, lorebook)
        except Exception:
            # LLM 不可用时，放行并附加提示
            return RuleResolutionResult(
                allowed=True,
                modified_action=user_action,
                world_consequence="（裁定系统暂时不可用，已默认放行）",
                warnings=[],
            )

    def _check_world_rules(
        self,
        user_action: str,
        world_state: "WorldState | None",
    ) -> RuleResolutionResult | None:
        """Layer 2 关键词世界规则检查，匹配到禁忌则阻止。"""
        if world_state is None:
            return None

        # 检查世界禁忌规则（rules_of_world 中含"禁止"/"不得"等的条目）
        action_lower = user_action.lower()
        for rule in world_state.rules_of_world:
            rule_lower = rule.lower()
            # 判断规则中是否含禁止前缀
            is_prohibition = any(
                kw in rule_lower for kw in ["禁止", "不得", "严禁", "不可"]
            )
            if not is_prohibition:
                continue
            # 提取禁止的关键词（去掉前缀）
            for prefix in ["禁止", "不得", "严禁", "不可"]:
                if prefix in rule_lower:
                    keyword = rule_lower.replace(prefix, "", 1).strip()
                    if keyword and keyword in action_lower:
                        return RuleResolutionResult(
                            allowed=False,
                            modified_action=user_action,
                            world_consequence="",
                            warnings=[f"此行动违反世界规则：{rule}"],
                            blocked_reason=f"世界规则禁止：{rule}",
                        )

        return None

    async def _llm_resolve(
        self,
        user_action: str,
        actor_character: "CharacterState",
        world_state: "WorldState | None",
        lorebook: list | None,
    ) -> RuleResolutionResult:
        """Layer 3: LLM 综合裁定。"""
        from narrative_os.execution.llm_router import LLMRequest, LLMRouter, ModelTier

        world_rules_text = "无"
        factions_text = "无"
        power_system = "无"
        if world_state is not None:
            world_rules_text = "；".join(world_state.rules_of_world[:5]) or "无"
            factions_text = "、".join(list(world_state.factions.keys())[:5]) or "无"
            power_system = world_state.power_system.name if world_state.power_system else "无"

        char_status = (
            f"角色「{actor_character.name}」"
            f"（情绪={actor_character.emotion}，"
            f"生命力={actor_character.health:.0%}，"
            f"所属势力={actor_character.faction or '无'}）"
        )

        prompt = "\n\n".join(
            [
                "你是一个 TRPG 世界裁定系统，判断玩家行动是否在世界规则内可执行。",
                "\n".join(
                    [
                        f"角色状态：{char_status}",
                        f"行动描述：{user_action}",
                        f"世界规则（前5条）：{world_rules_text}",
                        f"活跃势力：{factions_text}",
                        f"力量体系：{power_system}",
                    ]
                ),
                json_object_contract(
                    '{"allowed": true/false, "modified_action": "修正后行动（与原文相同则复制）", "world_consequence": "世界后果（1句）", "warnings": ["警告1"], "blocked_reason": "阻止原因（allowed=false时填写）"}'
                ),
            ]
        )

        router = LLMRouter()
        req = LLMRequest(
            task_type="rule_resolution",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.3,
            skill_name="rule_resolver",
            tier_override=ModelTier.SMALL,
        )
        resp = await router.call(req)
        raw = resp.content.strip()

        try:
            data = parse_json_response(raw, expect="object")
            if not isinstance(data, dict):
                raise ValueError("invalid resolver payload")
            return RuleResolutionResult(
                allowed=bool(data.get("allowed", True)),
                modified_action=str(data.get("modified_action", user_action)),
                world_consequence=str(data.get("world_consequence", "")),
                warnings=[str(w) for w in data.get("warnings", [])],
                blocked_reason=str(data.get("blocked_reason", "")),
            )
        except Exception:
            # JSON 解析失败 — 放行
            return RuleResolutionResult(
                allowed=True,
                modified_action=user_action,
                world_consequence="（裁定系统响应异常，已默认放行）",
                warnings=[],
            )
