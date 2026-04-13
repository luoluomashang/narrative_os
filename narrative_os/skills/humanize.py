"""
skills/humanize.py — Phase 2: 去 AI 味 / 人味注入 Skill（Humanizer）

功能：
  - 加载 style_rules.yaml + human_touch_rules.yaml 构建规则 prompt
  - 调用 LLMRouter 对生成文本做后处理（去机器感、注入人味）
  - 输出 HumanizeOutput（改写后文本 / 修改摘要 / 改写率）
  - 支持"仅返回 diff"模式（给 UI 渲染 before/after 对比）
  - 注册到全局 SkillRegistry

UI 映射：写作工作台"人味润色"按钮 → before/after 对比面板
"""

from __future__ import annotations

import asyncio
import difflib
import re
from typing import Any

from pydantic import BaseModel, Field

from narrative_os.execution.llm_router import (
    LLMRequest,
    LLMRouter,
    ModelTier,
    RoutingStrategy,
    get_default_routing_strategy,
)
from narrative_os.execution.prompt_utils import plain_text_contract
from narrative_os.infra.config import load_yaml
from narrative_os.skills.dsl import SkillRegistry, SkillRequest

_registry = SkillRegistry()


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class HumanizeOutput(BaseModel):
    original_text: str
    humanized_text: str
    change_ratio: float = 0.0      # 0~1，改写比例（字符级 diff）
    applied_rules: list[str] = Field(default_factory=list)
    model_used: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def word_count_delta(self) -> int:
        orig_wc = len(re.sub(r"\s", "", self.original_text))
        new_wc = len(re.sub(r"\s", "", self.humanized_text))
        return new_wc - orig_wc


# ------------------------------------------------------------------ #
# Humanizer                                                             #
# ------------------------------------------------------------------ #

class Humanizer:
    """
    文本人味化处理器。

    用法：
        h = Humanizer()
        output = await h.humanize(text)
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()
        self._system_prompt: str | None = None

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def humanize(
        self,
        text: str,
        style_focus: list[str] | None = None,
        strategy: RoutingStrategy = get_default_routing_strategy(),
    ) -> HumanizeOutput:
        """
        对文本进行人味化改写。
        style_focus: 可选，指定重点规则名（如 ["对话去AI化", "高潮节奏加速"]）
        """
        system = self._get_system_prompt(style_focus)
        user_msg = self._build_user_message(text)

        llm_req = LLMRequest(
            task_type="humanization",
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            strategy=strategy,
            tier_override=ModelTier.MEDIUM,
            max_tokens=int(len(text) * 2.5) + 512,
            temperature=0.65,
            skill_name="humanizer",
        )
        resp = await self._router.call(llm_req)
        humanized = self._extract_output(resp.content, text)
        ratio = self._calc_change_ratio(text, humanized)
        applied = self._list_applied_rules(style_focus)

        return HumanizeOutput(
            original_text=text,
            humanized_text=humanized,
            change_ratio=ratio,
            applied_rules=applied,
            model_used=resp.model_used,
        )

    # ---------------------------------------------------------------- #
    # Helpers                                                           #
    # ---------------------------------------------------------------- #

    def _get_system_prompt(self, focus: list[str] | None) -> str:
        if self._system_prompt and not focus:
            return self._system_prompt

        try:
            style = load_yaml("style_rules")
        except FileNotFoundError:
            style = {}
        try:
            human_touch = load_yaml("human_touch_rules")
        except FileNotFoundError:
            human_touch = {}

        lines = [
            "你是一位专业的中文网文润色编辑。",
            "你的任务是对下面的文本进行「去AI味、注入人味」的改写，",
            "保持原有情节内容不变，但文字更自然、更有生命力、更符合手机端网文阅读习惯。\n",
            "## 核心目标",
            style.get("core_goal", "")[:300],
            "",
        ]

        # 精选规则
        directives = style.get("style_directives", [])
        if focus:
            directives = [d for d in directives if d.get("name", "") in focus] or directives

        lines.append("## 必须遵守的风格规则（每条都要体现）")
        for d in directives[:8]:
            if isinstance(d, dict):
                name = d.get("name", "")
                content = d.get("content", "")[:200]
                lines.append(f"- **{name}**：{content}")

        # human_touch 核心哲学
        philosophy = human_touch.get("core_philosophy", "")
        if philosophy:
            lines.extend([
                "",
                "## 人味注入核心哲学",
                str(philosophy)[:400],
            ])

        lines.extend([
            "",
            plain_text_contract(
                "直接输出改写后的文本，不要加任何说明或前置语句。",
                "保持原文字数大致相当（允许 ±20%）。",
                "改写后文本必须是完整的，不得截断。",
            ),
        ])

        prompt = "\n".join(lines)
        if not focus:
            self._system_prompt = prompt  # 缓存通用提示
        return prompt

    def _build_user_message(self, text: str) -> str:
        return f"请对以下文本进行人味化改写：\n\n---\n{text}\n---"

    @staticmethod
    def _extract_output(raw: str, fallback: str) -> str:
        """从 LLM 输出中提取改写正文（去掉可能的前置说明）。"""
        # 去掉常见前缀
        PREFIXES = ["改写后：", "润色后：", "以下是改写", "改写结果：", "---\n"]
        result = raw.strip()
        for p in PREFIXES:
            if result.startswith(p):
                result = result[len(p):].strip()
        # 如果 LLM 返回空或极短，退回原文
        if len(result) < len(fallback) * 0.3:
            return fallback
        return result

    @staticmethod
    def _calc_change_ratio(original: str, humanized: str) -> float:
        """计算字符级改写率 (0~1)。"""
        if not original:
            return 0.0
        matcher = difflib.SequenceMatcher(None, original, humanized)
        ratio = 1.0 - matcher.ratio()
        return round(min(ratio, 1.0), 3)

    def _list_applied_rules(self, focus: list[str] | None) -> list[str]:
        try:
            style = load_yaml("style_rules")
        except FileNotFoundError:
            return []
        directives = style.get("style_directives", [])
        if focus:
            return [d.get("name", "") for d in directives if d.get("name", "") in focus]
        return [d.get("name", "") for d in directives[:8] if isinstance(d, dict)]


# ------------------------------------------------------------------ #
# SkillRegistry 注册                                                    #
# ------------------------------------------------------------------ #

_humanizer_instance = Humanizer()


def _humanize_handler(req: SkillRequest) -> dict[str, Any]:
    text: str = req.inputs.get("text", "")
    if not text:
        raise ValueError("humanizer skill 需要 inputs.text")
    focus: list[str] | None = req.inputs.get("style_focus")
    output = asyncio.run(_humanizer_instance.humanize(text, style_focus=focus))
    return output.model_dump()


_registry.register_fn("humanizer", _humanize_handler)
