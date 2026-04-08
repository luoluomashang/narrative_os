"""tests/test_skills/test_humanize.py — Humanizer 单元测试（无网络，mock LLMRouter）"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_os.execution.llm_router import Backend, LLMResponse
from narrative_os.skills.humanize import Humanizer, HumanizeOutput


# ------------------------------------------------------------------ #
# Fixture: mock router                                                  #
# ------------------------------------------------------------------ #

def make_humanizer(humanized_text: str = "改写后的文本。") -> Humanizer:
    """返回带 mock LLMRouter 的 Humanizer。"""
    mock_resp = LLMResponse(
        content=humanized_text,
        model_used="claude-3-5-sonnet-20241022",
        backend=Backend.ANTHROPIC,
        prompt_tokens=300,
        completion_tokens=200,
        latency_ms=500,
    )
    mock_router = MagicMock()
    mock_router.call = AsyncMock(return_value=mock_resp)
    h = Humanizer(router=mock_router)
    return h


# ------------------------------------------------------------------ #
# Tests                                                                #
# ------------------------------------------------------------------ #

class TestHumanizeOutput:
    def test_model_fields(self):
        out = HumanizeOutput(
            original_text="原始文本内容abc",
            humanized_text="改写后的文本内容xyz",
        )
        assert out.original_text == "原始文本内容abc"
        assert out.humanized_text == "改写后的文本内容xyz"

    def test_word_count_delta(self):
        out = HumanizeOutput(
            original_text="abc",
            humanized_text="abcde",
        )
        assert out.word_count_delta == 2

    def test_word_count_delta_negative(self):
        out = HumanizeOutput(
            original_text="稍微长一点点的文本",
            humanized_text="短文",
        )
        assert out.word_count_delta < 0


class TestHumanizer:
    @pytest.mark.asyncio
    async def test_humanize_returns_output(self):
        h = make_humanizer("这是改写后的内容，更有人味。")
        result = await h.humanize("这是原始AI生成的内容。")
        assert isinstance(result, HumanizeOutput)
        assert result.humanized_text == "这是改写后的内容，更有人味。"
        assert result.original_text == "这是原始AI生成的内容。"

    @pytest.mark.asyncio
    async def test_humanize_model_used(self):
        h = make_humanizer()
        result = await h.humanize("测试文本")
        assert result.model_used == "claude-3-5-sonnet-20241022"

    @pytest.mark.asyncio
    async def test_change_ratio_computed(self):
        original = "原来的一段话，用词平淡，有机器感。"
        humanized = "改写后的一段话，词语生动，充满人味。"
        h = make_humanizer(humanized)
        result = await h.humanize(original)
        assert 0.0 <= result.change_ratio <= 1.0

    @pytest.mark.asyncio
    async def test_applied_rules_populated(self):
        h = make_humanizer()
        result = await h.humanize("测试文本")
        assert isinstance(result.applied_rules, list)
        # Should have loaded style_rules from narrativespace config
        assert len(result.applied_rules) > 0

    @pytest.mark.asyncio
    async def test_fallback_if_llm_returns_too_short(self):
        """LLM 返回极短内容时，回退到原文。"""
        mock_resp = LLMResponse(
            content="短",  # 远小于原文的 30%
            model_used="test",
            backend=Backend.OLLAMA,
        )
        mock_router = MagicMock()
        mock_router.call = AsyncMock(return_value=mock_resp)
        h = Humanizer(router=mock_router)

        original = "这是一段有足够长度的原始文本，用于测试回退逻辑是否正确触发。" * 3
        result = await h.humanize(original)
        # Falls back to original
        assert result.humanized_text == original

    @pytest.mark.asyncio
    async def test_style_focus_param_accepted(self):
        h = make_humanizer("聚焦改写后内容。")
        result = await h.humanize(
            "原始文本",
            style_focus=["对话去AI化（硬约束）", "高潮节奏加速"],
        )
        assert isinstance(result, HumanizeOutput)

    @pytest.mark.asyncio
    async def test_system_prompt_cached(self):
        """第二次调用 _get_system_prompt 时使用缓存。"""
        h = make_humanizer()
        p1 = h._get_system_prompt(None)
        p2 = h._get_system_prompt(None)
        assert p1 is p2  # same object (cached)
