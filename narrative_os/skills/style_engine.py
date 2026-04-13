"""
skills/style_engine.py — Phase 5: 风格引擎（Style Engine）

职责：
  - 管理命名风格档案（StyleProfile）：从 narrativespace/config/style_rules.yaml
    及 style_modules/<name>.yaml 加载，也支持自定义构建
  - 本地风格合规评分（StyleScore）：无 LLM，纯统计
  - LLM 驱动风格迁移（StyleOutput）：apply_style()
  - 注册到 SkillRegistry: "style_score" / "style_apply"

UI 映射：写作工作台 → 风格面板（合规仪表盘 + 一键风格迁移）
"""

from __future__ import annotations

import re
from typing import Any, Literal

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
from narrative_os.skills.dsl import SkillRegistry, SkillRequest, SkillResponse

# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class StyleProfile(BaseModel):
    """命名风格档案。"""
    name: str
    warning_words: list[str] = Field(default_factory=list)
    style_directives: list[str] = Field(default_factory=list)
    sentence_length_target: Literal["short", "medium", "long"] = "medium"
    tone: str = "neutral"
    genre: str = "general"
    custom_rules: list[str] = Field(default_factory=list)

    model_config = {"frozen": False}


class StyleScore(BaseModel):
    """风格合规评分结果（本地计算，无 LLM）。"""
    warning_word_hits: dict[str, int] = Field(default_factory=dict)  # word → count
    warning_word_score: float = 1.0    # 0~1，命中越多分越低
    avg_sentence_length: float = 0.0
    sentence_length_score: float = 1.0  # 0~1，越接近目标越高
    overall: float = 1.0               # 加权综合分


class StyleOutput(BaseModel):
    """apply_style() 返回结果。"""
    original_text: str
    styled_text: str
    profile_name: str
    model_used: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


# ------------------------------------------------------------------ #
# StyleEngine                                                           #
# ------------------------------------------------------------------ #

_SENTENCE_IDEAL: dict[str, float] = {
    "short":  15.0,
    "medium": 25.0,
    "long":   40.0,
}

_SENTENCE_TOLERANCE: dict[str, float] = {
    "short":  10.0,
    "medium": 20.0,
    "long":   25.0,
}


class StyleEngine:
    """
    风格引擎主类。

    用法：
        engine = StyleEngine()
        profile = engine.load_profile("tomato")      # 加载内置档案
        score   = engine.score_compliance(text, profile)
        output  = await engine.apply_style(text, profile)
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()

    # ---------------------------------------------------------------- #
    # 档案管理                                                            #
    # ---------------------------------------------------------------- #

    def load_profile(self, name: str) -> StyleProfile:
        """
        从 narrativespace/config/style_rules.yaml 加载内置"番茄"档案；
        若 name 匹配 style_modules/<name>.yaml，则同时附加该模块规则。
        """
        try:
            base = load_yaml("style_rules")
        except FileNotFoundError:
            base = {}

        warning_words: list[str] = []
        if "warning_words" in base:
            warning_words = base["warning_words"].get("list", [])

        style_directives: list[str] = []
        if "style_directives" in base:
            style_directives = [d.get("name", "") for d in base["style_directives"] if d.get("name")]
        if "structure_directives" in base:
            style_directives += [d.get("name", "") for d in base["structure_directives"] if d.get("name")]

        # 尝试加载对应的风格模块
        genre = "general"
        module_rules: list[str] = []
        try:
            mod = load_yaml(f"style_modules/{name}")
            genre = name
            if "rules" in mod:
                module_rules = [r for r in mod["rules"] if isinstance(r, str)]
        except FileNotFoundError:
            pass

        return StyleProfile(
            name=name,
            warning_words=warning_words,
            style_directives=style_directives,
            sentence_length_target="short",  # 番茄风格默认短句
            tone="energetic",
            genre=genre,
            custom_rules=module_rules,
        )

    def build_profile(
        self,
        name: str,
        *,
        warning_words: list[str] | None = None,
        style_directives: list[str] | None = None,
        sentence_length_target: Literal["short", "medium", "long"] = "medium",
        tone: str = "neutral",
        genre: str = "general",
        custom_rules: list[str] | None = None,
    ) -> StyleProfile:
        """构建自定义风格档案。"""
        return StyleProfile(
            name=name,
            warning_words=warning_words or [],
            style_directives=style_directives or [],
            sentence_length_target=sentence_length_target,
            tone=tone,
            genre=genre,
            custom_rules=custom_rules or [],
        )

    # ---------------------------------------------------------------- #
    # 本地评分                                                            #
    # ---------------------------------------------------------------- #

    def score_compliance(self, text: str, profile: StyleProfile) -> StyleScore:
        """
        纯本地统计风格合规度。无 LLM 调用。

        warning_word_score: 每个违禁词出现一次扣 0.05，最低 0.0
        sentence_length_score: avg_sentence_length 偏离目标越大扣分越多
        overall: warning_word_score × 0.60 + sentence_length_score × 0.40
        """
        hits = self._check_warning_words(text, profile)
        total_hits = sum(hits.values())
        ww_score = max(0.0, 1.0 - total_hits * 0.05)

        avg_len = self._avg_sentence_length(text)
        sl_score = self._score_sentence_length(avg_len, profile.sentence_length_target)

        overall = round(ww_score * 0.60 + sl_score * 0.40, 4)

        return StyleScore(
            warning_word_hits=hits,
            warning_word_score=round(ww_score, 4),
            avg_sentence_length=round(avg_len, 2),
            sentence_length_score=round(sl_score, 4),
            overall=overall,
        )

    # ---------------------------------------------------------------- #
    # LLM 风格迁移                                                        #
    # ---------------------------------------------------------------- #

    async def apply_style(
        self,
        text: str,
        profile: StyleProfile,
        strategy: RoutingStrategy = get_default_routing_strategy(),
    ) -> StyleOutput:
        """
        将文本改写为目标风格档案的行文风格。
        """
        system = self._build_system_prompt(profile)
        user_msg = (
            f"请将以下文本改写为【{profile.name}】风格，保持原意，改写后直接输出正文：\n\n{text}"
        )
        llm_req = LLMRequest(
            task_type="style_transfer",
            system_prompt=system,
            messages=[{"role": "user", "content": user_msg}],
            strategy=strategy,
            tier_override=ModelTier.MEDIUM,
            max_tokens=int(len(text) * 2.5) + 512,
            temperature=0.65,
            skill_name="style_engine",
        )
        resp = await self._router.call(llm_req)
        return StyleOutput(
            original_text=text,
            styled_text=resp.content.strip(),
            profile_name=profile.name,
            model_used=resp.model_used,
        )

    # ---------------------------------------------------------------- #
    # 内部工具                                                            #
    # ---------------------------------------------------------------- #

    def _check_warning_words(self, text: str, profile: StyleProfile) -> dict[str, int]:
        hits: dict[str, int] = {}
        for word in profile.warning_words:
            count = text.count(word)
            if count:
                hits[word] = count
        return hits

    def _avg_sentence_length(self, text: str) -> float:
        """按中英文句末标点切分，计算平均字符数。"""
        sentences = re.split(r"[。！？!?\.]+", text)
        valid = [s.strip() for s in sentences if s.strip()]
        if not valid:
            return 0.0
        return sum(len(s) for s in valid) / len(valid)

    def _score_sentence_length(
        self, avg_len: float, target: Literal["short", "medium", "long"]
    ) -> float:
        """
        基于目标长度打分。
        偏差 = |avg_len - ideal| / tolerance
        score = max(0, 1 - deviation)
        """
        ideal = _SENTENCE_IDEAL[target]
        tol = _SENTENCE_TOLERANCE[target]
        deviation = abs(avg_len - ideal) / tol
        return round(max(0.0, 1.0 - deviation), 4)

    def _build_system_prompt(self, profile: StyleProfile) -> str:
        parts = [f"你是专业小说编辑，负责将文本改写为【{profile.name}】风格。"]
        parts.append(f"目标语气：{profile.tone}。目标句长：{profile.sentence_length_target}句。")
        if profile.style_directives:
            parts.append("风格要点：\n" + "\n".join(f"- {d}" for d in profile.style_directives[:8]))
        if profile.custom_rules:
            parts.append("额外规则：\n" + "\n".join(f"- {r}" for r in profile.custom_rules[:5]))
        if profile.warning_words:
            parts.append("禁止使用词汇：" + "、".join(profile.warning_words[:15]))
        parts.append(plain_text_contract("改写后只输出正文，不加说明。"))
        return "\n\n".join(parts)


# ------------------------------------------------------------------ #
# SkillRegistry 注册                                                    #
# ------------------------------------------------------------------ #

def _score_handler(req: SkillRequest) -> SkillResponse:
    """skill: "style_score" — 本地评分（同步）。"""
    engine = StyleEngine()
    profile_data = req.inputs.get("profile", {})
    text = req.inputs.get("text", "")
    if not text:
        return SkillResponse(skill=req.skill, status="failed", errors=["缺少 inputs.text"])
    if isinstance(profile_data, dict) and profile_data:
        profile = StyleProfile(**profile_data)
    else:
        name = req.inputs.get("profile_name", "default")
        profile = engine.load_profile(name)
    score = engine.score_compliance(text, profile)
    return SkillResponse(skill=req.skill, status="success", output=score.model_dump())


SkillRegistry.instance().register_fn("style_score", _score_handler)
