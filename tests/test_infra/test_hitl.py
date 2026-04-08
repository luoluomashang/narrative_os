"""tests/test_infra/test_hitl.py — HITLManager 测试组。"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from narrative_os.infra.hitl import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalStatus,
    HITLManager,
)


# ------------------------------------------------------------------ #
# Fixtures                                                              #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def isolated_hitl():
    """每个测试使用独立的 HITLManager 实例。"""
    HITLManager._instance = None
    yield
    HITLManager._instance = None


# ------------------------------------------------------------------ #
# Singleton                                                             #
# ------------------------------------------------------------------ #

class TestSingleton:
    def test_instance_returns_same_object(self):
        m1 = HITLManager.instance()
        m2 = HITLManager.instance()
        assert m1 is m2

    def test_fresh_instance_has_no_pending(self):
        assert HITLManager.instance().list_pending() == []


# ------------------------------------------------------------------ #
# ApprovalRequest / ApprovalResponse 模型                              #
# ------------------------------------------------------------------ #

class TestModels:
    def test_request_has_gate_id(self):
        req = ApprovalRequest(gate_type="test")
        assert req.gate_id  # uuid생성

    def test_request_ids_unique(self):
        r1 = ApprovalRequest(gate_type="t")
        r2 = ApprovalRequest(gate_type="t")
        assert r1.gate_id != r2.gate_id

    def test_response_defaults(self):
        resp = ApprovalResponse(gate_id="abc", status=ApprovalStatus.APPROVED)
        assert resp.modified_payload is None
        assert resp.comment == ""


# ------------------------------------------------------------------ #
# approve / reject flow                                                 #
# ------------------------------------------------------------------ #

class TestApproveRejectFlow:
    async def test_approve_resolves_checkpoint(self):
        mgr = HITLManager.instance()

        async def resolver():
            await asyncio.sleep(0.01)
            mgr.approve("unknown")  # first call with wrong id is a no-op
            # get the real gate_id
            pending = mgr.list_pending()
            assert len(pending) == 1
            mgr.approve(pending[0].gate_id)

        asyncio.ensure_future(resolver())
        resp = await mgr.checkpoint("test_type", {"key": "val"}, timeout=5.0)
        assert resp.status == ApprovalStatus.APPROVED

    async def test_reject_resolves_checkpoint(self):
        mgr = HITLManager.instance()

        async def resolver():
            await asyncio.sleep(0.01)
            pending = mgr.list_pending()
            mgr.reject(pending[0].gate_id, comment="拒绝理由")

        asyncio.ensure_future(resolver())
        resp = await mgr.checkpoint("test_type", {}, timeout=5.0)
        assert resp.status == ApprovalStatus.REJECTED
        assert resp.comment == "拒绝理由"

    async def test_modify_resolves_with_modified_payload(self):
        mgr = HITLManager.instance()
        new_data = {"modified": True}

        async def resolver():
            await asyncio.sleep(0.01)
            pending = mgr.list_pending()
            mgr.approve(pending[0].gate_id, modified_payload=new_data)

        asyncio.ensure_future(resolver())
        resp = await mgr.checkpoint("test_type", {"orig": True}, timeout=5.0)
        assert resp.status == ApprovalStatus.MODIFIED
        assert resp.modified_payload == new_data

    def test_approve_missing_gate_returns_false(self):
        mgr = HITLManager.instance()
        assert mgr.approve("nonexistent_id") is False

    def test_reject_missing_gate_returns_false(self):
        mgr = HITLManager.instance()
        assert mgr.reject("nonexistent_id") is False

    async def test_pending_gate_tracked(self):
        mgr = HITLManager.instance()
        ck = asyncio.ensure_future(
            mgr.checkpoint("planner", {"x": 1}, timeout=2.0)
        )
        await asyncio.sleep(0.02)
        pending = mgr.list_pending()
        assert len(pending) == 1
        assert pending[0].gate_type == "planner"
        # resolve it
        mgr.approve(pending[0].gate_id)
        await ck


# ------------------------------------------------------------------ #
# timeout                                                               #
# ------------------------------------------------------------------ #

class TestTimeout:
    async def test_timeout_returns_timeout_status(self):
        mgr = HITLManager.instance()
        resp = await mgr.checkpoint("slow_gate", {}, timeout=0.05)
        assert resp.status == ApprovalStatus.TIMEOUT

    async def test_pending_cleared_after_timeout(self):
        mgr = HITLManager.instance()
        await mgr.checkpoint("slow", {}, timeout=0.05)
        assert mgr.list_pending() == []


# ------------------------------------------------------------------ #
# callback handlers                                                     #
# ------------------------------------------------------------------ #

class TestHandlers:
    async def test_sync_handler_called(self):
        mgr = HITLManager.instance()
        calls = []

        def my_handler(req: ApprovalRequest):
            calls.append(req.gate_type)

        mgr.register_handler("mygate", my_handler)

        async def resolver():
            await asyncio.sleep(0.02)
            pending = mgr.list_pending()
            if pending:
                mgr.approve(pending[0].gate_id)

        asyncio.ensure_future(resolver())
        await mgr.checkpoint("mygate", {}, timeout=2.0)
        assert "mygate" in calls

    async def test_async_handler_called(self):
        mgr = HITLManager.instance()
        calls = []

        async def async_handler(req: ApprovalRequest):
            calls.append(req.gate_type)

        mgr.register_handler("asyncgate", async_handler)

        async def resolver():
            await asyncio.sleep(0.02)
            pending = mgr.list_pending()
            if pending:
                mgr.approve(pending[0].gate_id)

        asyncio.ensure_future(resolver())
        await mgr.checkpoint("asyncgate", {}, timeout=2.0)
        assert "asyncgate" in calls

    async def test_handler_error_does_not_crash(self):
        mgr = HITLManager.instance()

        def bad_handler(req):
            raise RuntimeError("handler 崩了")

        mgr.register_handler("badgate", bad_handler)

        async def resolver():
            await asyncio.sleep(0.02)
            pending = mgr.list_pending()
            if pending:
                mgr.approve(pending[0].gate_id)

        asyncio.ensure_future(resolver())
        # Should not raise even with broken handler
        resp = await mgr.checkpoint("badgate", {}, timeout=2.0)
        assert resp.status == ApprovalStatus.APPROVED

    def test_unregister_handler(self):
        mgr = HITLManager.instance()
        mgr.register_handler("removeme", lambda req: None)
        mgr.unregister_handler("removeme")
        assert "removeme" not in mgr._handlers


# ------------------------------------------------------------------ #
# is_pending / list_pending                                             #
# ------------------------------------------------------------------ #

class TestPendingQuery:
    async def test_is_pending_true_while_waiting(self):
        mgr = HITLManager.instance()
        ck = asyncio.ensure_future(mgr.checkpoint("q", {}, timeout=2.0))
        await asyncio.sleep(0.02)
        pending = mgr.list_pending()
        assert len(pending) == 1
        assert mgr.is_pending(pending[0].gate_id)
        mgr.approve(pending[0].gate_id)
        await ck

    def test_is_pending_false_for_unknown(self):
        assert HITLManager.instance().is_pending("ghost") is False
