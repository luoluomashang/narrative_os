"""
agents/interactive.py — Phase 3 (TRPG互动模式): Interactive Agent

12 阶段状态机：
  INIT → OPENING → PING_PONG ⇄ ROLLBACK / INTERRUPT
                ↓ PACING_ALERT（张力异常）
                ↓ LANDING → MAINTENANCE → ENDED

核心设计原则（源自 trpg_immersion.yaml）：
  ① Agency Isolation：DM 绝对禁止替玩家决策
  ② 决策驱动截断：到达决策节点立即截断，无论字数
  ③ 决策密度自动切换（scene_pressure >= 8 → dense / 4-8 → normal / <4 → sparse）

决策密度：
  dense   50-150 字/片段
  normal  150-300 字/片段
  sparse  400-800 字/片段

帮回系统（bangui）：
  支持甲类 8 指令 + 回滚 + 中断
  输入格式：以 "帮回" 开头（或 "/" 前缀）

API：
    agent = InteractiveAgent()
    session = agent.create_session(config)
    turn = await agent.start(session)
    turn = await agent.step(session, user_action="我向前冲！")
    session = agent.rollback(session, steps=1)
    turn = await agent.interrupt(session, "帮回主动1")
    output = agent.land(session)
"""

from __future__ import annotations

import re
import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from narrative_os.core.interactive_modes import ControlMode, ControlModeConfig
from narrative_os.execution.llm_router import (
    get_default_routing_strategy,
    LLMRequest,
    LLMRouter,
    ModelTier,
    RoutingStrategy,
)
from narrative_os.infra.config import load_yaml
from narrative_os.infra.logging import logger


# ------------------------------------------------------------------ #
# 常量                                                                  #
# ------------------------------------------------------------------ #

DecisionDensity = Literal["dense", "normal", "sparse"]

_DENSITY_LIMITS: dict[str, int] = {
    "dense":  150,
    "normal": 300,
    "sparse": 800,
}

_BANGUI_IDS = {
    "帮回主动1", "帮回主动2",
    "帮回被动1", "帮回被动2",
    "帮回黑暗1", "帮回黑暗2",
    "帮回推进1", "帮回推进2",
}

# 代理权侵犯模式（DM 不得替玩家决策）
_PROXY_PATTERNS: list[str] = [
    r"你决定", r"你选择了", r"你毫不犹豫", r"主角选择",
    r"你立刻", r"你于是", r"你没有犹豫",
]


# ------------------------------------------------------------------ #
# 状态枚举                                                              #
# ------------------------------------------------------------------ #

class SessionPhase(str, Enum):
    INIT        = "INIT"
    OPENING     = "OPENING"
    PING_PONG   = "PING_PONG"
    ROLLBACK    = "ROLLBACK"
    INTERRUPT   = "INTERRUPT"
    PACING_ALERT = "PACING_ALERT"
    LANDING     = "LANDING"
    MAINTENANCE = "MAINTENANCE"
    ENDED       = "ENDED"


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class DecisionPoint(BaseModel):
    """DM 截断时输出的决策节点。"""
    decision_type: str = "action"   # action / dialogue / moral / tactical
    options: list[str] = Field(default_factory=list)
    risk_levels: list[str] = Field(default_factory=list)  # per-option: safe / risky / dangerous
    truncated_at: str = ""          # 触发截断的短语描述
    is_free_action: bool = False    # True 时表示玩家自由决策（无结构化选项）


class TurnRecord(BaseModel):
    """单轮交互记录。"""
    turn_id: int
    who: Literal["dm", "user", "system"]
    content: str
    scene_pressure: float = 5.0
    density: DecisionDensity = "normal"
    phase: SessionPhase = SessionPhase.PING_PONG
    decision: DecisionPoint | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionConfig(BaseModel):
    """创建 Session 的初始配置。"""
    project_id: str = "default"
    character_name: str = "主角"
    world_summary: str = ""
    opening_prompt: str = ""
    initial_pressure: float = 5.0
    density_override: DecisionDensity | None = None
    max_history_turns: int = 30     # 滑动窗口大小


class InteractiveSession(BaseModel):
    """TRPG 会话状态容器。"""
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str = "default"
    phase: SessionPhase = SessionPhase.INIT
    turn: int = 0
    scene_pressure: float = 5.0
    density: DecisionDensity = "normal"
    history: list[TurnRecord] = Field(default_factory=list)
    open_decision: DecisionPoint | None = None
    character_name: str = "主角"
    world_summary: str = ""
    config: SessionConfig = Field(default_factory=SessionConfig)
    emotional_temperature: dict = Field(
        default_factory=lambda: {"base": "neutral", "current": 5.0, "drift": 0.0}
    )
    turn_char_count: int = 0
    # Phase 3: 控制权模式
    control_mode: ControlMode = ControlMode.USER_DRIVEN
    mode_config: ControlModeConfig = Field(default_factory=ControlModeConfig)
    # Phase 3: SL / 防死锁
    memory_summary_cache: str = ""
    # Phase 3: Agenda 状态缓存（上轮推演结果）
    last_agenda: list[dict] = Field(default_factory=list)


# ------------------------------------------------------------------ #
# InteractiveAgent                                                      #
# ------------------------------------------------------------------ #

class InteractiveAgent:
    """
    TRPG 互动模式 Agent。

    典型用法：
        agent = InteractiveAgent()
        session = agent.create_session(SessionConfig(opening_prompt="一处废弃的神殿…"))
        turn    = await agent.start(session)      # DM 开场
        turn    = await agent.step(session, "我举起火把，走向神坛。")  # 玩家行动
        session = agent.rollback(session, steps=1)
        output  = agent.land(session)
    """

    def __init__(self, router: LLMRouter | None = None) -> None:
        self._router = router or LLMRouter()
        self._trpg_cfg: dict[str, Any] | None = None
        self._bangui_cfg: dict[str, Any] | None = None

    # ---------------------------------------------------------------- #
    # 会话管理                                                            #
    # ---------------------------------------------------------------- #

    def create_session(self, config: SessionConfig) -> InteractiveSession:
        """创建新 Session，返回 INIT 状态。"""
        density = config.density_override or "normal"
        return InteractiveSession(
            project_id=config.project_id,
            scene_pressure=config.initial_pressure,
            density=density,
            character_name=config.character_name,
            world_summary=config.world_summary,
            config=config,
        )

    # ---------------------------------------------------------------- #
    # 主要操作                                                            #
    # ---------------------------------------------------------------- #

    async def start(self, session: InteractiveSession) -> TurnRecord:
        """
        INIT → OPENING：DM 生成开场白，包含第一个决策截断。
        """
        assert session.phase == SessionPhase.INIT, \
            f"start() 只能在 INIT 阶段调用，当前: {session.phase}"

        session.phase = SessionPhase.OPENING
        prompt = session.config.opening_prompt or session.world_summary or "一段未知的旅途即将开始。"
        turn = await self._dm_narrate(session, context_hint=prompt)
        session.phase = SessionPhase.PING_PONG
        return turn

    async def step(self, session: InteractiveSession, user_action: str) -> TurnRecord:
        """
        PING_PONG: 记录玩家行动 → DM 响应。

        返回 DM 生成的 TurnRecord（含下一个 DecisionPoint）。
        """
        assert session.phase in {SessionPhase.PING_PONG, SessionPhase.PACING_ALERT}, \
            f"step() 只能在 PING_PONG 阶段调用，当前: {session.phase}"

        # 先记录玩家行动
        user_turn = TurnRecord(
            turn_id=session.turn,
            who="user",
            content=user_action,
            scene_pressure=session.scene_pressure,
            density=session.density,
            phase=SessionPhase.PING_PONG,
        )
        session.history.append(user_turn)
        session.turn += 1

        # 清除上轮开放决策
        session.open_decision = None

        # 更新张力（简单启发：含"攻击/死/逃/危"字样时升压）
        self._update_pressure(session, user_action)

        # DM 响应
        dm_turn = await self._dm_narrate(session, context_hint=user_action)

        # 节奏警报检测
        if self._check_pacing_alert(session):
            session.phase = SessionPhase.PACING_ALERT
            recent_dm = [t for t in session.history if t.who == "dm"]
            near_limit = session.turn >= session.config.max_history_turns * 0.9
            sustained = (len(recent_dm) >= 3
                         and all(t.scene_pressure >= 8.0 for t in recent_dm[-3:]))
            reasons = []
            if near_limit:
                reasons.append(f"回合数 {session.turn}/{session.config.max_history_turns} 接近上限")
            if sustained:
                reasons.append("连续 3 轮高压（≥8）")
            dm_turn.metadata["pacing_alert_reason"] = "；".join(reasons)

        return dm_turn

    def rollback(self, session: InteractiveSession, steps: int = 1) -> InteractiveSession:
        """
        回滚 N 轮（默认 1 轮），移除历史末尾 steps*2 条（DM+用户各一条）。
        phase 回到 PING_PONG。
        """
        remove = steps * 2
        if remove > len(session.history):
            remove = len(session.history)

        session.history = session.history[:-remove] if remove else session.history
        session.turn = max(0, session.turn - steps)
        session.phase = SessionPhase.PING_PONG
        session.open_decision = None

        return session

    async def interrupt(self, session: InteractiveSession, bangui_command: str) -> TurnRecord:
        """
        处理帮回指令（甲类 8 种）。
        返回 DM 根据帮回模式生成的片段。
        """
        session.phase = SessionPhase.INTERRUPT
        bang = self._normalize_bangui(bangui_command)
        hint = self._bangui_hint(bang)

        turn = await self._dm_narrate(session, context_hint=hint, bangui_mode=bang)
        session.phase = SessionPhase.PING_PONG
        return turn

    def land(self, session: InteractiveSession) -> dict[str, Any]:
        """
        LANDING → MAINTENANCE → ENDED：结束会话，将 DM 叙事历史组装为章节文本并输出。

        从 session.history 中提取所有未回滚的 DM 叙事碎片，拼接为完整章节文本，
        提取 hook（最后一段 DM 叙事的尾部 200 字），统计字数，返回结构化结果。
        """
        if session.phase not in {SessionPhase.ENDED, SessionPhase.MAINTENANCE}:
            session.phase = SessionPhase.LANDING

        # 提取所有 DM 叙事文本（按 turn_id 排序）
        dm_turns = sorted(
            [t for t in session.history if t.who == "dm" and not getattr(t, "rolled_back", False)],
            key=lambda t: t.turn_id,
        )

        # 拼接章节文本
        chapter_parts: list[str] = []
        for turn in dm_turns:
            if turn.content and turn.content.strip():
                chapter_parts.append(turn.content.strip())

        chapter_text = "\n\n".join(chapter_parts) if chapter_parts else ""

        # 提取 hook：最后一段 DM 叙事的末尾 200 字
        hook = ""
        if chapter_parts:
            last_part = chapter_parts[-1]
            hook = last_part[-200:] if len(last_part) > 200 else last_part

        # 提取角色变化（从 player turns 中推断）
        player_turns = [t for t in session.history if t.who == "user" and not getattr(t, "rolled_back", False)]
        character_deltas: list[dict[str, Any]] = []
        if session.character_name:
            character_deltas.append({
                "name": session.character_name,
                "actions_count": len(player_turns),
                "final_pressure": session.scene_pressure,
            })

        # 历史摘要（前 3 个 DM 片段的首句）
        summary_sentences: list[str] = []
        for part in chapter_parts[:3]:
            first_sent = part.split("。")[0] if "。" in part else part[:50]
            summary_sentences.append(first_sent)
        history_summary = "；".join(summary_sentences)

        session.phase = SessionPhase.ENDED
        logger.info("trpg_session_ended", session_id=session.session_id, turns=session.turn)

        return {
            "session_id": session.session_id,
            "chapter_text": chapter_text,
            "word_count": len(chapter_text),
            "hook": hook,
            "character_deltas": character_deltas,
            "user_actions": character_deltas,  # 向后兼容旧字段名
            "turns": session.turn,
            "final_pressure": session.scene_pressure,
            "history_summary": history_summary,
            "dm_fragments": len(dm_turns),
        }

    # ---------------------------------------------------------------- #
    # DM 生成核心                                                         #
    # ---------------------------------------------------------------- #

    async def _dm_narrate(
        self,
        session: InteractiveSession,
        context_hint: str = "",
        bangui_mode: str | None = None,
    ) -> TurnRecord:
        system = self._build_system_prompt(session, bangui_mode)
        history_ctx = self._build_history_context(session)
        bangui_params = self._bangui_llm_params(bangui_mode)

        metadata: dict[str, Any] = {}
        content = ""
        reprompt_hint = ""

        for attempt in range(3):
            user_content = (
                f"[当前场景压力: {session.scene_pressure:.1f}/10]\n"
                f"[决策密度: {session.density}]\n"
                + (f"[帮回模式: {bangui_mode}]\n" if bangui_mode else "")
                + (f"[上下文提示: {context_hint}]\n" if context_hint else "")
                + reprompt_hint
                + "\n请继续叙事，到达决策截断点时立即停止，输出决策选项。"
            )

            llm_req = LLMRequest(
                task_type="trpg_narration",
                system_prompt=system,
                messages=history_ctx + [{"role": "user", "content": user_content}],
                        strategy=get_default_routing_strategy(),
                tier_override=ModelTier.MEDIUM,
                max_tokens=int(
                    _DENSITY_LIMITS[session.density]
                    * bangui_params.get("max_tokens_multiplier", 3.0)
                ),
                temperature=bangui_params.get("temperature", 0.80),
                skill_name="interactive_agent",
            )
            resp = await self._router.call(llm_req)
            content = resp.content.strip()

            # 决策驱动截断
            content = self._apply_truncation(content, session.density)

            # 代理权隔离守卫
            violation = self._detect_agency_violation(content)
            if not violation:
                break
            if attempt < 2:
                reprompt_hint = (
                    "\n[系统纠错] 上一次叙述越权替玩家决策，请重新叙述，"
                    "停在决策点前，不要代替玩家选择或行动。"
                )
            else:
                metadata["agency_violation_warning"] = (
                    f"DM 连续越权（片段: {violation[:50]}），已强制输出"
                )

        decision = self._extract_decision(content)
        if decision:
            session.open_decision = decision

        # 更新本轮字符计数
        session.turn_char_count += len(content)

        # 更新情感温度（根据场景压力微调 current）
        prev = session.emotional_temperature["current"]
        target = session.scene_pressure  # 0–10 与压力同步
        drift = round((target - prev) * 0.3, 2)
        session.emotional_temperature = {
            "base": session.emotional_temperature.get("base", "neutral"),
            "current": round(prev + drift, 2),
            "drift": drift,
        }

        turn = TurnRecord(
            turn_id=session.turn,
            who="dm",
            content=content,
            scene_pressure=session.scene_pressure,
            density=session.density,
            phase=session.phase,
            decision=decision,
            metadata=metadata,
        )
        session.history.append(turn)
        session.turn += 1

        return turn

    # ---------------------------------------------------------------- #
    # 压力与密度                                                           #
    # ---------------------------------------------------------------- #

    def _update_pressure(self, session: InteractiveSession, user_action: str) -> None:
        """根据玩家行动关键词微调 scene_pressure。"""
        HIGH_PRESSURE_WORDS = {"攻击", "冲", "杀", "逃", "危", "死", "爆", "击", "刺", "砍"}
        LOW_PRESSURE_WORDS = {"休息", "等待", "观察", "撤", "回", "营地"}

        has_high = any(w in user_action for w in HIGH_PRESSURE_WORDS)
        has_low = any(w in user_action for w in LOW_PRESSURE_WORDS)

        if has_high and not has_low:
            session.scene_pressure = min(10.0, session.scene_pressure + 1.0)
        elif has_low and not has_high:
            session.scene_pressure = max(0.0, session.scene_pressure - 1.0)

        # 自动切换密度
        if session.config.density_override is None:
            if session.scene_pressure >= 8:
                session.density = "dense"
            elif session.scene_pressure >= 4:
                session.density = "normal"
            else:
                session.density = "sparse"

    # ---------------------------------------------------------------- #
    # Prompt 构建                                                         #
    # ---------------------------------------------------------------- #

    def _build_system_prompt(
        self, session: InteractiveSession, bangui_mode: str | None
    ) -> str:
        """
        五层分层 Prompt 结构（Phase 3.5）：
          第1层：世界层 — 世界规则 + 禁忌 + 势力格局
          第2层：场景层 — 当前地点/压力/最近事件/可交互对象
          第3层：角色层 — 出场角色 persona + drive + key relationships + runtime
          第4层：控制层 — 控制权模式 + AI 接管范围 + DM 叙事密度
          第5层：安全/收束层 — 死锁检测/代理隔离/节奏纠偏/SL 建议时机
        """
        cfg = self._load_trpg_cfg()
        anti_proxy = cfg.get("anti_proxy_rule", "DM 绝对禁止替玩家做决策。")
        trunc_rule = cfg.get("truncation_priority", "到达决策节点立即截断输出。")
        density_cfg = cfg.get("decision_density", {}).get(session.density, {})
        density_desc = density_cfg.get("description", f"片段长度: {session.density}")
        length_limit = _DENSITY_LIMITS[session.density]

        # ── 第1层：世界层 ────────────────────────────────────────────────
        world_rules_text = "（无世界规则）"
        factions_text = "（无势力信息）"
        world_events_text = "（无近期事件）"
        if session.world_summary:
            world_rules_text = session.world_summary[:400] if len(session.world_summary) > 400 else session.world_summary

        layer1 = [
            "## 【第1层：世界层】",
            f"世界背景摘要：{world_rules_text}",
            f"关键势力：{factions_text}",
            f"近期世界事件：{world_events_text}",
            f"关键禁忌：任何违反 rules_of_world 的行动须先经裁定层过滤，不得直接执行。",
        ]

        # ── 第2层：场景层 ────────────────────────────────────────────────
        recent_3_turns = [
            t.content[:60] for t in session.history[-6:] if t.who == "dm"
        ][-3:]
        recent_summary = "；".join(recent_3_turns) or "（会话刚开始，暂无事件摘要）"

        layer2 = [
            "## 【第2层：场景层】",
            f"当前场景压力：{session.scene_pressure:.1f}/10  密度模式：{session.density}",
            f"最近3轮DM事件摘要：{recent_summary}",
            f"可交互对象：（由世界状态注入，当前默认开放）",
        ]

        # ── 第3层：角色层 ────────────────────────────────────────────────
        agenda_text = "（无 Agenda 推演数据）"
        if session.last_agenda:
            agenda_lines = []
            for item in session.last_agenda[:3]:
                name = item.get("character_name", "?")
                agenda = item.get("agenda_text", "")
                if name and agenda:
                    agenda_lines.append(f"  - {name}：{agenda[:60]}")
            if agenda_lines:
                agenda_text = "\n".join(agenda_lines)

        layer3 = [
            "## 【第3层：角色层】",
            f"主角名称：{session.character_name}",
            f"非玩家角色本轮 Agenda：\n{agenda_text}",
            "角色行为约束：角色不得做出与 behavior_constraints 矛盾的行为。",
        ]

        # ── 第4层：控制层 ────────────────────────────────────────────────
        mode_hint = session.mode_config.prompt_hint if hasattr(session, 'mode_config') else ""
        ai_chars = getattr(session.mode_config, 'ai_controlled_characters', []) if hasattr(session, 'mode_config') else []
        proxy_allowed = getattr(session.mode_config, 'allow_protagonist_proxy', False) if hasattr(session, 'mode_config') else False

        layer4 = [
            "## 【第4层：控制层】",
            f"当前控制模式：{session.control_mode.value if hasattr(session, 'control_mode') else 'user_driven'}",
            mode_hint,
            f"AI 接管角色：{', '.join(ai_chars) if ai_chars else '无（全部由用户控制）'}",
            f"允许AI代主角补全动作：{'是' if proxy_allowed else '否'}",
            f"DM叙事密度：{session.density}（每片段上限 {length_limit} 字）",
            density_desc,
            "",
            "## 决策选项格式",
            "[选项 A]：{行动描述}",
            "[选项 B]：{行动描述}",
        ]

        # ── 第5层：安全/收束层 ───────────────────────────────────────────
        layer5 = [
            "## 【第5层：安全/收束层】",
            anti_proxy,
            trunc_rule,
            "死锁检测：若玩家连续3次输入重复或无效，系统将自动注入解套事件，DM 协助推进。",
            "失控保护：若角色行动与 non_negotiable 底线冲突，DM 须延迟或提示后果，不得直接替玩家解决。",
            "节奏纠偏：连续3轮 scene_pressure >= 8 时，触发 PACING_ALERT；需在后续叙事中主动下压。",
            "SL 建议时机：角色面临死亡/极端后果时，DM 可在叙事末尾加注 [📎存档建议]。",
        ]

        # ── 帮回附加层（可选） ───────────────────────────────────────────
        bangui_parts: list[str] = []
        if bangui_mode:
            bcfg = self._load_bangui_cfg()
            for s in bcfg.get("suggestions", []):
                if s.get("trigger") == bangui_mode:
                    bangui_parts = [
                        f"## 帮回模式：{bangui_mode}",
                        s.get("description", ""),
                        f"逻辑：{s.get('logic', '')}",
                    ]
                    break

        all_parts = (
            [f"你是一位专业的 TRPG 地下城主（DM），正在主持一场中文网文风格的桌游推演。", ""]
            + layer1 + [""]
            + layer2 + [""]
            + layer3 + [""]
            + layer4 + [""]
            + layer5
            + ([""] + bangui_parts if bangui_parts else [])
        )
        return "\n".join(all_parts)

    def _build_history_context(
        self, session: InteractiveSession
    ) -> list[dict[str, str]]:
        """取最近 max_history_turns 条记录构建对话历史。"""
        window = session.history[-(session.config.max_history_turns):]
        messages = []
        for t in window:
            role = "assistant" if t.who == "dm" else "user"
            messages.append({"role": role, "content": t.content})
        return messages

    # ---------------------------------------------------------------- #
    # 决策点提取（多级降级链）                                             #
    # ---------------------------------------------------------------- #

    def _extract_decision(self, content: str) -> DecisionPoint | None:
        """
        从 DM 输出中多级提取决策点。
        Level 1: [选项 X]：标准格式
        Level 2: [A]：/ A. / A：等变体格式
        Level 3: 语义兜底（文本以选择语气结尾）
        """
        # Level 1: [选项 X]：格式（标准格式）
        options_l1 = re.findall(r"\[选项\s*[A-Za-z\d]\]：(.+)", content)
        if options_l1:
            return DecisionPoint(
                decision_type="action",
                options=[o.strip() for o in options_l1],
                truncated_at=content.rsplit("。", 2)[-2][:40] if "。" in content else "",
            )

        # Level 2: [A]：变体 / A. 变体 / A：变体
        options_l2 = re.findall(
            r"(?:^\s*\[[A-Da-d]\]：|^\s*[A-Da-d][.．、]|^\s*[A-Da-d]：)(.+)",
            content,
            re.MULTILINE,
        )
        if options_l2:
            opts = [o.strip() for o in options_l2 if o.strip()]
            if opts:
                return DecisionPoint(
                    decision_type="action",
                    options=opts,
                    truncated_at="",
                )

        # Level 3: 语义兜底 — 文本暗示有行动选择但未格式化
        _CHOICE_MARKERS = ["你会怎么做", "你的选择", "你将如何", "怎么办", "如何应对"]
        if any(m in content for m in _CHOICE_MARKERS):
            return DecisionPoint(
                decision_type="action",
                options=[],
                is_free_action=True,
                truncated_at="",
            )

        return None

    # ---------------------------------------------------------------- #
    # 截断与代理隔离工具                                                   #
    # ---------------------------------------------------------------- #

    def _apply_truncation(self, content: str, density: DecisionDensity) -> str:
        """
        决策驱动截断：
        - 若检测到 [选项 X] 标记，截断叙事至标记之前，选项块保留
        - 叙事部分超过密度限制时追加省略标记 …
        """
        limit = _DENSITY_LIMITS[density]
        option_match = re.search(r'\[选项\s*[A-Za-z\d]', content)
        if option_match:
            narrative = content[:option_match.start()]
            options_block = content[option_match.start():]
            if len(narrative) > limit:
                narrative = narrative[:limit] + "…\n"
            return narrative + options_block
        # 无决策标记：仅做长度截断
        if len(content) > limit:
            return content[:limit] + "…"
        return content

    def _detect_agency_violation(self, content: str) -> str | None:
        """检测 DM 是否越权替玩家做决策。返回违规片段或 None。"""
        for pattern in _PROXY_PATTERNS:
            m = re.search(pattern, content)
            if m:
                start = max(0, m.start() - 5)
                return content[start:m.end() + 15]
        return None

    def _bangui_llm_params(self, bangui_id: str | None) -> dict[str, Any]:
        """根据帮回类型返回 LLM 参数覆盖字典（temperature、max_tokens_multiplier）。"""
        if not bangui_id:
            return {}
        if "主动" in bangui_id:
            return {"temperature": 0.75, "max_tokens_multiplier": 3.0}
        if "被动" in bangui_id:
            return {"temperature": 0.70, "max_tokens_multiplier": 3.0}
        if "黑暗" in bangui_id:
            return {"temperature": 0.90, "max_tokens_multiplier": 3.0}
        if "推进" in bangui_id:
            return {"temperature": 0.65, "max_tokens_multiplier": 2.0}
        return {}

    def _check_pacing_alert(self, session: InteractiveSession) -> bool:
        """
        检测是否触发节奏警报。
        条件1：回合数 >= context_window * 0.9
        条件2：连续 3 轮 DM 叙事 scene_pressure >= 8
        """
        near_limit = session.turn >= session.config.max_history_turns * 0.9
        recent_dm = [t for t in session.history if t.who == "dm"]
        sustained_pressure = (
            len(recent_dm) >= 3
            and all(t.scene_pressure >= 8.0 for t in recent_dm[-3:])
        )
        return near_limit or sustained_pressure

    # ---------------------------------------------------------------- #
    # 帮回工具                                                            #
    # ---------------------------------------------------------------- #

    def _normalize_bangui(self, command: str) -> str:
        """标准化帮回指令名称。"""
        command = command.strip().lstrip("/")
        for bid in _BANGUI_IDS:
            if bid in command:
                return bid
        return command

    def _bangui_hint(self, bangui_id: str) -> str:
        bcfg = self._load_bangui_cfg()
        for s in bcfg.get("suggestions", []):
            if s.get("trigger") == bangui_id:
                return f"[帮回指令: {bangui_id}] 逻辑: {s.get('logic', '')}"
        return f"[帮回指令: {bangui_id}]"

    # ---------------------------------------------------------------- #
    # 配置懒加载                                                           #
    # ---------------------------------------------------------------- #

    def _load_trpg_cfg(self) -> dict[str, Any]:
        if self._trpg_cfg is None:
            try:
                self._trpg_cfg = load_yaml("trpg_immersion")
            except FileNotFoundError:
                self._trpg_cfg = {}
        return self._trpg_cfg

    def _load_bangui_cfg(self) -> dict[str, Any]:
        if self._bangui_cfg is None:
            try:
                self._bangui_cfg = load_yaml("bangui_modes")
            except FileNotFoundError:
                self._bangui_cfg = {}
        return self._bangui_cfg
