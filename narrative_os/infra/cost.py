"""
infra/cost.py — Token 预算与成本控制

追踪全局 + 按 Skill/Agent 的 token 消耗，
超出预算时抛出 BudgetExceededError，
支持降级链通知。
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import DefaultDict

from narrative_os.infra.config import settings


class BudgetExceededError(RuntimeError):
    """当 Token 消耗超出预算时抛出。"""


@dataclass
class TokenUsage:
    prompt: int = 0
    completion: int = 0

    @property
    def total(self) -> int:
        return self.prompt + self.completion

    def add(self, prompt: int, completion: int) -> None:
        self.prompt += prompt
        self.completion += completion


class CostController:
    """
    全局 Token 预算控制器（进程级单例）。

    使用方式：
        cost_ctrl.record("scene_generator", "writer", prompt=450, completion=1200)
        cost_ctrl.check_budget()  # 超出抛 BudgetExceededError
    """

    def __init__(self, daily_budget: int | None = None) -> None:
        self._budget = daily_budget or settings.daily_token_budget
        self._global = TokenUsage()
        self._by_skill: DefaultDict[str, TokenUsage] = defaultdict(TokenUsage)
        self._by_agent: DefaultDict[str, TokenUsage] = defaultdict(TokenUsage)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def record(
        self,
        skill: str,
        agent: str | None,
        prompt: int,
        completion: int,
    ) -> None:
        """记录一次 LLM 调用的 token 消耗，并即时检查预算。"""
        self._global.add(prompt, completion)
        self._by_skill[skill].add(prompt, completion)
        if agent:
            self._by_agent[agent].add(prompt, completion)
        # 双写 DB（fire-and-forget，不阻断业务逻辑）
        try:
            from narrative_os.infra.database import fire_and_forget  # noqa: PLC0415
            fire_and_forget(self._write_to_db(skill, agent or "", prompt, completion))
        except Exception:
            pass
        self.check_budget()

    async def _write_to_db(
        self, skill: str, agent: str, tokens_in: int, tokens_out: int
    ) -> None:
        """异步写入成本记录到 DB。"""
        try:
            from narrative_os.infra.database import AsyncSessionLocal  # noqa: PLC0415
            from narrative_os.infra.models import CostRecord  # noqa: PLC0415
            cost_usd = (tokens_in + tokens_out) * 0.000002  # $2/1M tokens 估算
            async with AsyncSessionLocal() as db:
                db.add(CostRecord(
                    skill=skill,
                    agent=agent,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost_usd,
                    model="",
                ))
                await db.commit()
        except Exception:
            pass

    def check_budget(self) -> None:
        """如果已超出预算，抛出 BudgetExceededError。"""
        if self._global.total > self._budget:
            raise BudgetExceededError(
                f"Daily token budget exceeded: {self._global.total} / {self._budget}"
            )

    @property
    def usage_ratio(self) -> float:
        """0.0 ~ 1.0，当前消耗占预算比例。"""
        return self._global.total / self._budget if self._budget else 0.0

    def summary(self) -> dict:
        return {
            "budget": self._budget,
            "used": self._global.total,
            "ratio": round(self.usage_ratio, 4),
            "by_skill": {k: v.total for k, v in self._by_skill.items()},
            "by_agent": {k: v.total for k, v in self._by_agent.items()},
        }

    def reset(self) -> None:
        """每日重置（可由调度器在 UTC 00:00 调用）。"""
        self._global = TokenUsage()
        self._by_skill.clear()
        self._by_agent.clear()


# 全局单例
cost_ctrl = CostController()
