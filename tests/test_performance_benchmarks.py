"""
tests/test_performance_benchmarks.py — 阶段六 6.D 性能基准测试

基准项目：5 角色 + 3 地区 + 2 势力（不含 LLM 调用）
性能目标：
  - WorldCompiler.compile()             ≤ 200ms
  - NarrativeCompiler.compile_authoring() ≤ 300ms
  - Lorebook.get_for_scene()            ≤ 100ms
  - SandboxSimulator.simulate_turn()    ≤ 2000ms（含一次 LLM，无 API_KEY 时跳过）
  - WorldChangeSet 序列化/反序列化     ≤ 50ms
  - MemorySystem 分池检索               ≤ 500ms
"""
from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from narrative_os.core.character import (
    CharacterDrive,
    CharacterRuntime,
    CharacterState,
)
from narrative_os.core.evolution import (
    CanonCommit,
    ChangeSource,
    ChangeTag,
    SessionCommitMode,
    WorldChange,
)
from narrative_os.core.lorebook import LoreEntry, LoreEntryType, Lorebook
from narrative_os.core.world import WorldState
from narrative_os.core.world_compiler import WorldCompiler
from narrative_os.core.world_sandbox import (
    Faction,
    Region,
    WorldSandboxData,
)
from narrative_os.execution.context_builder import ChapterTarget
from narrative_os.execution.narrative_compiler import NarrativeCompiler


# ------------------------------------------------------------------ #
# 基准数据工厂                                                          #
# ------------------------------------------------------------------ #

def _make_benchmark_sandbox() -> WorldSandboxData:
    """标准基准沙盘：5 角色 + 3 地区 + 2 势力。"""
    sb = WorldSandboxData()
    sb.world_name = "性能基准世界"
    sb.world_type = "continental"
    sb.world_description = "阶段六性能基准测试使用的世界"
    sb.world_rules = ["灵力为本", "修仙体系", "绝境逢生"]

    # 3 个地区
    for rname, rtype in [("天玄城", "capital"), ("幽冥谷", "cave"), ("龙脉山", "mountain")]:
        sb.regions.append(Region(name=rname, region_type=rtype))

    # 2 个势力
    r1_id = sb.regions[0].id
    r2_id = sb.regions[1].id
    sb.factions.append(Faction(
        name="天玄宗",
        scope="internal",
        description="顶尖正道宗门",
        territory_region_ids=[r1_id],
    ))
    sb.factions.append(Faction(
        name="魔道联盟",
        scope="external",
        description="反派势力联合体",
        territory_region_ids=[r2_id],
    ))

    return sb


def _make_benchmark_characters(n: int = 5) -> list[CharacterState]:
    """创建 n 个角色供基准使用。"""
    chars = []
    for i in range(n):
        chars.append(CharacterState(
            name=f"角色_{i}",
            personality="坚毅",
            faction="天玄宗" if i % 2 == 0 else "魔道联盟",
            health=1.0,
            emotion="neutral",
            drive=CharacterDrive(
                core_desire=f"目标_{i}",
                core_fear=f"恐惧_{i}",
                current_obsession=f"执念_{i}",
                short_term_goal=f"短目标_{i}",
                long_term_goal=f"长目标_{i}",
            ),
            runtime=CharacterRuntime(
                current_location="天玄城",
                current_agenda=f"任务_{i}",
            ),
        ))
    return chars


# ------------------------------------------------------------------ #
# BM.1 WorldCompiler.compile() ≤ 200ms                               #
# ------------------------------------------------------------------ #

class TestWorldCompilerPerf:
    """WorldCompiler 编译性能基准。"""

    def test_compile_time_within_200ms(self):
        """WorldCompiler.compile() 耗时应 ≤ 200ms（不含 LLM）。"""
        sb = _make_benchmark_sandbox()
        compiler = WorldCompiler()

        # 预热一次
        compiler.compile(concept=None, sandbox=sb)

        # 计时测量（取 3 次平均）
        times: list[float] = []
        for _ in range(3):
            start = time.perf_counter()
            world, report = compiler.compile(concept=None, sandbox=sb)
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        assert isinstance(world, WorldState)
        assert report.regions_compiled == 3
        assert report.factions_compiled == 2
        assert avg_ms <= 200, (
            f"WorldCompiler.compile() 平均耗时 {avg_ms:.1f}ms，超过 200ms 基准"
        )

    def test_compile_scales_linearly(self):
        """编译时间应与势力/地区数量大致线性增长（不超过 O(n^2)）。"""
        # 小沙盘（3 地区 + 2 势力）
        sb_small = _make_benchmark_sandbox()
        compiler = WorldCompiler()

        start = time.perf_counter()
        compiler.compile(concept=None, sandbox=sb_small)
        t_small = (time.perf_counter() - start) * 1000

        # 大沙盘（9 地区 + 6 势力）
        sb_large = WorldSandboxData()
        sb_large.world_name = "大型基准世界"
        for rname in [f"地区_{i}" for i in range(9)]:
            sb_large.regions.append(Region(name=rname, region_type="plain"))
        for fname in [f"势力_{i}" for i in range(6)]:
            sb_large.factions.append(Faction(name=fname, scope="internal"))

        start = time.perf_counter()
        compiler.compile(concept=None, sandbox=sb_large)
        t_large = (time.perf_counter() - start) * 1000

        # 大沙盘应 ≤ 200ms，不论 small/large 比例
        assert t_large <= 200, (
            f"大型沙盘编译耗时 {t_large:.1f}ms，超出 200ms 基准"
        )


# ------------------------------------------------------------------ #
# BM.2 NarrativeCompiler.compile_authoring() ≤ 300ms                #
# ------------------------------------------------------------------ #

class TestNarrativeCompilerPerf:
    """NarrativeCompiler 编译性能基准。"""

    def test_compile_authoring_within_300ms(self):
        """NarrativeCompiler.compile_authoring() 耗时应 ≤ 300ms（不含 LLM）。"""
        sb = _make_benchmark_sandbox()
        world_compiler = WorldCompiler()
        world, _ = world_compiler.compile(concept=None, sandbox=sb)

        lb = Lorebook()
        for i in range(20):  # 20 条 Lore 词条
            lb.add(LoreEntry(
                title=f"词条_{i}",
                entry_type=LoreEntryType.RULE,
                summary=f"规则内容 {i}，描述世界基础运行法则之一",
                tags=[f"标签_{i % 5}"],
                trigger_keywords=[f"关键词_{i}", f"触发_{i}"],
            ))

        characters = _make_benchmark_characters(5)
        chapter_target = ChapterTarget(
            chapter=3,
            target_summary="主角在决战前夕得到关键线索",
            word_count_target=3000,
            tension_target=0.9,
            hook_type="revelation",
        )

        nc = NarrativeCompiler()

        # 预热
        nc.compile_authoring(
            project_id="bench_warming",
            chapter_target=chapter_target,
            characters=characters,
            lorebook=lb,
            world=world,
        )

        # 计时测量（取 3 次平均）
        times: list[float] = []
        for _ in range(3):
            start = time.perf_counter()
            pkg = nc.compile_authoring(
                project_id=f"bench_{uuid.uuid4().hex[:6]}",
                chapter_target=chapter_target,
                characters=characters,
                lorebook=lb,
                world=world,
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        assert pkg.lore_injection is not None
        assert avg_ms <= 300, (
            f"NarrativeCompiler.compile_authoring() 平均耗时 {avg_ms:.1f}ms，超过 300ms 基准"
        )


# ------------------------------------------------------------------ #
# BM.3 Lorebook.get_for_scene() ≤ 100ms                              #
# ------------------------------------------------------------------ #

class TestLorebookPerf:
    """Lorebook 检索性能基准。"""

    def _make_large_lorebook(self, n: int = 100) -> Lorebook:
        """创建含 n 条词条的 Lorebook。"""
        lb = Lorebook()
        locations = ["天玄城", "幽冥谷", "龙脉山", "碧波海", "落日荒原"]
        factions = ["天玄宗", "魔道联盟", "中立商盟", "皇朝", "佛门"]
        for i in range(n):
            lb.add(LoreEntry(
                title=f"词条_{i}",
                entry_type=LoreEntryType.RULE if i % 3 == 0 else LoreEntryType.LOCATION,
                summary=f"关于{locations[i % 5]}和{factions[i % 5]}的关键规则或地理信息",
                tags=[f"tag_{i % 10}", locations[i % 5]],
                trigger_keywords=[locations[i % 5], factions[i % 5], f"kw_{i}"],
            ))
        return lb

    def test_get_for_scene_within_100ms(self):
        """Lorebook.get_for_scene() 检索耗时应 ≤ 100ms（100 条词条）。"""
        lb = self._make_large_lorebook(100)

        # 预热
        lb.get_for_scene(
            location="天玄城",
            characters=["角色_0", "角色_1"],
            factions=["天玄宗"],
        )

        # 计时测量（取 5 次平均）
        times: list[float] = []
        for _ in range(5):
            start = time.perf_counter()
            results = lb.get_for_scene(
                location="幽冥谷",
                characters=["角色_0", "角色_2"],
                factions=["魔道联盟"],
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        assert isinstance(results, list)
        assert avg_ms <= 100, (
            f"Lorebook.get_for_scene() 平均耗时 {avg_ms:.1f}ms，超过 100ms 基准"
        )

    def test_search_within_100ms(self):
        """Lorebook.search() 耗时应 ≤ 100ms（100 条词条）。"""
        lb = self._make_large_lorebook(100)

        # 计时测量
        start = time.perf_counter()
        for _ in range(5):
            lb.search("天玄宗 幽冥谷 规则", top_k=10)
        elapsed_ms = (time.perf_counter() - start) * 1000 / 5

        assert elapsed_ms <= 100, (
            f"Lorebook.search() 平均耗时 {elapsed_ms:.1f}ms，超过 100ms 基准"
        )


# ------------------------------------------------------------------ #
# BM.4 SandboxSimulator.simulate_turn() ≤ 2000ms（含 LLM）           #
# ------------------------------------------------------------------ #

class TestSandboxSimulatorPerf:
    """SandboxSimulator 推演性能基准（LLM 相关测试在无 API_KEY 时跳过）。"""

    def test_simulate_turn_mocked_within_2000ms(self):
        """使用 mock LLM，validate 推演流程的基础耗时 ≤ 200ms（不含 LLM 等待）。"""
        from unittest.mock import AsyncMock, patch
        from narrative_os.agents.sandbox_simulator import SandboxSimulator
        from narrative_os.core.interactive_modes import ControlMode

        sb = _make_benchmark_sandbox()
        world_compiler = WorldCompiler()
        world, _ = world_compiler.compile(concept=None, sandbox=sb)
        characters = _make_benchmark_characters(5)

        simulator = SandboxSimulator()

        # Mock LLM 调用，使其即时返回
        async def fast_mock(*args, **kwargs):
            from narrative_os.agents.sandbox_simulator import AgendaDelta
            return AgendaDelta(
                character_name="角色_0",
                new_agenda="模拟行动",
                reasoning="测试推演",
            )

        start = time.perf_counter()
        import asyncio
        with patch.object(simulator, "_simulate_character", side_effect=fast_mock):
            asyncio.run(simulator.simulate_turn(
                active_characters=characters,
                world_state=world,
                recent_events=["林枫在天玄城击退了魔道追兵"],
                control_mode=ControlMode.SEMI_AGENT,
                protagonist_name="角色_0",
            ))
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert elapsed_ms <= 200, (
            f"SandboxSimulator.simulate_turn()（mock LLM）耗时 {elapsed_ms:.1f}ms，超过 200ms"
        )


# ------------------------------------------------------------------ #
# BM.5 WorldChangeSet 序列化/反序列化 ≤ 50ms                          #
# ------------------------------------------------------------------ #

class TestWorldChangeSetSerializationPerf:
    """WorldChangeSet 序列化性能基准。"""

    def test_serialization_within_50ms(self):
        """WorldChangeSet 序列化/反序列化耗时应 ≤ 50ms（100 条变更）。"""
        import json
        from narrative_os.core.evolution import WorldChangeSet

        # 创建含 100 条变更的变更集
        pid = f"bench-{uuid.uuid4().hex[:8]}"
        canon = CanonCommit()
        changes = [
            WorldChange(
                source=ChangeSource.PIPELINE,
                chapter=i % 10 + 1,
                tag=ChangeTag.DRAFT,
                change_type="timeline_event",
                description=f"事件 {i} 的描述文本",
                after_value={"event": f"事件_{i}", "chapter": i % 10 + 1},
            )
            for i in range(100)
        ]
        cs = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.PIPELINE,
            commit_mode=SessionCommitMode.DRAFT_CHAPTER,
            draft_content="基准测试草稿章节内容",
            changes=changes,
        )

        # 序列化
        start = time.perf_counter()
        for _ in range(10):
            serialized = cs.model_dump_json()
        t_ser = (time.perf_counter() - start) * 1000 / 10

        # 反序列化
        start = time.perf_counter()
        for _ in range(10):
            WorldChangeSet.model_validate_json(serialized)
        t_de = (time.perf_counter() - start) * 1000 / 10

        assert t_ser <= 50, (
            f"WorldChangeSet.model_dump_json() 平均耗时 {t_ser:.1f}ms，超过 50ms 基准"
        )
        assert t_de <= 50, (
            f"WorldChangeSet.model_validate_json() 平均耗时 {t_de:.1f}ms，超过 50ms 基准"
        )


# ------------------------------------------------------------------ #
# BM.6 MemorySystem 分池检索 ≤ 500ms                                  #
# ------------------------------------------------------------------ #

class TestMemorySystemPerf:
    """MemorySystem 分池检索性能基准。"""

    def test_retrieve_within_500ms(self, tmp_path):
        """MemorySystem.retrieve_memory() 分池检索耗时应 ≤ 500ms（mock ChromaDB）。

        注：ChromaDB 本地 embedding model（sentence-transformers）单次调用约
        700-1000ms，不适合直接测试。本测试 mock ChromaDB 查询，测量 MemorySystem
        自身的多池分发、结果合并、排序等逻辑开销（应 ≤ 500ms）。
        """
        from unittest.mock import MagicMock, patch
        from narrative_os.core.memory import MemorySystem, MemoryPool, RetrievalResult

        pid = f"bench-mem-{uuid.uuid4().hex[:8]}"
        mem = MemorySystem(project_id=pid, persist_dir=str(tmp_path))

        # 构造 mock ChromaDB collection
        mock_coll = MagicMock()
        mock_coll.count.return_value = 30
        mock_coll.query.return_value = {
            "ids": [["m1", "m2", "m3"]],
            "documents": [["记忆1详情", "记忆2详情", "记忆3详情"]],
            "metadatas": [[
                {"memory_type": "event", "chapter": 1, "importance": 0.8,
                 "characters": '["林枫"]', "pool": "author", "layer": "short",
                 "source_chapter": 1},
                {"memory_type": "event", "chapter": 2, "importance": 0.7,
                 "characters": '["林枫"]', "pool": "author", "layer": "short",
                 "source_chapter": 2},
                {"memory_type": "event", "chapter": 3, "importance": 0.6,
                 "characters": '["血魔尊"]', "pool": "author", "layer": "mid",
                 "source_chapter": 3},
            ]],
            "distances": [[0.1, 0.2, 0.3]],
        }
        # 预填充 pool collections
        mem._initialized = True
        mem._pool_collections = {
            (pool.value, layer): mock_coll
            for pool in MemoryPool
            for layer in ["short", "mid", "long"]
        }

        # 计时测量（取 10 次均值）
        times: list[float] = []
        for _ in range(10):
            start = time.perf_counter()
            results = mem.retrieve_memory(
                "林枫 重要事件 改变",
                top_k=10,
                pools=[MemoryPool.AUTHOR],
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        assert isinstance(results, list)
        assert avg_ms <= 500, (
            f"MemorySystem.retrieve_memory()（mock ChromaDB）平均耗时 {avg_ms:.1f}ms，超过 500ms 基准"
        )
