"""
tests/test_evolution_canon.py — Phase 4 自查项

涵盖：
  4.C  WorldChangeSet 序列化/反序列化测试
  4.D  CanonCommit 提交测试
  4.E  TRPG 三种结束方式测试
  4.H  全链路集成测试（互动会话结束 → 生成 ChangeSet → 审批 → Canon 提交）
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from narrative_os.core.evolution import (
    CanonCommit,
    ChangeSource,
    ChangeTag,
    SessionCommitMode,
    WorldChange,
    WorldChangeSet,
    get_canon_commit,
)


# ================================================================== #
# 4.C  WorldChangeSet 序列化/反序列化                                   #
# ================================================================== #

class TestWorldChangeSetSerialization:

    def test_world_change_creation(self):
        change = WorldChange(
            source=ChangeSource.INTERACTIVE,
            chapter=3,
            tag=ChangeTag.DRAFT,
            change_type="timeline_event",
            description="林枫击败刘长老",
            after_value={"event": "击败刘长老", "chapter": 3},
        )
        assert change.change_id
        assert change.tag == ChangeTag.DRAFT

    def test_changeset_serialization(self):
        cs = WorldChangeSet(
            project_id="proj_1",
            session_id="sess_abc",
            source=ChangeSource.PIPELINE,
            changes=[
                WorldChange(
                    source=ChangeSource.PIPELINE,
                    chapter=1,
                    tag=ChangeTag.DRAFT,
                    change_type="faction_relation",
                    description="玄剑宗与血魔教关系改变",
                    after_value={"relation": "enemy"},
                )
            ],
        )
        data = cs.model_dump()
        cs2 = WorldChangeSet.model_validate(data)
        assert cs2.changeset_id == cs.changeset_id
        assert cs2.project_id == "proj_1"
        assert len(cs2.changes) == 1
        assert cs2.changes[0].tag == ChangeTag.DRAFT

    def test_three_tag_states_persist(self):
        """三态标签（DRAFT / CANON_PENDING / CANON_CONFIRMED）正确持久化。"""
        changes = [
            WorldChange(tag=ChangeTag.DRAFT),
            WorldChange(tag=ChangeTag.CANON_PENDING),
            WorldChange(tag=ChangeTag.CANON_CONFIRMED),
        ]
        cs = WorldChangeSet(project_id="p1", changes=changes)
        data = cs.model_dump()
        cs2 = WorldChangeSet.model_validate(data)
        tags = {c.tag for c in cs2.changes}
        assert ChangeTag.DRAFT in tags
        assert ChangeTag.CANON_PENDING in tags
        assert ChangeTag.CANON_CONFIRMED in tags

    def test_pending_and_confirmed_helpers(self):
        cs = WorldChangeSet(
            project_id="p1",
            changes=[
                WorldChange(tag=ChangeTag.DRAFT),
                WorldChange(tag=ChangeTag.CANON_PENDING),
                WorldChange(tag=ChangeTag.CANON_CONFIRMED),
            ],
        )
        assert len(cs.pending_changes()) == 2
        assert len(cs.confirmed_changes()) == 1

    def test_change_source_enum_values(self):
        assert ChangeSource.PIPELINE.value == "pipeline"
        assert ChangeSource.INTERACTIVE.value == "interactive"
        assert ChangeSource.SANDBOX_SIM.value == "sandbox_sim"
        assert ChangeSource.MANUAL.value == "manual"

    def test_change_tag_enum_values(self):
        assert ChangeTag.RUNTIME_ONLY.value == "runtime_only"
        assert ChangeTag.DRAFT.value == "draft"
        assert ChangeTag.CANON_PENDING.value == "canon_pending"
        assert ChangeTag.CANON_CONFIRMED.value == "canon_confirmed"


# ================================================================== #
# 4.D  CanonCommit 提交测试                                             #
# ================================================================== #

class TestCanonCommit:

    def test_create_changeset(self):
        cc = CanonCommit()
        cs = cc.create_changeset(
            project_id="proj_test",
            source=ChangeSource.INTERACTIVE,
            session_id="sess_1",
        )
        assert cs.changeset_id
        assert cs.project_id == "proj_test"
        assert cs.session_id == "sess_1"

    def test_list_changesets(self):
        cc = CanonCommit()
        cc.create_changeset(project_id="proj_x")
        cc.create_changeset(project_id="proj_x")
        cc.create_changeset(project_id="proj_y")
        assert len(cc.list_changesets("proj_x")) == 2
        assert len(cc.list_changesets("proj_y")) == 1

    def test_approve_change_promotes_to_pending(self):
        cc = CanonCommit()
        change = WorldChange(tag=ChangeTag.DRAFT, source=ChangeSource.MANUAL)
        cs = cc.create_changeset(project_id="p1", changes=[change])
        cc.approve_change(change.change_id)
        assert change.tag == ChangeTag.CANON_PENDING

    def test_approve_all(self):
        cc = CanonCommit()
        changes = [
            WorldChange(tag=ChangeTag.DRAFT),
            WorldChange(tag=ChangeTag.DRAFT),
            WorldChange(tag=ChangeTag.CANON_CONFIRMED),  # 跳过已确认
        ]
        cs = cc.create_changeset(project_id="p1", changes=changes)
        count = cc.approve_all(cs.changeset_id)
        assert count == 2
        for c in cs.changes[:2]:
            assert c.tag == ChangeTag.CANON_PENDING
        # 已确认的保持不变
        assert cs.changes[2].tag == ChangeTag.CANON_CONFIRMED

    def test_reject_change(self):
        cc = CanonCommit()
        change = WorldChange(tag=ChangeTag.DRAFT)
        cs = cc.create_changeset(project_id="p1", changes=[change])
        cc.reject_change(change.change_id)
        assert change.tag == ChangeTag.RUNTIME_ONLY

    def test_commit_to_canon_requires_pending(self):
        cc = CanonCommit()
        change = WorldChange(tag=ChangeTag.DRAFT)
        cs = cc.create_changeset(project_id="p1", changes=[change])
        # 先审批
        cc.approve_all(cs.changeset_id)
        # 再提交
        committed = cc.commit_to_canon(cs.changeset_id)
        assert len(committed) == 1
        assert change.tag == ChangeTag.CANON_CONFIRMED

    def test_commit_to_canon_updates_sandbox(self):
        """canon_chapter 提交后，sandbox world_rules 正确更新。"""
        from narrative_os.core.world_sandbox import WorldSandboxData
        cc = CanonCommit()
        change = WorldChange(
            tag=ChangeTag.DRAFT,
            change_type="rule_addition",
            description="新增规则",
            after_value={"rule": "守护苍生，不可害民"},
        )
        cs = cc.create_changeset(project_id="p1", changes=[change])
        cc.approve_all(cs.changeset_id)
        sandbox = WorldSandboxData(world_name="测试世界")
        committed = cc.commit_to_canon(cs.changeset_id, sandbox=sandbox)
        assert len(committed) == 1
        assert "守护苍生，不可害民" in sandbox.world_rules

    def test_canon_chapter_requires_confirmation(self):
        """canon_chapter 模式未设置 canon_confirmed 应抛 PermissionError。"""
        cc = CanonCommit()
        change = WorldChange(tag=ChangeTag.CANON_PENDING)
        cs = cc.create_changeset(
            project_id="p1",
            changes=[change],
            commit_mode=SessionCommitMode.CANON_CHAPTER,
        )
        # cs.canon_confirmed 默认 False
        with pytest.raises(PermissionError):
            cc.commit_to_canon(cs.changeset_id)

    def test_canon_chapter_with_confirmation_succeeds(self):
        cc = CanonCommit()
        change = WorldChange(tag=ChangeTag.CANON_PENDING)
        cs = cc.create_changeset(
            project_id="p1",
            changes=[change],
            commit_mode=SessionCommitMode.CANON_CHAPTER,
        )
        cs.canon_confirmed = True
        committed = cc.commit_to_canon(cs.changeset_id)
        assert len(committed) == 1

    def test_get_canon_commit_singleton_per_project(self):
        cc1 = get_canon_commit("proj_singleton")
        cc2 = get_canon_commit("proj_singleton")
        assert cc1 is cc2

    def test_get_canon_commit_different_projects(self):
        cc1 = get_canon_commit("proj_A")
        cc2 = get_canon_commit("proj_B")
        assert cc1 is not cc2


# ================================================================== #
# 4.E  TRPG 三种结束方式                                                #
# ================================================================== #

class TestSessionCommitModes:

    def test_session_only_does_not_promote_changes(self):
        """session_only 不提升变更 tag，不影响主线。"""
        cc = CanonCommit()
        changes = [WorldChange(tag=ChangeTag.RUNTIME_ONLY, description="临时变更")]
        cs = cc.commit_session(
            project_id="proj_1",
            session_id="sess_1",
            mode=SessionCommitMode.SESSION_ONLY,
            changes=changes,
        )
        assert cs.commit_mode == SessionCommitMode.SESSION_ONLY
        # 变更保持 RUNTIME_ONLY，不被提升
        for c in cs.changes:
            assert c.tag == ChangeTag.RUNTIME_ONLY

    def test_draft_chapter_promotes_to_pending(self):
        """阶段五后，draft_chapter 也先进入 CANON_PENDING，等待审批后回流正史。"""
        cc = CanonCommit()
        changes = [WorldChange(tag=ChangeTag.RUNTIME_ONLY, description="互动产生的变更")]
        cs = cc.commit_session(
            project_id="proj_2",
            session_id="sess_2",
            mode=SessionCommitMode.DRAFT_CHAPTER,
            draft_content="这是 DM 生成的章节草稿内容……",
            changes=changes,
        )
        assert cs.commit_mode == SessionCommitMode.DRAFT_CHAPTER
        assert cs.draft_content == "这是 DM 生成的章节草稿内容……"
        # 变更提升为 CANON_PENDING，但未自动进入正史
        for c in cs.changes:
            assert c.tag == ChangeTag.CANON_PENDING

    def test_canon_chapter_requires_confirm_flag(self):
        """canon_chapter 未经二次确认时，变更为 CANON_PENDING 但不自动确认。"""
        cc = CanonCommit()
        changes = [WorldChange(tag=ChangeTag.RUNTIME_ONLY)]
        cs = cc.commit_session(
            project_id="proj_3",
            session_id="sess_3",
            mode=SessionCommitMode.CANON_CHAPTER,
            changes=changes,
            require_canon_confirm=False,  # 未触发二次确认
        )
        assert cs.commit_mode == SessionCommitMode.CANON_CHAPTER
        for c in cs.changes:
            assert c.tag == ChangeTag.CANON_PENDING  # 等待确认
        # canon_confirmed 标志未设置
        assert cs.canon_confirmed is False

    def test_canon_chapter_with_confirm_sets_flag(self):
        """canon_chapter 且 require_canon_confirm=True 时设置 canon_confirmed。"""
        cc = CanonCommit()
        cs = cc.commit_session(
            project_id="proj_4",
            session_id="sess_4",
            mode=SessionCommitMode.CANON_CHAPTER,
            require_canon_confirm=True,
        )
        assert cs.canon_confirmed is True

    def test_session_only_does_not_modify_world(self):
        """session_only 后，正史不受影响（变更不可提交到正史）。"""
        cc = CanonCommit()
        changes = [WorldChange(tag=ChangeTag.RUNTIME_ONLY, change_type="rule_addition",
                               after_value={"rule": "禁止规则"})]
        cs = cc.commit_session(
            project_id="proj_5",
            session_id="sess_5",
            mode=SessionCommitMode.SESSION_ONLY,
            changes=changes,
        )
        # RUNTIME_ONLY 变更不能直接提交到正史
        from narrative_os.core.world_sandbox import WorldSandboxData
        sandbox = WorldSandboxData(world_name="世界")
        committed = cc.commit_to_canon(cs.changeset_id, sandbox=sandbox)
        assert len(committed) == 0  # RUNTIME_ONLY 不属于 CANON_PENDING，不被提交
        assert "禁止规则" not in sandbox.world_rules


# ================================================================== #
# 4.H  全链路集成测试（API 端点）                                        #
# ================================================================== #

class TestCanonCommitAPIEndpoints:

    @pytest.fixture
    def client(self):
        from narrative_os.interface.api import app
        return TestClient(app)

    def _create_session(self, client: TestClient, project_id="test_api_proj") -> str:
        resp = client.post("/sessions/create", json={
            "project_id": project_id,
            "character_name": "柳云烟",
            "world_summary": "测试世界",
        })
        assert resp.status_code == 201
        return resp.json()["session_id"]

    def test_list_changesets_empty(self, client: TestClient):
        resp = client.get("/projects/new_project_empty/changesets")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_commit_session_only(self, client: TestClient):
        session_id = self._create_session(client, project_id="commit_proj")
        resp = client.post(
            f"/projects/commit_proj/sessions/{session_id}/commit",
            json={"mode": "session_only"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["commit_mode"] == "session_only"
        assert "changeset_id" in data

    def test_commit_draft_chapter(self, client: TestClient):
        session_id = self._create_session(client, project_id="draft_proj")
        resp = client.post(
            f"/projects/draft_proj/sessions/{session_id}/commit",
            json={"mode": "draft_chapter", "draft_content": "章节草稿内容"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["commit_mode"] == "draft_chapter"

    def test_commit_invalid_mode_returns_400(self, client: TestClient):
        session_id = self._create_session(client, project_id="err_proj")
        resp = client.post(
            f"/projects/err_proj/sessions/{session_id}/commit",
            json={"mode": "invalid_mode"},
        )
        assert resp.status_code == 400

    def test_list_changesets_after_commit(self, client: TestClient):
        session_id = self._create_session(client, project_id="list_proj")
        client.post(
            f"/projects/list_proj/sessions/{session_id}/commit",
            json={"mode": "session_only"},
        )
        resp = client.get("/projects/list_proj/changesets")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1

    def test_get_changeset_detail(self, client: TestClient):
        session_id = self._create_session(client, project_id="detail_proj")
        commit_resp = client.post(
            f"/projects/detail_proj/sessions/{session_id}/commit",
            json={"mode": "session_only"},
        )
        cs_id = commit_resp.json()["changeset_id"]
        resp = client.get(f"/projects/detail_proj/changesets/{cs_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["changeset_id"] == cs_id
        assert "preview_session_only" in data
        assert "preview_draft_chapter" in data
        assert "preview_canon_chapter" in data

    def test_get_nonexistent_changeset_returns_404(self, client: TestClient):
        resp = client.get("/projects/some_proj/changesets/nonexistent-id")
        assert resp.status_code == 404

    def test_reject_changeset(self, client: TestClient):
        session_id = self._create_session(client, project_id="reject_proj")
        commit_resp = client.post(
            f"/projects/reject_proj/sessions/{session_id}/commit",
            json={"mode": "draft_chapter"},
        )
        cs_id = commit_resp.json()["changeset_id"]
        reject_resp = client.post(f"/projects/reject_proj/changesets/{cs_id}/reject")
        assert reject_resp.status_code == 200
        data = reject_resp.json()
        assert "rejected_count" in data

    def test_approve_changeset(self, client: TestClient):
        session_id = self._create_session(client, project_id="approve_proj")
        commit_resp = client.post(
            f"/projects/approve_proj/sessions/{session_id}/commit",
            json={"mode": "draft_chapter"},
        )
        cs_id = commit_resp.json()["changeset_id"]
        approve_resp = client.post(f"/projects/approve_proj/changesets/{cs_id}/approve")
        assert approve_resp.status_code == 200
        data = approve_resp.json()
        assert "committed_count" in data
