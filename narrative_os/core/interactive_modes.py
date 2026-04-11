"""
core/interactive_modes.py — Phase 3: 控制权模式定义

定义四档控制模式枚举和对应行为约束配置。
供 InteractiveSession、SandboxSimulator、API层使用。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class ControlMode(str, Enum):
    USER_DRIVEN = "user_driven"    # Mode1: 纯用户驱动，AI 不替主角行动
    SEMI_AGENT = "semi_agent"      # Mode2: 半代理，AI 润色补足，用户确认
    FULL_AGENT = "full_agent"      # Mode3: 全代理协作，用户给目标，AI 代管执行
    DIRECTOR = "director"          # Mode4: 观察者/导演，用户不下场，可插手暂停


class ControlModeConfig(BaseModel):
    """控制模式详细行为配置。"""
    mode: ControlMode = ControlMode.USER_DRIVEN
    ai_controlled_characters: list[str] = Field(default_factory=list)
    # 哪些角色允许 AI 接管（在 FULL_AGENT/DIRECTOR 模式下生效）
    allow_protagonist_proxy: bool = False
    # 是否允许 AI 代主角补全动作（仅 SEMI_AGENT/FULL_AGENT 可能为 True）
    director_intervention_enabled: bool = True
    # 导演模式下是否允许用户插手暂停

    @property
    def prompt_hint(self) -> str:
        """返回当前模式的提示词说明文本。"""
        hints: dict[ControlMode, str] = {
            ControlMode.USER_DRIVEN: (
                "当前模式：纯用户驱动（Mode1）。"
                "AI 绝对禁止替主角做决策或执行动作。"
                "DM 只负责叙述世界反馈，到达决策点立即截断等待玩家输入。"
            ),
            ControlMode.SEMI_AGENT: (
                "当前模式：半代理协作（Mode2）。"
                "AI 可为主角补全细节动作，但重大决策须明确停顿等待玩家确认。"
                "补全内容在括号内标注「[补全]」。"
            ),
            ControlMode.FULL_AGENT: (
                "当前模式：全代理协作（Mode3）。"
                "用户已给定目标，AI 全权代管主角执行贴近该目标的行动序列。"
                f"AI 接管角色：{', '.join([])}。"
            ),
            ControlMode.DIRECTOR: (
                "当前模式：观察者/导演（Mode4）。"
                "用户不直接扮演角色，以上帝视角观察世界推演。"
                "AI 自主推进所有角色 agenda，用户可随时插手暂停。"
            ),
        }
        return hints.get(self.mode, "")
