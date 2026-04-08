"""
skills/scene.py — Phase 2: Scene Generator Skill

功能：
  - 接收 WriteContext + SkillRequest，生成场景正文
  - 内部使用 LLMRouter 发起 LLM 调用
  - 输出结构化 SceneOutput（正文 / 字数 / 钩子评分 / 张力评分）
  - 支持"重写循环"：质量不达标时自动使用更高 tier 重写（最多 max_retries 次）
  - 注册到全局 SkillRegistry

UI 映射：写作工作台"生成场景"按钮 → 触发此 Skill
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import BaseModel, Field

from narrative_os.execution.context_builder import WriteContext
from narrative_os.execution.llm_router import (
    LLMRequest,
    LLMRouter,
    ModelTier,
    RoutingStrategy,
    get_default_routing_strategy,
)
from narrative_os.skills.dsl import SkillRegistry, SkillRequest, SkillResponse

_registry = SkillRegistry()


# ------------------------------------------------------------------ #
# 输出模型                                                              #
# ------------------------------------------------------------------ #

class SceneOutput(BaseModel):
    """场景生成结果。"""
    text: str
    word_count: int = 0
    tension_score: float = 0.5    # 0~1，由后处理估算
    hook_score: float = 0.5       # 0~1，结尾钩子强度
    chapter: int = 0
    volume: int = 1
    model_used: str = ""
    attempts: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ #
# SceneGenerator                                                        #
# ------------------------------------------------------------------ #

class SceneGenerator:
    """
    场景生成器。

    用法：
        gen = SceneGenerator()
        output = await gen.generate(context, req)
    """

    MIN_WORD_RATIO = 0.7   # 最低字数达到目标的 70%
    MAX_RETRIES = 2

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()

    # ---------------------------------------------------------------- #
    # Main                                                              #
    # ---------------------------------------------------------------- #

    async def generate(
        self,
        context: WriteContext,
        req: SkillRequest | None = None,
        strategy: RoutingStrategy = get_default_routing_strategy(),
    ) -> SceneOutput:
        """
        生成场景正文。自动重写循环（最多 MAX_RETRIES 次）。
        """
        target_words = context.chapter_target.word_count_target
        system_prompt = context.to_system_prompt()
        user_msg = self._build_user_message(context, req)
        tier = ModelTier.MEDIUM

        for attempt in range(1, self.MAX_RETRIES + 2):
            llm_req = LLMRequest(
                task_type="scene_generation",
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                strategy=strategy,
                tier_override=tier,
                max_tokens=max(2048, int(target_words * 2.5)),
                temperature=0.75,
                skill_name="scene_generator",
                agent_name=req.agent if req else None,
            )
            resp = await self._router.call(llm_req)
            text = resp.content.strip()
            wc = self._count_words(text)

            if wc >= target_words * self.MIN_WORD_RATIO:
                return SceneOutput(
                    text=text,
                    word_count=wc,
                    tension_score=self._estimate_tension(text, context),
                    hook_score=self._estimate_hook(text),
                    chapter=context.chapter_target.chapter,
                    volume=context.chapter_target.volume,
                    model_used=resp.model_used,
                    attempts=attempt,
                )

            # 达不到字数 → 升一级 tier 重写
            tier = ModelTier.LARGE
            user_msg = (
                f"{user_msg}\n\n"
                f"⚠️ 上一次输出仅 {wc} 字，低于目标 {target_words} 字。"
                f"请重新生成，确保不少于 {target_words} 字，内容更丰富。"
            )

        # 最后一次结果直接返回
        text = resp.content.strip()  # type: ignore[possibly-undefined]
        return SceneOutput(
            text=text,
            word_count=self._count_words(text),
            tension_score=self._estimate_tension(text, context),
            hook_score=self._estimate_hook(text),
            chapter=context.chapter_target.chapter,
            volume=context.chapter_target.volume,
            model_used=resp.model_used,
            attempts=self.MAX_RETRIES + 1,
        )

    # ---------------------------------------------------------------- #
    # Helpers                                                           #
    # ---------------------------------------------------------------- #

    def _build_user_message(
        self, context: WriteContext, req: SkillRequest | None
    ) -> str:
        ct = context.chapter_target
        lines = [
            f"请为卷{ct.volume}第{ct.chapter}章生成场景正文。",
            f"章节定位：{ct.target_summary}" if ct.target_summary else "",
            f"目标字数：不少于 {ct.word_count_target} 字。",
            f"张力目标：{ct.tension_target:.0%}（{'高张力激烈场景' if ct.tension_target >= 0.7 else '中等张力推进场景' if ct.tension_target >= 0.4 else '缓和过渡场景'}）。",
            f"结尾必须设置 [{ct.hook_type}] 类型的钩子。",
        ]
        # 额外用户约束
        if req and req.constraints:
            lines.append("\n额外约束：")
            for c in req.constraints:
                lines.append(f"- {c}")

        return "\n".join(l for l in lines if l)

    @staticmethod
    def _count_words(text: str) -> int:
        """中文字数统计（字符数，过滤空白）。"""
        return len(re.sub(r"\s", "", text))

    @staticmethod
    def _estimate_tension(text: str, context: WriteContext) -> float:
        """
        简单启发式张力估算：
        高张力词汇出现密度作为代理指标。
        生产版本应由 Critic Agent 进行 LLM 评分。
        """
        HIGH_TENSION_WORDS = [
            "杀", "死", "血", "爆", "轰", "撕", "裂", "崩", "战", "斗",
            "危", "险", "逃", "追", "刀", "剑", "怒", "吼", "震惊", "绝境",
        ]
        total = max(len(text), 1)
        hits = sum(text.count(w) for w in HIGH_TENSION_WORDS)
        raw = min(hits / (total / 200), 1.0)  # 每200字击中数归一化
        # 向目标张力靠拢
        return round(raw * 0.5 + context.chapter_target.tension_target * 0.5, 3)

    @staticmethod
    def _estimate_hook(text: str) -> float:
        """
        结尾钩子强度估算：检查末尾 200 字内的钩子信号词。
        """
        tail = text[-200:] if len(text) > 200 else text
        HOOK_SIGNALS = ["突然", "骤然", "然而", "却", "没想到", "没料到", "竟然",
                        "就在此时", "下一刻", "只见", "不料", "谁知", "？", "！"]
        score = sum(0.1 for s in HOOK_SIGNALS if s in tail)
        return round(min(score, 1.0), 3)


# ------------------------------------------------------------------ #
# SkillRegistry 注册                                                    #
# ------------------------------------------------------------------ #

_scene_gen_instance = SceneGenerator()


def _scene_skill_handler(req: SkillRequest) -> dict[str, Any]:
    """同步包装，供 SkillRegistry 调用。"""
    context: WriteContext | None = req.inputs.get("context")
    if context is None:
        raise ValueError("scene_generator skill 需要 inputs.context (WriteContext)")
    output = asyncio.run(_scene_gen_instance.generate(context, req))
    return output.model_dump()


_registry.register_fn("scene_generator", _scene_skill_handler)
