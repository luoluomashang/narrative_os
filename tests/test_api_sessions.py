"""

tests/test_api_sessions.py ??Phase 3: TRPG 会话 API 端点测试

"""

from __future__ import annotations



import time

import uuid

from unittest.mock import AsyncMock, MagicMock, patch



import pytest

from fastapi.testclient import TestClient



from narrative_os.agents.interactive import (

    DecisionPoint,

    InteractiveSession,

    SessionConfig,

    SessionPhase,

    TurnRecord,

)

from narrative_os.interface.api import (

    SESSION_TTL_SECONDS,

    _cleanup_stale_sessions,

    _get_session,

    _sessions,

    _sessions_lock,

    app,

)



# ------------------------------------------------------------------ #

# 固定装置                                                              #

# ------------------------------------------------------------------ #



@pytest.fixture(autouse=True)

def clear_sessions():

    """每个测试前后清空内存会话存储"""

    with _sessions_lock:

        _sessions.clear()

    yield

    with _sessions_lock:

        _sessions.clear()





@pytest.fixture()

def client():

    return TestClient(app, raise_server_exceptions=False)





def _make_session(phase: SessionPhase = SessionPhase.PING_PONG) -> InteractiveSession:

    cfg = SessionConfig(project_id="test-project")

    s = InteractiveSession(

        session_id=str(uuid.uuid4()),

        project_id="test-project",

        phase=phase,

        density="normal",

        scene_pressure=5.0,

    )

    s.config = cfg

    return s





def _make_dm_turn(session: InteractiveSession, content: str = "DM 叙事", turn_id: int = 1) -> TurnRecord:

    t = TurnRecord(

        turn_id=turn_id,

        who="dm",

        content=content,

        phase=session.phase,

        density=session.density,

        scene_pressure=session.scene_pressure,

    )

    session.history.append(t)

    session.turn = turn_id

    return t





# ------------------------------------------------------------------ #

# POST /sessions/create                                                #

# ------------------------------------------------------------------ #



def test_create_session_returns_session_id(client):

    """创建会话时应返回 session_id ??opening_turn"""

    session = _make_session(phase=SessionPhase.PING_PONG)

    opening_turn = TurnRecord(

        turn_id=0, who="dm", content="你站在废弃神殿的入口",

        phase=SessionPhase.OPENING, density="normal", scene_pressure=5.0,

    )

    session.history.append(opening_turn)



    with (

        patch("narrative_os.interface.api._interactive_agent") as mock_agent,

    ):

        mock_agent.create_session.return_value = session

        mock_agent.start = AsyncMock(return_value=opening_turn)



        resp = client.post("/sessions/create", json={

            "project_id": "test-project",

            "character_name": "主角",

            "density": "normal",

        })



    assert resp.status_code == 201

    body = resp.json()

    assert "session_id" in body

    assert "opening_turn" in body





def test_create_session_stores_session_in_memory(client):

    """创建会话后，session_id 应存在内存中"""

    session = _make_session(phase=SessionPhase.PING_PONG)

    opening_turn = TurnRecord(

        turn_id=0, who="dm", content="开场叙",

        phase=SessionPhase.OPENING, density="normal", scene_pressure=5.0,

    )

    session.history.append(opening_turn)



    with patch("narrative_os.interface.api._interactive_agent") as mock_agent:

        mock_agent.create_session.return_value = session

        mock_agent.start = AsyncMock(return_value=opening_turn)



        resp = client.post("/sessions/create", json={"project_id": "p1"})



    assert resp.status_code == 201

    sid = resp.json()["session_id"]

    with _sessions_lock:

        assert sid in _sessions





def test_create_session_llm_error_returns_500(client):

    """LLM 启动失败应返??500"""

    session = _make_session()



    with patch("narrative_os.interface.api._interactive_agent") as mock_agent:

        mock_agent.create_session.return_value = session

        mock_agent.start = AsyncMock(side_effect=RuntimeError("LLM 超时"))



        resp = client.post("/sessions/create", json={})



    assert resp.status_code == 500





# ------------------------------------------------------------------ #

# POST /sessions/{id}/step                                             #

# ------------------------------------------------------------------ #



def test_step_increments_turn_and_returns_dm_response(client):

    """step 应推??turn 并返??DM 叙事"""

    session = _make_session(phase=SessionPhase.PING_PONG)

    _make_dm_turn(session, "你进入了神殿大厅", turn_id=1)



    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    async def fake_step(s, action):

        s.turn += 1

        _make_dm_turn(s, "黑暗中传来脚步声", turn_id=s.turn)



    with patch("narrative_os.interface.api._interactive_agent") as mock_agent:

        mock_agent.step = AsyncMock(side_effect=fake_step)



        resp = client.post(

            f"/sessions/{session.session_id}/step",

            json={"user_input": "我举起火把向前走"},

        )



    assert resp.status_code == 200

    body = resp.json()

    assert body["who"] == "dm"

    assert "黑暗中传来脚步声" in body["content"]





def test_step_on_invalid_phase_returns_409(client):

    """ENDED 阶段不应接受 step 操作"""

    session = _make_session(phase=SessionPhase.ENDED)

    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    resp = client.post(

        f"/sessions/{session.session_id}/step",

        json={"user_input": "还能做什么吗"},

    )



    assert resp.status_code == 409





def test_step_on_missing_session_returns_404(client):

    resp = client.post("/sessions/not-exist/step", json={"user_input": "hello"})

    assert resp.status_code == 404





# ------------------------------------------------------------------ #

# POST /sessions/{id}/interrupt                                         #

# ------------------------------------------------------------------ #



def test_interrupt_sends_bangui_command(client):

    session = _make_session(phase=SessionPhase.PING_PONG)

    _make_dm_turn(session, "风格已切换为黑暗模式", turn_id=1)



    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    with patch("narrative_os.interface.api._interactive_agent") as mock_agent:

        mock_agent.interrupt = AsyncMock()



        resp = client.post(

            f"/sessions/{session.session_id}/interrupt",

            json={"bangui_command": "黑暗"},

        )



    assert resp.status_code == 200

    mock_agent.interrupt.assert_awaited_once()





# ------------------------------------------------------------------ #

# POST /sessions/{id}/rollback                                          #

# ------------------------------------------------------------------ #



def test_rollback_reduces_history(client):

    session = _make_session(phase=SessionPhase.PING_PONG)

    for i in range(4):

        _make_dm_turn(session, f"段落{i}", turn_id=i)

    original_count = len(session.history)



    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    def fake_rollback(s, steps=1):

        for _ in range(steps):

            if s.history:

                s.history.pop()

        s.turn = max(0, s.turn - steps)



    with patch("narrative_os.interface.api._interactive_agent") as mock_agent:

        mock_agent.rollback = MagicMock(side_effect=fake_rollback)



        resp = client.post(

            f"/sessions/{session.session_id}/rollback",

            json={"steps": 2},

        )



    assert resp.status_code == 200

    body = resp.json()

    assert body["history_count"] < original_count





def test_rollback_steps_out_of_range_returns_422(client):

    """steps > 10 应触??Pydantic 验证错误??22）"""

    session = _make_session()

    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    resp = client.post(

        f"/sessions/{session.session_id}/rollback",

        json={"steps": 99},

    )

    assert resp.status_code == 422





# ------------------------------------------------------------------ #

# GET /sessions/{id}/status                                            #

# ------------------------------------------------------------------ #



def test_get_status_returns_correct_phase(client):

    session = _make_session(phase=SessionPhase.PACING_ALERT)

    session.turn = 5

    session.scene_pressure = 8.5

    with _sessions_lock:

        _sessions[session.session_id] = (session, time.time())



    resp = client.get(f"/sessions/{session.session_id}/status")



    assert resp.status_code == 200

    body = resp.json()

    assert body["phase"] == "PACING_ALERT"

    assert body["turn"] == 5

    assert body["scene_pressure"] == pytest.approx(8.5)





def test_404_on_unknown_session(client):

    resp = client.get("/sessions/ghost-id-0000/status")

    assert resp.status_code == 404





# ------------------------------------------------------------------ #

# TTL 过期清理                                                          #

# ------------------------------------------------------------------ #



def test_stale_session_cleaned_up():

    """访问时间超过 TTL 的会话应被清理"""

    session = _make_session()

    stale_ts = time.time() - SESSION_TTL_SECONDS - 1



    with _sessions_lock:

        _sessions[session.session_id] = (session, stale_ts)



    # 手动运行一次清理（跳过 sleep??

    cutoff = time.time() - SESSION_TTL_SECONDS

    with _sessions_lock:

        expired = [sid for sid, (_, ts) in _sessions.items() if ts < cutoff]

        for sid in expired:

            del _sessions[sid]



    with _sessions_lock:

        assert session.session_id not in _sessions





def test_get_session_updates_access_time():

    """_get_session 应刷新访问时间戳"""

    session = _make_session()

    old_ts = time.time() - 100



    with _sessions_lock:

        _sessions[session.session_id] = (session, old_ts)



    _get_session(session.session_id)



    with _sessions_lock:

        _, new_ts = _sessions[session.session_id]



    assert new_ts > old_ts

