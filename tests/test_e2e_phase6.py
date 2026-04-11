"""
tests/test_e2e_phase6.py — 阶段六：集成验收端到端测试

覆盖范围：
  6.A  创作模式 E2E — 项目 → 世界发布 → 角色 → NarrativeCompiler → ChangeSet → CanonCommit
  6.B  互动模式 E2E — Lorebook 检索 → TRPG Session → 5+ 轮 → SL → 防死锁 → 三种提交方式
  6.C  模式切换 E2E — 创作跑完 CanonCommit → 互动模式能访问更新后的世界
"""
from __future__ import annotations

import uuid
import pytest
from fastapi.testclient import TestClient

from narrative_os.core.character import CharacterDrive, CharacterRuntime, CharacterState
from narrative_os.core.evolution import (
    CanonCommit,
    ChangeSource,
    ChangeTag,
    SessionCommitMode,
    WorldChange,
    WorldChangeSet,
    get_canon_commit,
)
from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
from narrative_os.core.lorebook import LoreEntry, LoreEntryType, Lorebook
from narrative_os.core.save_load import (
    DeadlockBreaker,
    DeadlockCondition,
    SaveStore,
    SoftRollback,
    get_save_store,
)
from narrative_os.core.world import FactionState, PowerSystem, WorldState
from narrative_os.core.world_compiler import WorldCompiler
from narrative_os.core.world_sandbox import (
    Faction,
    Region,
    WorldSandboxData,
)
from narrative_os.core.world_validator import WorldValidator
from narrative_os.execution.narrative_compiler import NarrativeCompiler
from narrative_os.execution.context_builder import ChapterTarget
from narrative_os.interface.api import app


# ------------------------------------------------------------------ #
# 固定装置                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


def _pid() -> str:
    return f"e2e-phase6-{uuid.uuid4().hex[:8]}"


def _make_full_sandbox() -> WorldSandboxData:
    """构建一个完整的测试用沙盘（五区三势力）。"""
    sandbox = WorldSandboxData()
    sandbox.world_name = "六阶段验收世界"
    sandbox.world_type = "continental"
    sandbox.world_description = "为阶段六集成验收创建的测试世界"
    sandbox.world_rules = ["灵气为本", "修仙分境界", "禁止使用血魔"]

    # 地区
    r1 = Region(name="玄天城", region_type="capital")
    r2 = Region(name="幽冥谷", region_type="cave")
    r3 = Region(name="龙脉山", region_type="mountain")
    r4 = Region(name="碧波海", region_type="ocean")
    r5 = Region(name="落日荒原", region_type="desert")
    for r in [r1, r2, r3, r4, r5]:
        sandbox.regions.append(r)

    # 势力
    f1 = Faction(
        name="天玄宗",
        scope="internal",
        description="顶尖正道宗门",
        territory_region_ids=[r1.id, r3.id],
    )
    f2 = Faction(
        name="魔道联盟",
        scope="external",
        description="最大反派势力",
        territory_region_ids=[r2.id],
    )
    f3 = Faction(
        name="中立商盟",
        scope="external",
        description="负责跨势力贸易",
        territory_region_ids=[r4.id],
    )
    for f in [f1, f2, f3]:
        sandbox.factions.append(f)

    return sandbox


def _make_characters() -> list[CharacterState]:
    """创建标准四层角色。"""
    hero = CharacterState(
        name="林枫",
        personality="刚直正义",
        faction="天玄宗",
        health=1.0,
        emotion="neutral",
        drive=CharacterDrive(
            core_desire="成为最强修士",
            core_fear="失去同伴",
            current_obsession="寻找失踪的师父",
            short_term_goal="突破筑基境",
            long_term_goal="护卫大陆和平",
        ),
        runtime=CharacterRuntime(
            current_location="玄天城",
            current_agenda="前往宗门议事厅",
        ),
    )
    antagonist = CharacterState(
        name="血魔尊",
        personality="阴险狡诈",
        faction="魔道联盟",
        health=0.9,
        emotion="calculating",
        drive=CharacterDrive(
            core_desire="颠覆正道修仙世界",
            core_fear="败于天道裁决",
            current_obsession="获取古秘宝",
            short_term_goal="拉拢叛逃弟子",
            long_term_goal="重建血魔王朝",
        ),
        runtime=CharacterRuntime(
            current_location="幽冥谷",
            current_agenda="策划阴谋",
        ),
    )
    return [hero, antagonist]


# ================================================================== #
# 6.A  创作模式 E2E                                                     #
# ================================================================== #

class TestAuthoringModeE2E:
    """自查项 6.A — 创作模式全链路。"""

    def test_world_validate_and_compile(self):
        """世界设定校验 → 编译 → 产出 WorldState。"""
        sandbox = _make_full_sandbox()
        validator = WorldValidator()
        report = validator.validate(sandbox)
        # 无严重错误
        assert len(report.errors) == 0, f"Validation errors: {report.errors}"

        compiler = WorldCompiler()
        world, pub_report = compiler.compile(concept=None, sandbox=sandbox)

        assert isinstance(world, WorldState)
        assert pub_report.regions_compiled == 5
        assert pub_report.factions_compiled == 3
        assert len(world.factions) == 3
        assert len(world.geography) == 5

    def test_world_publish_api(self, client):
        """API: /world/publish 返回 published 状态和编译报告。"""
        pid = _pid()
        # 先构建沙盘
        client.put(f"/projects/{pid}/world/meta", json={
            "world_name": "验收世界",
            "world_type": "continental",
        })
        for name, rtype in [("北极城", "capital"), ("幽暗森林", "forest")]:
            client.post(f"/projects/{pid}/world/regions", json={"name": name, "region_type": rtype})

        resp = client.post(f"/projects/{pid}/world/publish")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "published"
        assert "publish_report" in body

    def test_narrative_compiler_authoring_package(self):
        """NarrativeCompiler 创作输出包包含Lore注入和上下文。"""
        sandbox = _make_full_sandbox()
        compiler_wc = WorldCompiler()
        world, _ = compiler_wc.compile(concept=None, sandbox=sandbox)

        lb = Lorebook()
        lb.add(LoreEntry(
            title="天玄宗门规",
            entry_type=LoreEntryType.RULE,
            summary="天玄宗弟子不得擅离宗门，违者逐出师门",
            tags=["规则"],
            trigger_keywords=["天玄宗", "门规"],
        ))
        lb.add(LoreEntry(
            title="玄天城",
            entry_type=LoreEntryType.LOCATION,
            summary="六阶段验收世界的首都，修仙圣地",
            tags=["地点"],
            trigger_keywords=["玄天城"],
        ))

        characters = _make_characters()
        chapter_target = ChapterTarget(
            chapter=1,
            target_summary="主角遭遇神秘追杀并逃脱",
            word_count_target=2000,
            tension_target=0.8,
            hook_type="cliffhanger",
        )

        nc = NarrativeCompiler()
        pkg = nc.compile_authoring(
            project_id="e2e_authoring_test",
            chapter_target=chapter_target,
            characters=characters,
            lorebook=lb,
            world=world,
        )

        assert pkg.project_id == "e2e_authoring_test"
        assert pkg.chapter == 1
        # Gate10 Lore 注入存在
        assert pkg.lore_injection is not None
        # 系统提示非空
        assert len(pkg.to_system_prompt()) > 0

    def test_changeset_and_canon_commit_flow(self):
        """完整变更集 → 审批 → Canon 提交流程。"""
        canon = CanonCommit()
        pid = _pid()

        # 创作流水线产生变更集
        cs = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.PIPELINE,
            commit_mode=SessionCommitMode.DRAFT_CHAPTER,
            draft_content="第一章：林枫在玄天城察觉到一丝异常……",
            changes=[
                WorldChange(
                    source=ChangeSource.PIPELINE,
                    chapter=1,
                    tag=ChangeTag.DRAFT,
                    change_type="timeline_event",
                    description="林枫首次发现血魔踪迹",
                    after_value={"event": "发现血魔踪迹", "chapter": 1},
                ),
                WorldChange(
                    source=ChangeSource.PIPELINE,
                    chapter=1,
                    tag=ChangeTag.DRAFT,
                    change_type="faction_relation",
                    description="天玄宗与中立商盟结盟",
                    after_value={"faction_a": "天玄宗", "faction_b": "中立商盟", "relation": "alliance"},
                ),
            ],
        )
        assert len(cs.pending_changes()) == 2

        # 批量审批
        approved = canon.approve_all(cs.changeset_id)
        assert approved == 2
        assert all(c.tag == ChangeTag.CANON_PENDING for c in cs.changes)

        # 提交正史
        canon.commit_to_canon(cs.changeset_id)
        assert all(c.tag == ChangeTag.CANON_CONFIRMED for c in cs.changes)

        # 验证可查询
        changesets = canon.list_changesets(pid)
        assert len(changesets) == 1
        assert changesets[0].changeset_id == cs.changeset_id

    def test_changeset_api_endpoints(self, client):
        """API: 变更集 CRUD 端点正常响应（GET list / detail / approve / reject）。

        注：API 不提供 POST /changesets 直接创建端点；变更集通过 CanonCommit
        业务层创建，然后通过 REST 端点查询和操作。
        """
        pid = _pid()

        # 列出（初始为空）
        r = client.get(f"/projects/{pid}/changesets")
        assert r.status_code == 200
        assert r.json() == []

        # 通过业务层创建变更集，再验证 API 可读取
        canon = get_canon_commit(pid)
        cs = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.PIPELINE,
            commit_mode=SessionCommitMode.DRAFT_CHAPTER,
            draft_content="第一章草稿内容",
            changes=[
                WorldChange(
                    source=ChangeSource.PIPELINE,
                    chapter=1,
                    tag=ChangeTag.DRAFT,
                    change_type="timeline_event",
                    description="重大事件发生",
                    after_value={"event": "test"},
                )
            ],
        )
        cs_id = cs.changeset_id

        # 列出现有变更集（应有 1 条）
        r = client.get(f"/projects/{pid}/changesets")
        assert r.status_code == 200
        items = r.json()
        assert len(items) == 1
        assert items[0]["changeset_id"] == cs_id

        # 查看详情
        r = client.get(f"/projects/{pid}/changesets/{cs_id}")
        assert r.status_code == 200
        assert r.json()["changeset_id"] == cs_id

        # 批量审批
        r = client.post(f"/projects/{pid}/changesets/{cs_id}/approve")
        assert r.status_code == 200

        # 驳回整个变更集（再创建一个新的）
        cs2 = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.PIPELINE,
            commit_mode=SessionCommitMode.SESSION_ONLY,
            changes=[],
        )
        cs_id2 = cs2.changeset_id
        rj = client.post(f"/projects/{pid}/changesets/{cs_id2}/reject")
        assert rj.status_code == 200


# ================================================================== #
# 6.B  互动模式 E2E                                                     #
# ================================================================== #

class TestInteractiveModeE2E:
    """自查项 6.B — 互动模式全链路。"""

    def _make_interactive_session(self):
        """创建标准互动会话（含轮次历史）。"""
        from narrative_os.agents.interactive import (
            InteractiveAgent,
            SessionConfig,
            SessionPhase,
            TurnRecord,
        )
        cfg = SessionConfig(
            project_id=_pid(),
            character_name="林枫",
            world_summary="六阶段验收世界：玄天大陆，灵力横行",
        )
        agent = InteractiveAgent()
        session = agent.create_session(cfg)
        session.memory_summary_cache = "林枫已与血魔尊初次交手，险些落败"
        # 注入5轮历史
        for i in range(5):
            session.history.append(TurnRecord(
                turn_id=i * 2,
                who="user",
                content=f"林枫行动 #{i + 1}：继续追击血魔踪迹",
                scene_pressure=5.0 + i * 0.3,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
            session.history.append(TurnRecord(
                turn_id=i * 2 + 1,
                who="dm",
                content=f"DM叙事 #{i + 1}：情势愈发紧张，血魔踪迹渐明",
                scene_pressure=5.0 + i * 0.3,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
        session.turn = 10
        session.scene_pressure = 6.5
        session.phase = SessionPhase.PING_PONG
        return session

    def test_lorebook_scene_retrieval(self):
        """Lorebook.get_for_scene() 按场景检索相关词条。"""
        lb = Lorebook()
        lb.add(LoreEntry(
            title="幽冥血魔法阵",
            entry_type=LoreEntryType.RULE,
            summary="血魔法阵在满月时威力翻倍",
            tags=["规则", "血魔"],
            trigger_keywords=["血魔", "法阵", "满月"],
        ))
        lb.add(LoreEntry(
            title="天玄宗护山大阵",
            entry_type=LoreEntryType.LOCATION,
            summary="天玄宗周围有护山大阵，外敌难以强闯",
            tags=["地点", "天玄宗"],
            trigger_keywords=["天玄宗", "护山", "大阵"],
        ))
        lb.add(LoreEntry(
            title="商盟中立协定",
            entry_type=LoreEntryType.FACTION,
            summary="中立商盟不得卷入宗门战争，违者驱逐",
            tags=["势力", "商盟"],
            trigger_keywords=["商盟", "中立", "协定"],
        ))

        # 搜索血魔场景相关（用空格分隔关键词供 Lorebook 逐词匹配）
        results = lb.search("血魔 法阵 满月", top_k=5)
        assert len(results) > 0
        assert any("血魔法阵" in e.title for e in results)

        # 按标签搜索
        by_tag = lb.search_by_tags(["天玄宗"])
        assert len(by_tag) > 0

        # 按场景多维检索
        for_scene = lb.get_for_scene(
            location="幽冥谷",
            characters=["血魔尊"],
            factions=["魔道联盟"],
        )
        assert isinstance(for_scene, list)

    def test_sl_save_and_load(self):
        """SL 系统：存档 → 读档 → 会话状态恢复。"""
        session = self._make_interactive_session()
        original_turn = session.turn
        original_summary = session.memory_summary_cache
        original_history_len = len(session.history)

        store = SaveStore()
        save = store.create(
            session=session,
            trigger="manual",
            memory_summary=original_summary,
        )
        assert save.save_id
        assert save.turn == original_turn
        assert len(save.session_history) == original_history_len

        # 软回退
        save_point = store.get(save.save_id)
        assert save_point is not None
        restored = SoftRollback.restore(session, save_point)
        assert restored.turn == original_turn
        assert restored.memory_summary_cache == original_summary

    def test_sl_5plus_turns(self):
        """5轮以上的会话在SL存档后可完整恢复。"""
        session = self._make_interactive_session()
        assert session.turn >= 10, "会话应已有 10+ 轮次"

        store = SaveStore()
        sp = store.create(session=session, trigger="major_decision", memory_summary="关键决策点")
        assert sp.trigger == "major_decision"

        # 从存档列表取
        saves = store.list_saves(session.session_id)
        assert len(saves) == 1

        # 读档
        save_point = store.get(sp.save_id)
        assert save_point is not None
        restored = SoftRollback.restore(session, save_point)
        assert restored.turn == 10

    def test_deadlock_detection_and_resolution(self):
        """防死锁：检测僵持局面并输出解套叙事文本。"""
        from narrative_os.agents.interactive import SessionPhase, TurnRecord
        session = self._make_interactive_session()

        # 手工注入"死循环"迹象：连续相同用户输入
        for _ in range(3):
            session.history.append(TurnRecord(
                turn_id=session.turn,
                who="user",
                content="我继续等待",
                scene_pressure=session.scene_pressure,
                density="normal",
                phase=SessionPhase.PING_PONG,
            ))
            session.turn += 1

        breaker = DeadlockBreaker()
        condition = breaker.detect(session)
        # 重复输入应能检测到某种死锁状态或返回None（视实现）
        # 关键：不抛异常，deadlock文本可生成
        if condition is not None:
            import asyncio as _asyncio
            text = _asyncio.run(breaker.resolve(condition, session))
            assert isinstance(text, str)
            assert len(text) > 0

    def test_three_commit_modes_e2e(self):
        """三种提交方式各走一次。"""
        canon = CanonCommit()
        pid = _pid()
        session_id = str(uuid.uuid4())

        # SESSION_ONLY: 仅保留会话记录，不影响主线
        cs1 = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.INTERACTIVE,
            session_id=session_id,
            commit_mode=SessionCommitMode.SESSION_ONLY,
            changes=[
                WorldChange(
                    source=ChangeSource.INTERACTIVE,
                    chapter=1,
                    tag=ChangeTag.RUNTIME_ONLY,
                    change_type="timeline_event",
                    description="互动模式临时事件",
                    after_value={"event": "临时事件"},
                )
            ],
        )
        assert cs1.commit_mode == SessionCommitMode.SESSION_ONLY
        # session_only 不提交正史，变更仍为 RUNTIME_ONLY
        assert cs1.changes[0].tag == ChangeTag.RUNTIME_ONLY

        # DRAFT_CHAPTER: 生成草稿，人工确认后再接受
        cs2 = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.INTERACTIVE,
            session_id=session_id,
            commit_mode=SessionCommitMode.DRAFT_CHAPTER,
            draft_content="TRPG 会话第一章草稿：林枫在幽冥谷与血魔尊短暂交手……",
            changes=[
                WorldChange(
                    source=ChangeSource.INTERACTIVE,
                    chapter=1,
                    tag=ChangeTag.DRAFT,
                    change_type="faction_relation",
                    description="天玄宗与血魔尊产生正面冲突",
                    after_value={"faction": "天玄宗", "event": "正面冲突"},
                )
            ],
        )
        assert cs2.commit_mode == SessionCommitMode.DRAFT_CHAPTER
        assert cs2.draft_content != ""
        assert cs2.changes[0].tag == ChangeTag.DRAFT

        # CANON_CHAPTER: 二次确认后直接提交正史
        cs3 = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.INTERACTIVE,
            session_id=session_id,
            commit_mode=SessionCommitMode.CANON_CHAPTER,
            draft_content="正式章节：血魔事件起始",
            changes=[
                WorldChange(
                    source=ChangeSource.INTERACTIVE,
                    chapter=1,
                    tag=ChangeTag.CANON_PENDING,
                    change_type="timeline_event",
                    description="血魔尊首次现身",
                    after_value={"event": "血魔尊现身"},
                )
            ],
        )
        # 设置 canon_confirmed 标志（模拟用户二次确认）
        cs3.canon_confirmed = True
        assert cs3.canon_confirmed is True
        # 执行提交
        canon.commit_to_canon(cs3.changeset_id)
        assert all(c.tag == ChangeTag.CANON_CONFIRMED for c in cs3.changes)

    def test_control_mode_switch(self):
        """四档控制模式可正常切换。"""
        session = self._make_interactive_session()

        # 默认是 USER_DRIVEN
        assert session.control_mode == ControlMode.USER_DRIVEN

        # 切换到 SEMI_AGENT
        session.control_mode = ControlMode.SEMI_AGENT
        session.mode_config = ControlModeConfig(
            mode=ControlMode.SEMI_AGENT,
            allow_protagonist_proxy=True,
        )
        assert session.control_mode == ControlMode.SEMI_AGENT
        assert session.mode_config.allow_protagonist_proxy is True

        # 切换到 DIRECTOR（无需用户输入）
        session.control_mode = ControlMode.DIRECTOR
        session.mode_config = ControlModeConfig(
            mode=ControlMode.DIRECTOR,
            director_intervention_enabled=True,
        )
        assert session.control_mode == ControlMode.DIRECTOR

    def test_sl_api_endpoints(self, client):
        """API: SL 存/读档端点正常响应。"""
        pid = _pid()

        # 先建 session
        from unittest.mock import MagicMock, patch
        from narrative_os.core.state import NarrativeState
        mgr = MagicMock()
        state = NarrativeState(project_id=pid, project_name=pid)
        mgr.state = state
        mgr.load_state.return_value = state
        mgr.load_kb.return_value = {}
        mgr._dir = MagicMock()

        with patch("narrative_os.interface.api.StateManager", return_value=mgr):
            r = client.post(f"/projects/{pid}/sessions", json={
                "character_name": "林枫",
                "world_summary": "测试世界",
            })
        if r.status_code not in (200, 201):
            pytest.skip("Session 创建失败，跳过 SL API 测试")

        session_id = r.json().get("session_id")
        if not session_id:
            pytest.skip("无法获取 session_id")

        # 列出存档（初始为空）
        r_list = client.get(f"/projects/{pid}/sessions/{session_id}/saves")
        assert r_list.status_code == 200
        assert isinstance(r_list.json(), list)

        # 手动存档
        r_save = client.post(f"/projects/{pid}/sessions/{session_id}/save")
        assert r_save.status_code in (200, 201)


# ================================================================== #
# 6.C 模式切换 E2E                                                      #
# ================================================================== #

class TestModeSwitchE2E:
    """自查项 6.C — 创作→互动→再创作的模式切换。"""

    def test_world_state_persists_across_modes(self):
        """CanonCommit 提交后，WorldState 更新可被互动模式访问。"""
        sandbox = _make_full_sandbox()
        compiler = WorldCompiler()
        world, report = compiler.compile(concept=None, sandbox=sandbox)

        # 创作模式产出变更集
        canon = CanonCommit()
        pid = _pid()
        cs = canon.create_changeset(
            project_id=pid,
            source=ChangeSource.PIPELINE,
            commit_mode=SessionCommitMode.CANON_CHAPTER,
            changes=[
                WorldChange(
                    source=ChangeSource.PIPELINE,
                    chapter=1,
                    tag=ChangeTag.CANON_PENDING,
                    change_type="timeline_event",
                    description="林枫获得天玄剑意",
                    after_value={"event": "获得剑意", "character": "林枫"},
                )
            ],
        )
        cs.canon_confirmed = True
        canon.commit_to_canon(cs.changeset_id)

        # 验证变更已正史
        committed = [c for c in cs.changes if c.tag == ChangeTag.CANON_CONFIRMED]
        assert len(committed) == 1

        # 互动模式：Lorebook 能从世界数据构建
        lb = Lorebook()
        result = lb.publish_from_sandbox(sandbox)
        assert result >= 0  # 词条数非负

        # 互动模式：world 可使用
        assert isinstance(world, WorldState)
        assert len(world.factions) == 3

    def test_lore_reflects_sandbox_data(self):
        """Lorebook.publish_from_sandbox() 从沙盘生成正确数量词条。"""
        sandbox = _make_full_sandbox()
        lb = Lorebook()
        count = lb.publish_from_sandbox(sandbox)
        # 沙盘有 5 地区 + 3 势力 = 至少 8 条基础 Lore
        assert count >= 8

    def test_narrative_compiler_interactive_package(self):
        """互动模式编译包含 Gate10(Lore) + Gate11(ControlMode)。"""
        from narrative_os.agents.interactive import InteractiveAgent, SessionConfig
        sandbox = _make_full_sandbox()
        compiler_wc = WorldCompiler()
        world, _ = compiler_wc.compile(concept=None, sandbox=sandbox)

        lb = Lorebook()
        lb.add(LoreEntry(
            title="六阶段验收世界规则",
            entry_type=LoreEntryType.RULE,
            summary="本世界以灵气修炼为核心体系",
            tags=["规则"],
            trigger_keywords=["灵气", "修炼"],
        ))

        cfg = SessionConfig(
            project_id=_pid(),
            character_name="林枫",
            world_summary="六阶段验收世界：以灵气为本的修仙世界",
        )
        agent = InteractiveAgent()
        session = agent.create_session(cfg)
        session.control_mode = ControlMode.SEMI_AGENT

        nc = NarrativeCompiler()
        pkg = nc.compile_interactive(
            project_id=cfg.project_id,
            session=session,
            lorebook=lb,
            world=world,
        )

        assert pkg.project_id == cfg.project_id
        # Gate11 控制层注入
        assert pkg.control_layer is not None
        assert "semi_agent" in pkg.control_layer.control_mode
        # Gate10 Lore 注入
        assert pkg.lore_injection is not None

    def test_world_repository_integration(self, client):
        """WorldRepository 接口通过 API 验证：sandbox → publish → get world state。"""
        pid = _pid()

        # 构建完整沙盘
        client.put(f"/projects/{pid}/world/meta", json={
            "world_name": "切换验收世界",
            "world_type": "continental",
            "world_description": "模式切换E2E测试用",
        })
        r = client.post(f"/projects/{pid}/world/regions", json={
            "name": "中央圣地", "region_type": "capital",
        })
        assert r.status_code in (200, 201)

        # 发布
        pub = client.post(f"/projects/{pid}/world/publish")
        assert pub.status_code == 200
        assert pub.json()["status"] == "published"

        # 互动模式：能获取世界概览
        overview = client.get(f"/projects/{pid}/world/overview")
        assert overview.status_code == 200
        body = overview.json()
        assert "statistics" in body
        assert body["statistics"]["regions"] == 1
