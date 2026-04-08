"""
tests/test_infra/test_cost.py — CostController 全量单元测试

覆盖 TokenUsage 和 CostController 的所有公开 / 关键路径。
"""
from __future__ import annotations

import pytest

from narrative_os.infra.cost import BudgetExceededError, CostController, TokenUsage


# ------------------------------------------------------------------ #
# TokenUsage                                                            #
# ------------------------------------------------------------------ #

class TestTokenUsage:
    def test_initial_values(self):
        tu = TokenUsage()
        assert tu.prompt == 0
        assert tu.completion == 0

    def test_total_property(self):
        tu = TokenUsage(prompt=100, completion=200)
        assert tu.total == 300

    def test_total_zero(self):
        tu = TokenUsage()
        assert tu.total == 0

    def test_add_increments(self):
        tu = TokenUsage()
        tu.add(50, 80)
        assert tu.prompt == 50
        assert tu.completion == 80
        assert tu.total == 130

    def test_add_cumulative(self):
        tu = TokenUsage()
        tu.add(100, 200)
        tu.add(50, 100)
        assert tu.prompt == 150
        assert tu.completion == 300
        assert tu.total == 450


# ------------------------------------------------------------------ #
# CostController — 基本记录                                             #
# ------------------------------------------------------------------ #

class TestCostControllerRecord:
    def test_record_increments_global(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=100, completion=200)
        s = ctrl.summary()
        assert s["used"] == 300

    def test_record_by_skill(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("humanize", "editor", prompt=50, completion=100)
        s = ctrl.summary()
        assert s["by_skill"]["humanize"] == 150

    def test_record_by_agent(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=400, completion=800)
        s = ctrl.summary()
        assert s["by_agent"]["writer"] == 1200

    def test_record_no_agent(self):
        ctrl = CostController(daily_budget=10000)
        # agent=None → should not crash, just skip by_agent recording
        ctrl.record("scene", None, prompt=100, completion=200)
        s = ctrl.summary()
        assert s["used"] == 300
        assert len(s["by_agent"]) == 0

    def test_record_multiple_skills(self):
        ctrl = CostController(daily_budget=100000)
        ctrl.record("scene", "writer", prompt=100, completion=100)
        ctrl.record("review", "critic", prompt=50, completion=50)
        s = ctrl.summary()
        assert s["by_skill"]["scene"] == 200
        assert s["by_skill"]["review"] == 100
        assert s["used"] == 300


# ------------------------------------------------------------------ #
# CostController — 预算检查                                             #
# ------------------------------------------------------------------ #

class TestCheckBudget:
    def test_within_budget_no_exception(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=1000, completion=2000)
        # should not raise

    def test_exceeds_budget_raises(self):
        ctrl = CostController(daily_budget=100)
        with pytest.raises(BudgetExceededError, match="Daily token budget exceeded"):
            ctrl.record("scene", "writer", prompt=60, completion=60)  # total=120 > 100

    def test_exactly_at_budget_no_exception(self):
        ctrl = CostController(daily_budget=100)
        ctrl.record("scene", "writer", prompt=50, completion=50)  # total=100, not > 100

    def test_check_budget_manual_call(self):
        ctrl = CostController(daily_budget=50)
        ctrl._global.add(60, 0)  # force exceed without record
        with pytest.raises(BudgetExceededError):
            ctrl.check_budget()

    def test_budget_exceeded_error_is_runtime_error(self):
        assert issubclass(BudgetExceededError, RuntimeError)


# ------------------------------------------------------------------ #
# CostController — usage_ratio                                          #
# ------------------------------------------------------------------ #

class TestUsageRatio:
    def test_zero_usage(self):
        ctrl = CostController(daily_budget=10000)
        assert ctrl.usage_ratio == 0.0

    def test_half_usage(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", None, prompt=5000, completion=0)
        assert ctrl.usage_ratio == pytest.approx(0.5)

    def test_usage_ratio_zero_budget(self):
        ctrl = CostController(daily_budget=0)
        # zero budget → usage_ratio should be 0 (no division by zero)
        ctrl._budget = 0
        assert ctrl.usage_ratio == 0.0


# ------------------------------------------------------------------ #
# CostController — summary                                              #
# ------------------------------------------------------------------ #

class TestSummary:
    def test_summary_keys_present(self):
        ctrl = CostController(daily_budget=5000)
        s = ctrl.summary()
        assert "budget" in s
        assert "used" in s
        assert "ratio" in s
        assert "by_skill" in s
        assert "by_agent" in s

    def test_summary_budget_matches(self):
        ctrl = CostController(daily_budget=12345)
        assert ctrl.summary()["budget"] == 12345

    def test_summary_ratio_rounded(self):
        ctrl = CostController(daily_budget=3)
        ctrl.record("x", None, prompt=1, completion=1)  # used=2
        # ratio = 2/3 ≈ 0.6667 → rounded to 4 decimal places
        ratio = ctrl.summary()["ratio"]
        assert ratio == round(2 / 3, 4)


# ------------------------------------------------------------------ #
# CostController — reset                                                #
# ------------------------------------------------------------------ #

class TestReset:
    def test_reset_clears_global(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=500, completion=1000)
        ctrl.reset()
        assert ctrl.summary()["used"] == 0

    def test_reset_clears_by_skill(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("humanize", "editor", prompt=200, completion=300)
        ctrl.reset()
        assert ctrl.summary()["by_skill"] == {}

    def test_reset_clears_by_agent(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=100, completion=100)
        ctrl.reset()
        assert ctrl.summary()["by_agent"] == {}

    def test_record_after_reset(self):
        ctrl = CostController(daily_budget=10000)
        ctrl.record("scene", "writer", prompt=5000, completion=3000)
        ctrl.reset()
        ctrl.record("review", "critic", prompt=100, completion=50)
        assert ctrl.summary()["used"] == 150
