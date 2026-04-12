"""
tests/test_governance_plane.py — 阶段一：GovernancePlane 单元测试

覆盖：
  1.A  PRE_RUN / POST_RUN / POST_COMMIT 钩子按序触发
  1.B  max_cost_per_chapter_usd 生效，超限时主流程中止（CostLimitExceeded）
  1.C  质量分 < 0.6 且 hitl_on_low_quality=True 时流程暂停（返回 hitl_required=True）
"""
from __future__ import annotations

import asyncio
import pytest

from narrative_os.core.governance import (
    CostLimitExceeded,
    GovernanceHook,
    GovernancePlane,
    GovernanceResult,
    RunContext,
    RunPolicy,
    create_run_context,
    get_governance_plane,
)


# ------------------------------------------------------------------ #
# 辅助                                                                  #
# ------------------------------------------------------------------ #

def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------ #
# 1.A  钩子按序触发                                                     #
# ------------------------------------------------------------------ #

class TestHookOrdering:
    def test_pre_post_commit_hooks_fire_in_order(self):
        """PRE_RUN → POST_RUN → POST_COMMIT 的注册、触发顺序正确。"""
        plane = GovernancePlane()
        fired: list[str] = []

        def pre_run_handler(ctx: RunContext) -> GovernanceResult:
            fired.append("PRE_RUN")
            return GovernanceResult(hook=GovernanceHook.PRE_RUN, passed=True)

        async def post_run_handler(ctx: RunContext) -> GovernanceResult:
            fired.append("POST_RUN")
            return GovernanceResult(hook=GovernanceHook.POST_RUN, passed=True)

        def post_commit_handler(ctx: RunContext) -> GovernanceResult:
            fired.append("POST_COMMIT")
            return GovernanceResult(hook=GovernanceHook.POST_COMMIT, passed=True)

        plane.register_hook(GovernanceHook.PRE_RUN, pre_run_handler)
        plane.register_hook(GovernanceHook.POST_RUN, post_run_handler)
        plane.register_hook(GovernanceHook.POST_COMMIT, post_commit_handler)

        ctx = RunContext(project_id="test-ordering", plane=plane)

        _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        _run(plane.run_hooks(GovernanceHook.POST_RUN, ctx))
        _run(plane.run_hooks(GovernanceHook.POST_COMMIT, ctx))

        assert fired == ["PRE_RUN", "POST_RUN", "POST_COMMIT"]

    def test_multiple_handlers_per_hook_all_fired(self):
        """同一 hook 注册多个 handler，全部按序触发。"""
        plane = GovernancePlane()
        log: list[int] = []

        for i in range(3):
            def make_handler(idx):
                def h(ctx: RunContext) -> GovernanceResult:
                    log.append(idx)
                    return GovernanceResult(hook=GovernanceHook.PRE_RUN, passed=True)
                return h
            plane.register_hook(GovernanceHook.PRE_RUN, make_handler(i))

        ctx = RunContext(project_id="test-multi", plane=plane)
        _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        assert log == [0, 1, 2]

    def test_handler_passed_false_stops_chain(self):
        """第一个 handler 返回 passed=False 时，后续 handler 不执行。"""
        plane = GovernancePlane()
        second_called = []

        def first(ctx: RunContext) -> GovernanceResult:
            return GovernanceResult(
                hook=GovernanceHook.PRE_RUN, passed=False, blocked_reason="blocked"
            )

        def second(ctx: RunContext) -> GovernanceResult:
            second_called.append(True)
            return GovernanceResult(hook=GovernanceHook.PRE_RUN, passed=True)

        plane.register_hook(GovernanceHook.PRE_RUN, first)
        plane.register_hook(GovernanceHook.PRE_RUN, second)

        ctx = RunContext(project_id="test-stop", plane=plane)
        result = _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))

        assert not result.passed
        assert result.blocked_reason == "blocked"
        assert second_called == []

    def test_no_handlers_returns_passed(self):
        """未注册任何 handler 时，默认返回 passed=True。"""
        plane = GovernancePlane()
        ctx = RunContext(project_id="test-empty", plane=plane)
        result = _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        assert result.passed is True


# ------------------------------------------------------------------ #
# 1.B  成本超限测试                                                     #
# ------------------------------------------------------------------ #

class TestCostGuard:
    def test_cost_within_limit_passes(self):
        """预估成本未超限，钩子通过。"""
        plane = GovernancePlane()
        policy = RunPolicy(max_cost_per_chapter_usd=1.0)
        plane.save_policy("proj-cost", policy)

        guard = plane.make_cost_guard("proj-cost")
        plane.register_hook(GovernanceHook.PRE_RUN, guard)

        ctx = RunContext(project_id="proj-cost", plane=plane)
        ctx.estimated_cost_usd = 0.3

        result = _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        assert result.passed is True

    def test_cost_exceeds_limit_raises(self):
        """预估成本超出限额时，make_cost_guard 中的 handler 抛出 CostLimitExceeded。"""
        plane = GovernancePlane()
        policy = RunPolicy(max_cost_per_chapter_usd=0.5)
        plane.save_policy("proj-exceed", policy)

        guard = plane.make_cost_guard("proj-exceed")
        plane.register_hook(GovernanceHook.PRE_RUN, guard)

        ctx = RunContext(project_id="proj-exceed", plane=plane)
        ctx.estimated_cost_usd = 1.2

        with pytest.raises(CostLimitExceeded) as exc_info:
            _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))

        assert exc_info.value.estimated == pytest.approx(1.2)
        assert exc_info.value.limit == pytest.approx(0.5)

    def test_cost_near_limit_warning(self):
        """预估成本接近限额（80% 以上）时，返回 passed=True 但包含警告。"""
        plane = GovernancePlane()
        policy = RunPolicy(max_cost_per_chapter_usd=1.0)
        plane.save_policy("proj-warn", policy)

        guard = plane.make_cost_guard("proj-warn")
        plane.register_hook(GovernanceHook.PRE_RUN, guard)

        ctx = RunContext(project_id="proj-warn", plane=plane)
        ctx.estimated_cost_usd = 0.85  # 85%

        result = _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        assert result.passed is True
        assert len(result.warnings) > 0

    def test_default_policy_cost_guard(self):
        """使用默认策略（0.5 USD），成本 0.1 时通过。"""
        plane = GovernancePlane()
        guard = plane.make_cost_guard("proj-default")
        plane.register_hook(GovernanceHook.PRE_RUN, guard)

        ctx = RunContext(project_id="proj-default", plane=plane)
        ctx.estimated_cost_usd = 0.1

        result = _run(plane.run_hooks(GovernanceHook.PRE_RUN, ctx))
        assert result.passed is True


# ------------------------------------------------------------------ #
# 1.C  HITL 触发测试                                                   #
# ------------------------------------------------------------------ #

class TestHITLQualityGuard:
    def test_high_quality_passes(self):
        """质量分高于阈值时，不触发 HITL。"""
        plane = GovernancePlane()
        policy = RunPolicy(hitl_on_low_quality=True, quality_threshold=0.6)
        plane.save_policy("proj-hq", policy)

        guard = plane.make_quality_guard("proj-hq")
        plane.register_hook(GovernanceHook.POST_RUN, guard)

        ctx = RunContext(project_id="proj-hq", plane=plane)
        ctx.quality_score = 0.8

        result = _run(plane.run_hooks(GovernanceHook.POST_RUN, ctx))
        assert result.passed is True
        assert not result.hitl_required

    def test_low_quality_with_hitl_enabled_pauses(self):
        """质量分 < 0.6 且 hitl_on_low_quality=True 时，返回 hitl_required=True。"""
        plane = GovernancePlane()
        policy = RunPolicy(hitl_on_low_quality=True, quality_threshold=0.6)
        plane.save_policy("proj-lq", policy)

        guard = plane.make_quality_guard("proj-lq")
        plane.register_hook(GovernanceHook.POST_RUN, guard)

        ctx = RunContext(project_id="proj-lq", plane=plane)
        ctx.quality_score = 0.45  # < 0.6

        result = _run(plane.run_hooks(GovernanceHook.POST_RUN, ctx))
        assert result.passed is False
        assert result.hitl_required is True
        assert result.blocked_reason is not None
        assert "0.45" in result.blocked_reason or "0.6" in result.blocked_reason

    def test_low_quality_without_hitl_passes(self):
        """质量分 < 0.6 但 hitl_on_low_quality=False 时，正常通过。"""
        plane = GovernancePlane()
        policy = RunPolicy(hitl_on_low_quality=False, quality_threshold=0.6)
        plane.save_policy("proj-lq-nohitl", policy)

        guard = plane.make_quality_guard("proj-lq-nohitl")
        plane.register_hook(GovernanceHook.POST_RUN, guard)

        ctx = RunContext(project_id="proj-lq-nohitl", plane=plane)
        ctx.quality_score = 0.3

        result = _run(plane.run_hooks(GovernanceHook.POST_RUN, ctx))
        assert result.passed is True

    def test_none_quality_score_passes(self):
        """质量分尚未设置（None）时，守卫不阻断。"""
        plane = GovernancePlane()
        policy = RunPolicy(hitl_on_low_quality=True, quality_threshold=0.6)
        plane.save_policy("proj-none-qs", policy)

        guard = plane.make_quality_guard("proj-none-qs")
        plane.register_hook(GovernanceHook.POST_RUN, guard)

        ctx = RunContext(project_id="proj-none-qs", plane=plane)
        ctx.quality_score = None  # 未设置

        result = _run(plane.run_hooks(GovernanceHook.POST_RUN, ctx))
        assert result.passed is True


# ------------------------------------------------------------------ #
# RunContext 单元测试                                                   #
# ------------------------------------------------------------------ #

class TestRunContext:
    def test_create_run_context(self):
        """工厂函数正确创建 RunContext。"""
        ctx = create_run_context("proj-factory", chapter=3, estimated_cost_usd=0.1)
        assert ctx.project_id == "proj-factory"
        assert ctx.chapter == 3
        assert ctx.estimated_cost_usd == pytest.approx(0.1)

    def test_emit_artifact(self):
        """emit_artifact 将数据写入内部列表。"""
        ctx = create_run_context("proj-artifact")

        class FakeArtifact:
            def model_dump(self):
                return {"type": "draft", "content": "hello"}

        _run(ctx.emit_artifact(FakeArtifact()))
        artifacts = ctx.get_artifacts()
        assert len(artifacts) == 1
        assert artifacts[0]["type"] == "draft"

    def test_trigger_hook(self):
        """ctx.trigger() 委托到 plane.run_hooks()。"""
        fired = []

        def handler(ctx: RunContext) -> GovernanceResult:
            fired.append(True)
            return GovernanceResult(hook=GovernanceHook.POST_COMMIT, passed=True)

        ctx = create_run_context("proj-trigger")
        ctx.plane.register_hook(GovernanceHook.POST_COMMIT, handler)
        result = _run(ctx.trigger(GovernanceHook.POST_COMMIT))

        assert result.passed is True
        assert fired == [True]

    def test_global_singleton(self):
        """get_governance_plane 对同一 project_id 返回同一实例。"""
        p1 = get_governance_plane("proj-singleton")
        p2 = get_governance_plane("proj-singleton")
        assert p1 is p2

    def test_elapsed_seconds(self):
        """elapsed_seconds 大于 0。"""
        ctx = create_run_context("proj-time")
        import time
        time.sleep(0.01)
        assert ctx.elapsed_seconds > 0
