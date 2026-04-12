"""
tests/test_narrative_compiler.py — Phase 4 自查项

涵盖：
  4.F  NarrativeCompiler 输出测试（Gate10 Lore 注入 + token 裁剪）
  4.G  记忆分池测试
  4.I  回归测试：NarrativeCompiler 输出与旧 ContextBuilder 等价
"""

from __future__ import annotations

import pytest

from narrative_os.core.lorebook import LoreEntry, LoreEntryType, Lorebook
from narrative_os.execution.context_builder import ChapterTarget, ContextBuilder
from narrative_os.execution.narrative_compiler import (
    AuthoringInputError,
    AuthoringRuntimePackage,
    ControlLayerInjection,
    InteractiveRuntimePackage,
    LoreInjection,
    NarrativeCompiler,
)


# ================================================================== #
# 辅助工厂                                                              #
# ================================================================== #

def _make_lorebook() -> Lorebook:
    lb = Lorebook()
    lb.add(LoreEntry(
        title="玄剑宗规则",
        entry_type=LoreEntryType.RULE,
        summary="玄剑宗弟子不得使用邪术，违者逐出师门",
        tags=["规则"],
        trigger_keywords=["玄剑宗", "弟子"],
    ))
    lb.add(LoreEntry(
        title="中州描述",
        entry_type=LoreEntryType.LOCATION,
        summary="天下正道的聚集之地",
        tags=["地点"],
        trigger_keywords=["中州"],
    ))
    return lb


def _make_chapter_target(chapter: int = 3) -> ChapterTarget:
    return ChapterTarget(
        chapter=chapter,
        target_summary="主角被围攻，寻得转机",
        word_count_target=2000,
        tension_target=0.8,
        hook_type="cliffhanger",
    )


def _make_session():
    from narrative_os.agents.interactive import InteractiveAgent, SessionConfig
    from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
    cfg = SessionConfig(project_id="compiler_proj", character_name="柳云烟")
    agent = InteractiveAgent()
    session = agent.create_session(cfg)
    session.world_summary = "玄天大陆，灵力纵横"
    session.control_mode = ControlMode.SEMI_AGENT
    session.mode_config = ControlModeConfig(
        mode=ControlMode.SEMI_AGENT,
        ai_controlled_characters=["林天佑"],
    )
    return session


# ================================================================== #
# 4.F  NarrativeCompiler 输出测试                                      #
# ================================================================== #

class TestNarrativeCompilerAuthoring:

    def test_compile_authoring_returns_package(self):
        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
        )
        assert isinstance(pkg, AuthoringRuntimePackage)
        assert pkg.project_id == "test_proj"
        assert pkg.chapter == 3

    def test_compile_authoring_to_system_prompt(self):
        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
        )
        prompt = pkg.to_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_gate10_lore_injection(self):
        """Gate10 应在输出包和 system_prompt 中包含 Lore 信息。"""
        compiler = NarrativeCompiler()
        lb = _make_lorebook()
        # 制造能命中触发词的角色名
        from narrative_os.core.character import CharacterState
        char = CharacterState(name="玄剑宗弟子甲", health=1.0, emotion="calm")
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
            characters=[char],
            lorebook=lb,
        )
        # Lore 注入应有内容
        assert len(pkg.lore_injection.entries) > 0
        # 应能在 system_prompt 中找到 lore 词条 title 或 summary
        prompt = pkg.to_system_prompt()
        lore_titles = {e["title"] for e in pkg.lore_injection.entries}
        assert any(t in prompt for t in lore_titles), f"lore_titles={lore_titles}\nprompt snippet:\n{prompt[:500]}"

    def test_no_lore_without_lorebook(self):
        """不传 lorebook 时，Lore 注入应为空。"""
        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
        )
        assert len(pkg.lore_injection.entries) == 0

    def test_token_budget_trims_low_priority_gates(self):
        """超出 token 预算时，低优先级 Gate 应被裁剪。"""
        compiler = NarrativeCompiler()
        lb = _make_lorebook()
        # 使用非常小的 token 预算来触发裁剪
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
            lorebook=lb,
            token_budget=5,  # 极小预算，必然触发裁剪
        )
        # 应有裁剪记录
        assert len(pkg.gates_trimmed) > 0

    def test_within_budget_no_trimming(self):
        """在 token 预算内时，不应裁剪任何 Gate。"""
        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=_make_chapter_target(),
            token_budget=100000,  # 超大预算
        )
        assert len(pkg.gates_trimmed) == 0

    def test_package_has_chapter_info(self):
        compiler = NarrativeCompiler()
        target = _make_chapter_target(chapter=7)
        pkg = compiler.compile_authoring(
            project_id="test_proj",
            chapter_target=target,
        )
        assert pkg.chapter == 7

    def test_lore_injection_model(self):
        inj = LoreInjection(entries=[
            {"title": "T1", "summary": "S1", "type": "rule"},
            {"title": "T2", "summary": "S2", "type": "faction"},
        ])
        block = inj.to_prompt_block()
        assert "T1" in block
        assert "T2" in block
        assert "Lorebook" in block or "世界知识" in block

    def test_compile_authoring_requires_published_world(self):
        compiler = NarrativeCompiler()
        with pytest.raises(AuthoringInputError, match="WorldState 尚未发布"):
            compiler.compile_authoring(
                project_id="test_proj",
                chapter_target=_make_chapter_target(),
                characters=[],
                world=None,
                previous_hook="",
                current_volume_goal="卷一目标",
                author_memory_anchors=[],
                require_complete_inputs=True,
            )


class TestNarrativeCompilerInteractive:

    def test_compile_interactive_returns_package(self):
        compiler = NarrativeCompiler()
        session = _make_session()
        pkg = compiler.compile_interactive(
            project_id="compiler_proj",
            session=session,
        )
        assert isinstance(pkg, InteractiveRuntimePackage)
        assert pkg.session_id == session.session_id

    def test_gate11_control_layer_injection(self):
        """Gate11 应包含控制模式信息。"""
        compiler = NarrativeCompiler()
        session = _make_session()
        pkg = compiler.compile_interactive(
            project_id="compiler_proj",
            session=session,
        )
        ctrl = pkg.control_layer
        assert ctrl.control_mode == "semi_agent"
        assert "林天佑" in ctrl.ai_controlled_characters

    def test_interactive_to_system_prompt(self):
        compiler = NarrativeCompiler()
        session = _make_session()
        pkg = compiler.compile_interactive(
            project_id="compiler_proj",
            session=session,
        )
        prompt = pkg.to_system_prompt()
        assert "semi_agent" in prompt or "互动控制层" in prompt or "控制模式" in prompt

    def test_control_layer_model(self):
        ctrl = ControlLayerInjection(
            control_mode="full_agent",
            ai_controlled_characters=["角色A", "角色B"],
            allow_protagonist_proxy=True,
            director_intervention=False,
        )
        block = ctrl.to_prompt_block()
        assert "full_agent" in block
        assert "角色A" in block
        assert "允许" in block


# ================================================================== #
# 4.G  记忆分池测试                                                     #
# ================================================================== #

class TestMemoryPool:

    def test_memory_pool_enum_values(self):
        from narrative_os.core.memory import MemoryPool
        assert MemoryPool.AUTHOR.value == "author"
        assert MemoryPool.TRPG.value == "trpg"
        assert MemoryPool.CANON.value == "canon"

    def test_write_to_author_pool(self, tmp_path):
        from narrative_os.core.memory import MemoryPool, MemorySystem
        mem = MemorySystem(project_id="pool_test", persist_dir=str(tmp_path))
        record = mem.write_memory(
            "创作流水线记忆内容",
            memory_type="event",
            layer="short",
            pool=MemoryPool.AUTHOR,
        )
        assert record.memory_type == "event"

    def test_write_to_trpg_pool(self, tmp_path):
        from narrative_os.core.memory import MemoryPool, MemorySystem
        mem = MemorySystem(project_id="pool_test_trpg", persist_dir=str(tmp_path))
        record = mem.write_memory(
            "TRPG 会话记忆内容",
            memory_type="event",
            layer="short",
            pool=MemoryPool.TRPG,
        )
        assert record.memory_type == "event"

    def test_author_pool_does_not_return_trpg_data(self, tmp_path):
        """检索 AUTHOR 池不返回 TRPG 池内容。"""
        from narrative_os.core.memory import MemoryPool, MemorySystem
        mem = MemorySystem(project_id="isolation_test", persist_dir=str(tmp_path))

        # 写入 AUTHOR 池
        mem.write_memory(
            "创作专属内容_作者记忆",
            memory_type="semantic",
            layer="long",
            importance=0.9,
            pool=MemoryPool.AUTHOR,
        )
        # 写入 TRPG 池
        mem.write_memory(
            "TRPG专属内容_互动记忆",
            memory_type="event",
            layer="short",
            importance=0.9,
            pool=MemoryPool.TRPG,
        )

        # 只查 AUTHOR 池
        author_results = mem.retrieve_memory(
            "专属内容",
            top_k=10,
            pools=[MemoryPool.AUTHOR],
        )
        author_contents = [r.content for r in author_results]
        # AUTHOR 池应包含创作内容
        assert any("创作专属" in c for c in author_contents)
        # TRPG 内容不应出现在 AUTHOR 池检索中
        assert not any("TRPG专属" in c for c in author_contents)

    def test_default_retrieve_excludes_trpg_pool(self, tmp_path):
        """默认检索（不指定 pools）应排除 TRPG 池。"""
        from narrative_os.core.memory import MemoryPool, MemorySystem
        mem = MemorySystem(project_id="default_pool_test", persist_dir=str(tmp_path))
        mem.write_memory(
            "TRPG互动专项数据",
            memory_type="event",
            layer="short",
            importance=0.95,
            pool=MemoryPool.TRPG,
        )
        # 默认检索 = AUTHOR + CANON（不含 TRPG）
        results = mem.retrieve_memory("TRPG互动专项数据", top_k=10)
        contents = [r.content for r in results]
        assert not any("TRPG互动专项" in c for c in contents)

    def test_cross_pool_search(self, tmp_path):
        """显式指定跨池检索时应返回多池数据。"""
        from narrative_os.core.memory import MemoryPool, MemorySystem
        mem = MemorySystem(project_id="cross_pool_test", persist_dir=str(tmp_path))
        mem.write_memory(
            "跨池检索内容_TRPG",
            memory_type="event",
            layer="short",
            pool=MemoryPool.TRPG,
        )
        mem.write_memory(
            "跨池检索内容_AUTHOR",
            memory_type="event",
            layer="short",
            pool=MemoryPool.AUTHOR,
        )
        # 跨池检索
        results = mem.retrieve_memory(
            "跨池检索内容",
            top_k=10,
            pools=[MemoryPool.AUTHOR, MemoryPool.TRPG],
        )
        contents = " ".join(r.content for r in results)
        assert "TRPG" in contents
        assert "AUTHOR" in contents


# ================================================================== #
# 4.I  回归测试：NarrativeCompiler vs 旧 ContextBuilder                #
# ================================================================== #

class TestNarrativeCompilerRegression:

    def test_authoring_package_contains_chapter_info(self):
        """NarrativeCompiler.compile_authoring 包含与 ContextBuilder 相同的章节信息。"""
        ct = _make_chapter_target(chapter=5)
        cb = ContextBuilder()
        ctx = cb.build(chapter_target=ct)
        old_prompt = ctx.to_system_prompt()

        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(project_id="regr_test", chapter_target=ct)
        new_prompt = pkg.to_system_prompt()

        # 两个 prompt 都应包含张力目标
        assert "0.8" in old_prompt or "80%" in old_prompt
        assert "0.8" in new_prompt or "80%" in new_prompt

    def test_compile_authoring_no_crash_without_optionals(self):
        """不传可选参数时 compile_authoring 不崩溃。"""
        compiler = NarrativeCompiler()
        pkg = compiler.compile_authoring(
            project_id="min_test",
            chapter_target=ChapterTarget(chapter=1),
        )
        assert pkg.chapter == 1
        assert isinstance(pkg.to_system_prompt(), str)

    def test_compile_interactive_no_crash_without_optionals(self):
        """不传可选参数时 compile_interactive 不崩溃。"""
        compiler = NarrativeCompiler()
        session = _make_session()
        pkg = compiler.compile_interactive(project_id="min_test_i", session=session)
        assert isinstance(pkg.to_system_prompt(), str)
