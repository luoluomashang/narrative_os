"""tests/test_core/test_dsl.py — SkillDSL + SkillRegistry 单元测试"""
import asyncio

import pytest
from narrative_os.skills.dsl import SkillRegistry, SkillRequest, SkillResponse, skill


# ------------------------------------------------------------------ #
# Fixtures — 隔离 registry                                             #
# ------------------------------------------------------------------ #

@pytest.fixture(autouse=True)
def fresh_registry():
    """每个测试使用隔离的 SkillRegistry 实例。"""
    reg = SkillRegistry()
    # Patch Singleton
    original = SkillRegistry._instance
    SkillRegistry._instance = reg
    yield reg
    SkillRegistry._instance = original


# ------------------------------------------------------------------ #
# Registration                                                          #
# ------------------------------------------------------------------ #

class TestRegistration:
    def test_register_and_list(self, fresh_registry: SkillRegistry):
        @fresh_registry.register("test_skill", description="测试用技能")
        def _fn(req: SkillRequest) -> SkillResponse:
            return SkillResponse(skill=req.skill, status="success", output={"result": "ok"})

        skills = fresh_registry.list_skills()
        assert "test_skill" in skills

    def test_duplicate_registration_raises(self, fresh_registry: SkillRegistry):
        def _fn(req):
            return SkillResponse(skill=req.skill, status="success", output={})

        fresh_registry.register("dup_skill")(_fn)
        with pytest.raises(ValueError, match="已注册"):
            fresh_registry.register("dup_skill")(_fn)

    def test_get_meta(self, fresh_registry: SkillRegistry):
        @fresh_registry.register("meta_skill", description="元数据测试")
        def _fn(req):
            return SkillResponse(skill=req.skill, status="success", output={})

        meta = fresh_registry.get_meta("meta_skill")
        assert meta["description"] == "元数据测试"


# ------------------------------------------------------------------ #
# Execute                                                               #
# ------------------------------------------------------------------ #

class TestExecute:
    def test_execute_success(self, fresh_registry: SkillRegistry):
        @fresh_registry.register("add_skill")
        def _fn(req: SkillRequest) -> SkillResponse:
            a = req.inputs.get("a", 0)
            b = req.inputs.get("b", 0)
            return SkillResponse(
                skill=req.skill,
                status="success",
                output={"sum": a + b},
            )

        req = SkillRequest(skill="add_skill", inputs={"a": 3, "b": 4})
        resp = fresh_registry.execute(req)
        assert resp.success
        assert resp.output["sum"] == 7

    def test_execute_missing_skill_returns_failed(self, fresh_registry: SkillRegistry):
        req = SkillRequest(skill="nonexistent_skill", inputs={})
        resp = fresh_registry.execute(req)
        assert resp.status == "failed"
        assert len(resp.errors) > 0

    def test_execute_exception_captured(self, fresh_registry: SkillRegistry):
        @fresh_registry.register("boom_skill")
        def _fn(req: SkillRequest) -> SkillResponse:
            raise RuntimeError("爆炸了")

        req = SkillRequest(skill="boom_skill", inputs={})
        resp = fresh_registry.execute(req)
        assert resp.status == "failed"
        assert any("爆炸了" in e for e in resp.errors)

    def test_execute_async(self, fresh_registry: SkillRegistry):
        @fresh_registry.register("async_skill")
        async def _fn(req: SkillRequest) -> SkillResponse:
            return SkillResponse(skill=req.skill, status="success", output={"async": True})

        req = SkillRequest(skill="async_skill", inputs={})
        resp = asyncio.get_event_loop().run_until_complete(fresh_registry.execute_async(req))
        assert resp.success
        assert resp.output["async"] is True


# ------------------------------------------------------------------ #
# SkillRequest / SkillResponse models                                  #
# ------------------------------------------------------------------ #

class TestModels:
    def test_skill_request_frozen(self):
        req = SkillRequest(skill="s", inputs={"x": 1})
        with pytest.raises(Exception):
            req.skill = "other"  # frozen model should raise

    def test_total_tokens(self):
        resp = SkillResponse(
            skill="s",
            status="success",
            output={},
            token_usage={"prompt": 100, "completion": 50},
        )
        assert resp.total_tokens == 150

    def test_success_property(self):
        resp_ok = SkillResponse(skill="s", status="success", output={})
        resp_fail = SkillResponse(skill="s", status="failed", output={})
        assert resp_ok.success is True
        assert resp_fail.success is False
