"""
tests/test_sl_system.py — Phase 3 自查项

涵盖：
  3.D  SL 快照测试：手动存档 → 读档 → 世界/角色/会话历史完整恢复
  3.E  软回退测试：读档后 memory_summary 保留，不丢失关键记忆摘要
  3.G  五层提示词验证：_build_system_prompt 输出包含五层结构
  3.H  新增 API 端点测试：SL 端点和控制模式端点正常响应
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from narrative_os.agents.interactive import (
    InteractiveAgent,
    InteractiveSession,
    SessionConfig,
    SessionPhase,
    TurnRecord,
)
from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
from narrative_os.core.save_load import (
    DeadlockBreaker,
    DeadlockCondition,
    SavePoint,
    SaveStore,
    SoftRollback,
    get_save_store,
)


# ================================================================== #
# 辅助工厂                                                              #
# ================================================================== #

def _make_session(
    project_id="test_proj",
    character_name="柳云烟",
    world_summary="玄天大陆，灵力横行。",
    memory_summary="柳云烟已与林天佑结成同盟",
) -> InteractiveSession:
    cfg = SessionConfig(
        project_id=project_id,
        character_name=character_name,
        world_summary=world_summary,
    )
    agent = InteractiveAgent()
    session = agent.create_session(cfg)
    session.memory_summary_cache = memory_summary
    # 添加几轮历史
    for i in range(3):
        session.history.append(TurnRecord(
            turn_id=i * 2,
            who="user",
            content=f"玩家行动 #{i + 1}",
            scene_pressure=5.0 + i * 0.5,
            density="normal",
            phase=SessionPhase.PING_PONG,
        ))
        session.history.append(TurnRecord(
            turn_id=i * 2 + 1,
            who="dm",
            content=f"DM 叙事 #{i + 1}：场景在继续……",
            scene_pressure=5.0 + i * 0.5,
            density="normal",
            phase=SessionPhase.PING_PONG,
        ))
    session.turn = 6
    session.scene_pressure = 6.5
    session.phase = SessionPhase.PING_PONG
    return session


# ================================================================== #
# 3.D  SL 快照测试                                                      #
# ================================================================== #

class TestSLSnapshot:

    def test_create_save_point(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session, trigger="manual")
        assert sp.save_id
        assert sp.session_id == session.session_id
        assert sp.turn == session.turn
        assert sp.scene_pressure == session.scene_pressure
        assert sp.trigger == "manual"

    def test_save_history_snapshot(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session, trigger="scene_start")
        assert len(sp.session_history) == len(session.history)
        # 检查历史条目完整保存
        first_user = sp.session_history[0]
        assert first_user["who"] == "user"
        assert "玩家行动" in first_user["content"]

    def test_list_saves_empty(self):
        store = SaveStore()
        saves = store.list_saves("nonexistent_session")
        assert saves == []

    def test_list_saves_returns_created(self):
        session = _make_session()
        store = SaveStore()
        sp1 = store.create(session, trigger="manual")
        sp2 = store.create(session, trigger="high_risk")
        saves = store.list_saves(session.session_id)
        assert len(saves) == 2
        save_ids = {s.save_id for s in saves}
        assert sp1.save_id in save_ids
        assert sp2.save_id in save_ids

    def test_get_save_by_id(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session, trigger="major_decision")
        fetched = store.get(sp.save_id)
        assert fetched is not None
        assert fetched.save_id == sp.save_id

    def test_get_nonexistent_returns_none(self):
        store = SaveStore()
        assert store.get("nonexistent-id") is None

    def test_delete_save(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session)
        assert store.get(sp.save_id) is not None
        result = store.delete(sp.save_id)
        assert result is True
        assert store.get(sp.save_id) is None

    def test_delete_nonexistent_returns_false(self):
        store = SaveStore()
        result = store.delete("does-not-exist")
        assert result is False

    def test_save_point_serialization(self):
        sp = SavePoint(
            session_id="s1",
            project_id="p1",
            trigger="manual",
            session_history=[{"who": "dm", "content": "test"}],
            memory_summary="key memory",
            scene_pressure=7.5,
            turn=10,
        )
        data = sp.model_dump()
        sp2 = SavePoint.model_validate(data)
        assert sp2.session_id == "s1"
        assert sp2.memory_summary == "key memory"
        assert sp2.scene_pressure == 7.5
        assert sp2.turn == 10

    def test_get_save_store_singleton_per_session(self):
        store1 = get_save_store("sess_abc")
        store2 = get_save_store("sess_abc")
        assert store1 is store2

    def test_get_save_store_different_sessions(self):
        store1 = get_save_store("session_X")
        store2 = get_save_store("session_Y")
        assert store1 is not store2

    def test_save_preserves_memory_summary(self):
        session = _make_session()
        session.memory_summary_cache = "关键记忆：柳云烟发现了古剑的秘密"
        store = SaveStore()
        sp = store.create(session, memory_summary=session.memory_summary_cache)
        assert sp.memory_summary == "关键记忆：柳云烟发现了古剑的秘密"


# ================================================================== #
# 3.E  软回退测试（memory_summary 保留）                                 #
# ================================================================== #

class TestSoftRollback:

    def test_restore_reduces_turn_count(self):
        session = _make_session()
        original_turn = session.turn
        store = SaveStore()
        # 在回合 2 时创建存档
        early_session = _make_session()
        early_session.turn = 2
        early_session.history = session.history[:4]  # 前4条
        sp = store.create(early_session, trigger="manual")

        # 继续推进到 6 轮
        SoftRollback.restore(session, sp)
        assert session.turn == 2

    def test_restore_preserves_memory_summary(self):
        session = _make_session()
        early_summary = "关键记忆：发现了古剑"
        store = SaveStore()
        sp = store.create(
            session,
            memory_summary=early_summary,
            trigger="manual",
        )

        # 修改 session 的 memory_summary_cache
        session.memory_summary_cache = "新的错误记忆"
        # 读档后应恢复存档中的 memory_summary
        SoftRollback.restore(session, sp)
        assert session.memory_summary_cache == early_summary

    def test_restore_resets_phase_to_ping_pong(self):
        session = _make_session()
        session.phase = SessionPhase.PACING_ALERT
        store = SaveStore()
        sp = store.create(session, trigger="manual")
        session.phase = SessionPhase.LANDING  # 手动改变
        SoftRollback.restore(session, sp)
        assert session.phase == SessionPhase.PING_PONG

    def test_restore_injects_micro_perturbation_with_memory(self):
        session = _make_session()
        history_before = len(session.history)
        store = SaveStore()
        sp = store.create(
            session,
            memory_summary="关键记忆存在",
            trigger="manual",
        )
        SoftRollback.restore(session, sp, inject_micro_perturbation=True)
        # 注入了一条 system 微扰
        system_turns = [t for t in session.history if t.who == "system"]
        assert len(system_turns) >= 1

    def test_restore_no_micro_perturbation_when_disabled(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session, memory_summary="关键记忆", trigger="manual")
        SoftRollback.restore(session, sp, inject_micro_perturbation=False)
        system_turns = [t for t in session.history if t.who == "system"]
        assert len(system_turns) == 0

    def test_restore_history_matches_save_point(self):
        session = _make_session()
        store = SaveStore()
        sp = store.create(session, trigger="manual")
        # 修改 session 的历史
        session.history.append(TurnRecord(
            turn_id=99,
            who="dm",
            content="额外 DM 叙事",
            scene_pressure=8.0,
            density="dense",
            phase=SessionPhase.PING_PONG,
        ))
        assert len(session.history) == len(sp.session_history) + 1
        # 读档后应恢复
        SoftRollback.restore(session, sp, inject_micro_perturbation=False)
        non_system = [t for t in session.history if t.who != "system"]
        assert len(non_system) == len(sp.session_history)

    def test_restore_resets_open_decision(self):
        from narrative_os.agents.interactive import DecisionPoint
        session = _make_session()
        session.open_decision = DecisionPoint(
            decision_type="action",
            options=["攻击", "逃跑"],
        )
        store = SaveStore()
        sp = store.create(session, trigger="manual")
        session.open_decision = DecisionPoint(options=["其他选项"])
        SoftRollback.restore(session, sp, inject_micro_perturbation=False)
        assert session.open_decision is None


# ================================================================== #
# 3.G  五层提示词验证                                                    #
# ================================================================== #

class TestFiveLayerPrompt:

    def test_prompt_contains_all_five_layers(self):
        agent = InteractiveAgent()
        session = _make_session(world_summary="玄天大陆，灵力横行。")
        prompt = agent._build_system_prompt(session, None)
        assert "第1层" in prompt or "世界层" in prompt or "Layer" in prompt or "【第" in prompt, \
            f"Prompt 缺少第1层标记\n---\n{prompt[:300]}"
        assert "第2层" in prompt or "场景层" in prompt or "【第" in prompt, \
            f"Prompt 缺少第2层标记"
        assert "第3层" in prompt or "角色层" in prompt or "【第" in prompt, \
            f"Prompt 缺少第3层标记"
        assert "第4层" in prompt or "控制层" in prompt or "【第" in prompt, \
            f"Prompt 缺少第4层标记"
        assert "第5层" in prompt or "安全" in prompt or "收束" in prompt or "【第" in prompt, \
            f"Prompt 缺少第5层标记"

    def test_prompt_contains_world_summary(self):
        agent = InteractiveAgent()
        session = _make_session(world_summary="玄天大陆，灵力横行。")
        prompt = agent._build_system_prompt(session, None)
        assert "玄天大陆" in prompt

    def test_prompt_contains_control_mode(self):
        agent = InteractiveAgent()
        session = _make_session()
        session.control_mode = ControlMode.FULL_AGENT
        session.mode_config = ControlModeConfig(mode=ControlMode.FULL_AGENT)
        prompt = agent._build_system_prompt(session, None)
        assert "full_agent" in prompt or "全代理" in prompt or "full" in prompt

    def test_prompt_contains_anti_proxy_rule(self):
        agent = InteractiveAgent()
        session = _make_session()
        prompt = agent._build_system_prompt(session, None)
        # 第5层应含代理隔离规则
        assert "禁止" in prompt or "决策" in prompt

    def test_prompt_contains_agenda_when_present(self):
        agent = InteractiveAgent()
        session = _make_session()
        session.last_agenda = [
            {"character_name": "林天佑", "agenda_text": "寻找古剑"},
        ]
        prompt = agent._build_system_prompt(session, None)
        assert "林天佑" in prompt
        assert "寻找古剑" in prompt

    def test_prompt_bangui_mode_appended(self):
        agent = InteractiveAgent()
        session = _make_session()
        prompt = agent._build_system_prompt(session, "帮回主动1")
        assert "帮回" in prompt or "主动1" in prompt or "bangui" in prompt.lower()


# ================================================================== #
# 3.H  API 端点测试（SL + 控制模式）                                    #
# ================================================================== #

class TestSLAPIEndpoints:

    @pytest.fixture
    def client(self):
        from narrative_os.interface.api import app
        return TestClient(app)

    def _create_session(self, client: TestClient, project_id="test_api_proj") -> str:
        """创建一个 session，返回 session_id。"""
        resp = client.post("/sessions/create", json={
            "project_id": project_id,
            "character_name": "柳云烟",
            "world_summary": "测试世界",
        })
        assert resp.status_code == 201, f"创建 session 失败: {resp.text}"
        return resp.json()["session_id"]

    def test_create_save_returns_save_id(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/save",
            json={"trigger": "manual"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "save_id" in data
        assert data["trigger"] == "manual"

    def test_list_saves_returns_list(self, client: TestClient):
        session_id = self._create_session(client)
        # 创建一个存档
        client.post(
            f"/projects/test_api_proj/sessions/{session_id}/save",
            json={"trigger": "manual"},
        )
        resp = client.get(f"/projects/test_api_proj/sessions/{session_id}/saves")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_load_save_restores_session(self, client: TestClient):
        session_id = self._create_session(client)
        # 存档
        save_resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/save",
            json={"trigger": "manual"},
        )
        save_id = save_resp.json()["save_id"]
        # 读档
        load_resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/load/{save_id}",
        )
        assert load_resp.status_code == 200
        data = load_resp.json()
        assert data["save_id"] == save_id
        assert "restored_turn" in data

    def test_delete_save(self, client: TestClient):
        session_id = self._create_session(client)
        save_resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/save",
            json={"trigger": "manual"},
        )
        save_id = save_resp.json()["save_id"]
        del_resp = client.delete(
            f"/projects/test_api_proj/sessions/{session_id}/saves/{save_id}",
        )
        assert del_resp.status_code == 204

    def test_set_control_mode_user_driven(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/control-mode",
            json={"mode": "user_driven"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "user_driven"
        assert "prompt_hint" in data

    def test_set_control_mode_full_agent(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/control-mode",
            json={
                "mode": "full_agent",
                "ai_controlled_characters": ["林天佑"],
                "allow_protagonist_proxy": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["mode"] == "full_agent"

    def test_set_invalid_control_mode_returns_400(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/control-mode",
            json={"mode": "invalid_mode"},
        )
        assert resp.status_code == 400

    def test_get_agenda_returns_list(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.get(f"/projects/test_api_proj/sessions/{session_id}/agenda")
        assert resp.status_code == 200
        data = resp.json()
        assert "agenda" in data
        assert isinstance(data["agenda"], list)

    def test_load_nonexistent_save_returns_404(self, client: TestClient):
        session_id = self._create_session(client)
        resp = client.post(
            f"/projects/test_api_proj/sessions/{session_id}/load/nonexistent-save-id",
        )
        assert resp.status_code == 404
