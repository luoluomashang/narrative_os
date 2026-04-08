"""
tests/test_world_builder_completion.py — Phase 5: WorldBuilder 完善测试
"""
from __future__ import annotations

import pytest

from narrative_os.core.world_builder import BuilderStep, StepResult, WorldBuilder


# ------------------------------------------------------------------ #
# 辅助：快速推进到指定步骤                                               #
# ------------------------------------------------------------------ #

def _advance_to_one_page(builder: WorldBuilder) -> None:
    """将 builder 推进到 ONE_PAGE 步骤（无力量体系触发路径）。"""
    builder.start()
    builder.submit_step("弱小少年踏上旅途，追寻传说中的秘宝")         # ONE_SENTENCE → ONE_PARAGRAPH (无触发词)
    builder.submit_step("第一卷：找到秘宝，全书走向传奇。")  # ONE_PARAGRAPH → ONE_PAGE


def _advance_to_one_page_xiu_zhen(builder: WorldBuilder) -> None:
    """将 builder 推进到 ONE_PAGE 步骤（修真路径）。"""
    builder.start()
    builder.submit_step("少年在修真大陆修炼成仙，对抗魔族")    # ONE_SENTENCE → ONE_PARAGRAPH（过WORLD_POWER）
    builder.submit_step("第一卷：筑基成功，全书走向封神。")     # ONE_PARAGRAPH → WORLD_POWER
    builder.submit_step("练气→筑基→金丹，灵石兑换升级。")       # WORLD_POWER → ONE_PAGE


# ------------------------------------------------------------------ #
# _parse_one_page                                                       #
# ------------------------------------------------------------------ #

def test_parse_one_page_extracts_characters():
    """含"主角："格式的文本应提取到角色。"""
    builder = WorldBuilder()
    text = "主角：林枫，男，热血少年。\n反派：陈天行，阴谋家。\n关键地点：宗门广场。"
    result = builder._parse_one_page(text)
    names = [c["name"] for c in result["characters"]]
    assert "林枫" in names
    assert "陈天行" in names


def test_parse_one_page_generates_plot_nodes():
    """多段文本应生成 ≥1 个情节节点。"""
    builder = WorldBuilder()
    text = (
        "林枫被驱逐出宗门。\n"
        "林枫在废墟中找到上古秘籍。\n"
        "林枫回到宗门复仇挑战长老。\n"
    )
    result = builder._parse_one_page(text)
    assert len(result["plot_nodes"]) >= 1


def test_parse_one_page_empty_input_does_not_crash():
    """空输入应返回空列表，不抛异常。"""
    builder = WorldBuilder()
    result = builder._parse_one_page("")
    assert result["characters"] == []
    assert result["plot_nodes"] == []


def test_parse_one_page_extracts_world_factions():
    """含"势力："格式的文本应提取势力信息。"""
    builder = WorldBuilder()
    text = "势力：天枢阁是最强宗门，控制东海三省。\n主角：叶辰，散修。"
    result = builder._parse_one_page(text)
    assert len(result["world"]["factions"]) >= 1


# ------------------------------------------------------------------ #
# _finalize                                                             #
# ------------------------------------------------------------------ #

def test_finalize_populates_initial_characters():
    """调用 _finalize 后 initial_characters 应非空（若大纲含角色信息）。"""
    builder = WorldBuilder()
    builder.start()
    builder.submit_step("少年在都市追梦，踏上江湖之路")
    builder.submit_step("第一卷完结。")
    # ONE_PAGE 步骤（含角色描述）
    builder.submit_step("主角：陈浩，热血少年，想保护家人。\n反派：神秘组织头目。")
    # 跳过 CHARACTER_ARCS 和 FOUR_PAGES
    builder.submit_step("")  # CHARACTER_ARCS skip
    result = builder.submit_step("")  # FOUR_PAGES skip → DONE

    assert result.step == BuilderStep.DONE
    assert len(builder.state.initial_characters) >= 1
    names = [c["name"] for c in builder.state.initial_characters]
    assert "陈浩" in names


def test_finalize_has_at_least_one_plot_node():
    """_finalize() 生成的 PlotNode 至少 1 个。"""
    builder = WorldBuilder()
    builder.start()
    builder.submit_step("少年踏足江湖寻找武学秘籍")      # ONE_SENTENCE (无触发词)
    builder.submit_step("第一卷：获得秘籍，学成归来。")  # ONE_PARAGRAPH → ONE_PAGE
    builder.submit_step("主角：赵雷，军人出身。")         # ONE_PAGE → CHARACTER_ARCS
    builder.submit_step("")                               # CHARACTER_ARCS → FOUR_PAGES
    builder.submit_step("")                               # FOUR_PAGES → DONE

    assert len(builder.state.initial_plot_nodes) >= 1


# ------------------------------------------------------------------ #
# CHARACTER_ARCS 步骤                                                    #
# ------------------------------------------------------------------ #

def test_character_arcs_step_stores_arcs():
    """经过 CHARACTER_ARCS 步骤后 state.character_arcs 应非空。"""
    builder = WorldBuilder()
    _advance_to_one_page(builder)
    builder.submit_step("主角：高中生\n反派：组织弟子\n关键地点：城市边缘。")  # ONE_PAGE → CHARACTER_ARCS
    # 提供弧光（CHARACTER_ARCS 步骤）→ 推进到 FOUR_PAGES
    result = builder.submit_step("高中生：懵懂少年 → 觉醒异能 → 肩负使命")
    assert result.step == BuilderStep.FOUR_PAGES
    assert len(builder.state.character_arcs) >= 1


def test_character_arcs_skippable_with_empty_input():
    """CHARACTER_ARCS 阶段空回车应直接跳到 FOUR_PAGES。"""
    builder = WorldBuilder()
    _advance_to_one_page(builder)
    builder.submit_step("主角：李刚\n反派：boss")  # ONE_PAGE → CHARACTER_ARCS
    result = builder.submit_step("")               # 跳过 CHARACTER_ARCS → FOUR_PAGES
    assert result.step == BuilderStep.FOUR_PAGES
    assert result.skippable is True


def test_four_pages_skippable_with_empty_input():
    """FOUR_PAGES 阶段空回车应直接生成 DONE。"""
    builder = WorldBuilder()
    _advance_to_one_page(builder)
    builder.submit_step("主角：李刚")  # ONE_PAGE → CHARACTER_ARCS
    builder.submit_step("")             # CHARACTER_ARCS → FOUR_PAGES
    result = builder.submit_step("")   # FOUR_PAGES → DONE
    assert result.step == BuilderStep.DONE


# ------------------------------------------------------------------ #
# 类型感知种子模板                                                       #
# ------------------------------------------------------------------ #

def test_genre_template_xiu_zhen_prefills_world_power():
    """包含"修真"关键词时应自动预填修炼境界力量体系。"""
    builder = WorldBuilder()
    builder.start()
    builder.submit_step("少年在修真大陆修炼成仙，对抗魔族")
    assert builder.state.needs_world_power is True
    assert "修真" in builder.state.genre_tags or builder.state.world_power_system
    if builder.state.world_power_system:
        assert "tiers" in builder.state.world_power_system


def test_genre_template_does_not_overwrite_custom():
    """用户已自定义力量体系时，类型模板不应覆盖。"""
    builder = WorldBuilder()
    # 手动预设
    builder.state.world_power_system = {"system_name": "我的自定义体系", "tiers": ["一级"]}
    builder.start()
    builder.submit_step("少年在修真大陆修炼")
    # 自定义不应被修真模板覆盖
    assert builder.state.world_power_system["system_name"] == "我的自定义体系"


# ------------------------------------------------------------------ #
# get_seed_data                                                          #
# ------------------------------------------------------------------ #

def test_get_seed_data_after_done_returns_complete_dict():
    """DONE 状态后 get_seed_data() 应包含所有必须字段。"""
    builder = WorldBuilder()
    _advance_to_one_page(builder)
    builder.submit_step("主角：陈曦，高中生，力量系。")  # ONE_PAGE → CHARACTER_ARCS
    builder.submit_step("")   # CHARACTER_ARCS skip
    builder.submit_step("")   # FOUR_PAGES skip → DONE

    seed = builder.get_seed_data()
    assert "plot_nodes" in seed
    assert "characters" in seed
    assert "world" in seed
    assert "one_sentence" in seed
    assert "one_paragraph" in seed
    assert isinstance(seed["plot_nodes"], list)
    assert len(seed["plot_nodes"]) >= 1


# ------------------------------------------------------------------ #
# Phase 5-F1：AI 对话式世界构建测试                                       #
# ------------------------------------------------------------------ #

def test_discuss_mode_does_not_advance_step():
    """discuss() 不应推进步骤。"""
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock

    builder = WorldBuilder()
    builder.start()
    builder.submit_step("少年踏上修炼之路")  # → ONE_PARAGRAPH
    current_step = builder.state.step
    assert current_step == BuilderStep.ONE_PARAGRAPH

    # Mock router.call_stream
    async def fake_stream(req):
        yield "这个概念不错，"
        yield "建议增加冲突元素。"

    with patch("narrative_os.execution.llm_router.router") as mock_router:
        mock_router.call_stream = fake_stream

        async def run():
            chunks = []
            async for chunk in builder.discuss("这个方向好吗？"):
                chunks.append(chunk)
            return chunks

        chunks = asyncio.run(run())

    # 步骤不应改变
    assert builder.state.step == current_step
    assert len(chunks) >= 1
    assert "".join(chunks) == "这个概念不错，建议增加冲突元素。"


def test_conversation_history_accumulates():
    """对话历史在 discuss() 调用后正确累积。"""
    import asyncio
    from unittest.mock import patch

    builder = WorldBuilder()
    builder.start()
    builder.submit_step("少年修炼成仙")

    async def fake_stream(req):
        yield "好的建议！"

    with patch("narrative_os.execution.llm_router.router") as mock_router:
        mock_router.call_stream = fake_stream

        async def run():
            async for _ in builder.discuss("第一个问题"):
                pass
            async for _ in builder.discuss("第二个问题"):
                pass

        asyncio.run(run())

    history = builder.state.conversation_history
    assert len(history) == 4  # 2 user + 2 assistant
    assert history[0] == {"role": "user", "content": "第一个问题"}
    assert history[1] == {"role": "assistant", "content": "好的建议！"}
    assert history[2] == {"role": "user", "content": "第二个问题"}
    assert history[3] == {"role": "assistant", "content": "好的建议！"}


def test_submit_advance_with_ai_feedback():
    """StepResult 包含 ai_feedback 和 suggestions 字段。"""
    builder = WorldBuilder()
    result = builder.start()
    assert hasattr(result, "ai_feedback")
    assert hasattr(result, "suggestions")
    assert isinstance(result.suggestions, list)


def test_world_builder_with_mocked_llm_full_7_steps():
    """Mock LLM 完整 7 步流程（含修真力量体系路径）。"""
    builder = WorldBuilder()

    # Step 1: start → ONE_SENTENCE
    r = builder.start()
    assert r.step == BuilderStep.ONE_SENTENCE

    # Step 2: ONE_SENTENCE → ONE_PARAGRAPH (修真触发)
    r = builder.submit_step("少年在修真大陆修炼成仙，对抗魔族")
    assert r.step == BuilderStep.ONE_PARAGRAPH
    assert builder.state.needs_world_power is True

    # Step 3: ONE_PARAGRAPH → WORLD_POWER
    r = builder.submit_step("第一卷：突破筑基，全书走向封神。")
    assert r.step == BuilderStep.WORLD_POWER

    # Step 4: WORLD_POWER → ONE_PAGE
    r = builder.submit_step("练气→筑基→金丹→元婴→化神")
    assert r.step == BuilderStep.ONE_PAGE

    # Step 5: ONE_PAGE → CHARACTER_ARCS
    r = builder.submit_step("主角：林枫，天才少年。\n反派：魔族大帝。")
    assert r.step == BuilderStep.CHARACTER_ARCS
    assert r.skippable is True

    # Step 6: CHARACTER_ARCS → FOUR_PAGES
    r = builder.submit_step("林枫：懵懂少年 → 筑基成功 → 对抗魔族")
    assert r.step == BuilderStep.FOUR_PAGES
    assert r.skippable is True

    # Step 7: FOUR_PAGES → DONE
    r = builder.submit_step("")
    assert r.step == BuilderStep.DONE

    seed = builder.get_seed_data()
    assert seed["one_sentence"] == "少年在修真大陆修炼成仙，对抗魔族"
    assert len(seed["characters"]) >= 1


def test_sse_stream_format():
    """SSE /worldbuilder/discuss 端点返回正确的 text/event-stream 格式。"""
    import asyncio
    from unittest.mock import patch, AsyncMock

    from fastapi.testclient import TestClient
    from narrative_os.interface.api import app

    # 先创建一个 WorldBuilder 会话
    client = TestClient(app, raise_server_exceptions=False)

    # 创建项目和 world builder 会话
    with (
        patch("narrative_os.interface.api._load_project_or_404") as mock_load,
        patch("narrative_os.interface.api.WorldBuilder") as MockWB,
    ):
        mock_load.return_value = {"meta": {"title": "test"}}

        async def fake_discuss(user_input):
            yield "chunk1"
            yield "chunk2"

        mock_wb_inst = MockWB.return_value
        mock_wb_inst.state = type("S", (), {"step": BuilderStep.ONE_SENTENCE})()
        mock_wb_inst.discuss = fake_discuss

        # 注入会话
        from narrative_os.interface.api import _wb_sessions
        _wb_sessions["test-wb-session"] = mock_wb_inst

        # 调用 SSE 端点
        resp = client.post(
            "/worldbuilder/discuss",
            json={"wb_session_id": "test-wb-session", "message": "你好"},
        )

        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")

        # 清理
        _wb_sessions.pop("test-wb-session", None)
