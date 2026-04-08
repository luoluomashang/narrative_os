"""tests/test_skills_phase5/test_style_engine.py — StyleEngine 测试组。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_os.skills.style_engine import (
    StyleEngine,
    StyleOutput,
    StyleProfile,
    StyleScore,
)


# ------------------------------------------------------------------ #
# Fixtures                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture
def clean_profile() -> StyleProfile:
    return StyleProfile(
        name="test",
        warning_words=["综上所述", "不可否认", "值得注意"],
        style_directives=["短句", "情绪化"],
        sentence_length_target="short",
        tone="energetic",
        genre="fantasy",
    )


@pytest.fixture
def engine_no_llm(monkeypatch) -> StyleEngine:
    """StyleEngine with LLM router mocked out."""
    router = MagicMock()
    return StyleEngine(router=router)


# ------------------------------------------------------------------ #
# StyleProfile 模型                                                     #
# ------------------------------------------------------------------ #

class TestStyleProfileModel:
    def test_defaults(self):
        p = StyleProfile(name="x")
        assert p.sentence_length_target == "medium"
        assert p.tone == "neutral"
        assert p.genre == "general"
        assert p.warning_words == []
        assert p.custom_rules == []

    def test_custom_fields(self, clean_profile):
        assert clean_profile.name == "test"
        assert "综上所述" in clean_profile.warning_words
        assert clean_profile.sentence_length_target == "short"
        assert clean_profile.genre == "fantasy"


# ------------------------------------------------------------------ #
# StyleScore 模型                                                       #
# ------------------------------------------------------------------ #

class TestStyleScoreModel:
    def test_defaults(self):
        s = StyleScore()
        assert s.overall == 1.0
        assert s.warning_word_hits == {}
        assert s.avg_sentence_length == 0.0

    def test_partial_fields(self):
        s = StyleScore(warning_word_score=0.8, sentence_length_score=0.9)
        assert s.warning_word_score == 0.8
        assert s.sentence_length_score == 0.9


# ------------------------------------------------------------------ #
# load_profile                                                          #
# ------------------------------------------------------------------ #

class TestLoadProfile:
    def test_loads_builtin_returns_style_profile(self, engine_no_llm):
        engine = engine_no_llm
        profile = engine.load_profile("tomato")
        assert isinstance(profile, StyleProfile)
        assert profile.name == "tomato"

    def test_loads_fantasy_genre(self, engine_no_llm):
        profile = engine_no_llm.load_profile("fantasy")
        assert profile.genre == "fantasy"
        # fantasy.yaml has rules list
        assert len(profile.custom_rules) > 0

    def test_unknown_name_fallback(self, engine_no_llm):
        # 无对应 style_modules 时应降级为通用档案
        profile = engine_no_llm.load_profile("nonexistent_xyz")
        assert isinstance(profile, StyleProfile)
        assert profile.name == "nonexistent_xyz"
        assert profile.genre == "general"

    def test_warning_words_populated(self, engine_no_llm):
        profile = engine_no_llm.load_profile("tomato")
        # style_rules.yaml 中有 warning_words.list
        assert isinstance(profile.warning_words, list)


# ------------------------------------------------------------------ #
# build_profile                                                         #
# ------------------------------------------------------------------ #

class TestBuildProfile:
    def test_build_custom(self, engine_no_llm):
        p = engine_no_llm.build_profile(
            "my_style",
            warning_words=["foo", "bar"],
            sentence_length_target="long",
            tone="dark",
        )
        assert p.name == "my_style"
        assert p.warning_words == ["foo", "bar"]
        assert p.sentence_length_target == "long"
        assert p.tone == "dark"

    def test_build_minimal(self, engine_no_llm):
        p = engine_no_llm.build_profile("min")
        assert p.name == "min"
        assert p.custom_rules == []


# ------------------------------------------------------------------ #
# score_compliance — warning words                                      #
# ------------------------------------------------------------------ #

class TestScoreComplianceWarningWords:
    def test_no_violations(self, clean_profile, engine_no_llm):
        text = "他拔出长剑，猛地刺出。对方应声倒地。"
        score = engine_no_llm.score_compliance(text, clean_profile)
        assert score.warning_word_hits == {}
        assert score.warning_word_score == 1.0

    def test_one_violation(self, clean_profile, engine_no_llm):
        text = "综上所述，这件事很重要。"
        score = engine_no_llm.score_compliance(text, clean_profile)
        assert "综上所述" in score.warning_word_hits
        assert score.warning_word_score < 1.0

    def test_multiple_violations(self, clean_profile, engine_no_llm):
        text = "综上所述，不可否认，值得注意的是这很关键。"
        score = engine_no_llm.score_compliance(text, clean_profile)
        assert len(score.warning_word_hits) == 3
        assert score.warning_word_score < 0.9

    def test_repeated_violation(self, clean_profile, engine_no_llm):
        text = "综上所述，综上所述，综上所述。"
        score = engine_no_llm.score_compliance(text, clean_profile)
        assert score.warning_word_hits["综上所述"] == 3
        # 3 hits × 0.05 = 0.15 deduction
        assert abs(score.warning_word_score - 0.85) < 0.01

    def test_score_floored_at_zero(self, engine_no_llm):
        words = [f"bad{i}" for i in range(30)]
        p = engine_no_llm.build_profile("harsh", warning_words=words)
        text = " ".join(words)  # all 30 words appear once
        score = engine_no_llm.score_compliance(text, p)
        assert score.warning_word_score == 0.0


# ------------------------------------------------------------------ #
# score_compliance — sentence length                                    #
# ------------------------------------------------------------------ #

class TestScoreComplianceSentenceLength:
    def test_ideal_short(self, engine_no_llm):
        # avg ≈ 11 chars/sentence → short target → score should be > 0.5
        p = engine_no_llm.build_profile("s", sentence_length_target="short")
        # Each sentence ~10-14 chars (Chinese short action sentences)
        text = "他猛地拔出长剑，向前跃出一步。剑光如闪电划破黑暗。对手大叫一声，连退三步。"
        score = engine_no_llm.score_compliance(text, p)
        assert score.sentence_length_score > 0.5

    def test_very_long_sentences_penalise_short_target(self, engine_no_llm):
        p = engine_no_llm.build_profile("s", sentence_length_target="short")
        text = "在这个充满危险与未知的广袤世界中，他孤身一人踏上了艰难险阻的旅途，不知前方等待着他的将是何种命运与挑战。"
        score = engine_no_llm.score_compliance(text, p)
        assert score.sentence_length_score < 0.9

    def test_overall_between_0_and_1(self, clean_profile, engine_no_llm):
        text = "任何文本都应当得到0到1之间的分数。"
        score = engine_no_llm.score_compliance(text, clean_profile)
        assert 0.0 <= score.overall <= 1.0


# ------------------------------------------------------------------ #
# apply_style — LLM 路径                                               #
# ------------------------------------------------------------------ #

class TestApplyStyle:
    async def test_returns_style_output(self, clean_profile):
        mock_resp = MagicMock()
        mock_resp.content = "改写后的文本内容。"
        mock_resp.model_used = "gpt-4o-mini"

        router = MagicMock()
        router.call = AsyncMock(return_value=mock_resp)

        engine = StyleEngine(router=router)
        output = await engine.apply_style("原始文本", clean_profile)

        assert isinstance(output, StyleOutput)
        assert output.original_text == "原始文本"
        assert output.styled_text == "改写后的文本内容。"
        assert output.profile_name == "test"
        assert output.model_used == "gpt-4o-mini"

    async def test_llm_called_once(self, clean_profile):
        mock_resp = MagicMock(content="输出", model_used="m")
        router = MagicMock()
        router.call = AsyncMock(return_value=mock_resp)

        engine = StyleEngine(router=router)
        await engine.apply_style("文本", clean_profile)

        router.call.assert_called_once()

    async def test_system_prompt_contains_profile_name(self, clean_profile):
        captured = {}

        async def capture(req):
            captured["system"] = req.system_prompt
            return MagicMock(content="ok", model_used="m")

        router = MagicMock()
        router.call = AsyncMock(side_effect=capture)
        engine = StyleEngine(router=router)
        await engine.apply_style("sample", clean_profile)

        assert "test" in captured["system"]

    async def test_warning_words_in_system_prompt(self):
        p = StyleProfile(
            name="strict",
            warning_words=["综上所述", "不可否认"],
        )
        captured = {}

        async def capture(req):
            captured["system"] = req.system_prompt
            return MagicMock(content="OK", model_used="m")

        router = MagicMock()
        router.call = AsyncMock(side_effect=capture)
        engine = StyleEngine(router=router)
        await engine.apply_style("text", p)

        assert "综上所述" in captured["system"]
