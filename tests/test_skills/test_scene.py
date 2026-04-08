"""tests/test_skills/test_scene.py — SceneGenerator 单元测试（mock LLMRouter）"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_os.execution.context_builder import ChapterTarget, ContextBuilder
from narrative_os.execution.llm_router import Backend, LLMResponse
from narrative_os.skills.scene import SceneGenerator, SceneOutput


# ------------------------------------------------------------------ #
# Helper                                                               #
# ------------------------------------------------------------------ #

def make_generator(text: str = "林风迎着风站了起来。" * 200) -> SceneGenerator:
    mock_resp = LLMResponse(
        content=text,
        model_used="gpt-4o",
        backend=Backend.OPENAI,
        prompt_tokens=200,
        completion_tokens=800,
        latency_ms=1200,
    )
    mock_router = MagicMock()
    mock_router.call = AsyncMock(return_value=mock_resp)
    return SceneGenerator(router=mock_router)


def make_context(chapter: int = 1, word_count: int = 2000, tension: float = 0.7) -> object:
    cb = ContextBuilder()
    return cb.build(
        chapter_target=ChapterTarget(
            chapter=chapter,
            target_summary="主角被围攻",
            word_count_target=word_count,
            tension_target=tension,
            hook_type="cliffhanger",
        )
    )


# ------------------------------------------------------------------ #
# Tests                                                                #
# ------------------------------------------------------------------ #

class TestSceneOutput:
    def test_model_fields(self):
        out = SceneOutput(
            text="场景文本",
            word_count=100,
            tension_score=0.7,
            hook_score=0.6,
            chapter=1,
        )
        assert out.text == "场景文本"
        assert out.chapter == 1

    def test_default_scores(self):
        out = SceneOutput(text="测试")
        assert out.tension_score == pytest.approx(0.5)
        assert out.hook_score == pytest.approx(0.5)


class TestSceneGenerator:
    @pytest.mark.asyncio
    async def test_generate_returns_output(self):
        gen = make_generator("林风高喝一声。" * 400)
        ctx = make_context()
        result = await gen.generate(ctx)
        assert isinstance(result, SceneOutput)
        assert len(result.text) > 0

    @pytest.mark.asyncio
    async def test_word_count_set(self):
        text = "字" * 2000
        gen = make_generator(text)
        ctx = make_context(word_count=2000)
        result = await gen.generate(ctx)
        assert result.word_count == 2000

    @pytest.mark.asyncio
    async def test_chapter_and_volume_set(self):
        gen = make_generator("内容" * 500)
        ctx = make_context(chapter=5)
        result = await gen.generate(ctx)
        assert result.chapter == 5
        assert result.volume == 1

    @pytest.mark.asyncio
    async def test_model_used_propagated(self):
        gen = make_generator("文本" * 300)
        ctx = make_context()
        result = await gen.generate(ctx)
        assert result.model_used == "gpt-4o"

    @pytest.mark.asyncio
    async def test_retry_on_short_output(self):
        """第一次输出太短，自动重试。"""
        short_text = "短"  # 远低于目标字数
        long_text = "足够长的内容" * 400

        responses = [
            LLMResponse(content=short_text, model_used="gpt-4o-mini", backend=Backend.OPENAI,
                        prompt_tokens=100, completion_tokens=10),
            LLMResponse(content=long_text, model_used="gpt-4o", backend=Backend.OPENAI,
                        prompt_tokens=200, completion_tokens=800),
        ]
        call_count = {"n": 0}

        async def mock_call(req):
            resp = responses[min(call_count["n"], 1)]
            call_count["n"] += 1
            return resp

        mock_router = MagicMock()
        mock_router.call = mock_call
        gen = SceneGenerator(router=mock_router)
        ctx = make_context(word_count=2000)
        result = await gen.generate(ctx)
        assert result.attempts >= 2
        assert result.word_count > 1

    @pytest.mark.asyncio
    async def test_tension_score_range(self):
        gen = make_generator("林风怒吼，杀意爆发，剑光炸裂，死战！" * 100)
        ctx = make_context(tension=0.9)
        result = await gen.generate(ctx)
        assert 0.0 <= result.tension_score <= 1.0

    @pytest.mark.asyncio
    async def test_hook_score_range(self):
        gen = make_generator("就在此时，突然一声怒吼！谁知？" * 100)
        ctx = make_context()
        result = await gen.generate(ctx)
        assert 0.0 <= result.hook_score <= 1.0


class TestWordCountHelper:
    def test_count_words_chinese(self):
        gen = SceneGenerator.__new__(SceneGenerator)
        assert SceneGenerator._count_words("你好世界") == 4
        assert SceneGenerator._count_words("你 好 世 界") == 4

    def test_estimate_hook_signal(self):
        text_with_hook = "平常内容" * 50 + "就在此时，突然一声怒吼！"
        score = SceneGenerator._estimate_hook(text_with_hook)
        text_without = "平常内容" * 50 + "然后他离开了。"
        score2 = SceneGenerator._estimate_hook(text_without)
        assert score > score2
