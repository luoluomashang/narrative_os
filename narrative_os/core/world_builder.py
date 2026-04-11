"""
core/world_builder.py — Phase 0: World Builder 冷启动模块

职责：将"一句话脑洞"引导式转化为结构化 JSON 输出：
  - 初始 PlotGraph（第一卷大纲节点）
  - CharacterState[]（主要人物初始面板）
  - WorldState（世界观/势力/力量体系）

设计原则：
  1. 先问后写：每步都先访谈用户需求，再生成结构
  2. 分步确认：每步完成后必须等待用户明确"确认"
  3. 最小可写门槛：当前卷大纲 + 角色面板完整即可
  4. 复用 planning 模块的 Step 1-6 方法论
  5. AI 对话式世界构建：每步调用 LLM 进行反馈 + 多轮讨论
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class BuilderStep(str, Enum):
    """World Builder 引导步骤（对应 planning 模块 Step 1-6）。"""
    ONE_SENTENCE = "one_sentence"       # Step 1: ≤25词 核心句
    ONE_PARAGRAPH = "one_paragraph"     # Step 2: 当前卷落点 + 全书方向
    WORLD_POWER = "world_power"         # Step 3: 世界观/力量体系（条件触发）
    ONE_PAGE = "one_page"               # Step 4: 第一卷核心目标/反派/脉络
    CHARACTER_ARCS = "character_arcs"   # Step 5（可选）: 人物弧光
    FOUR_PAGES = "four_pages"           # Step 6（可选）: 四页详尽大纲
    DONE = "done"


@dataclass
class WorldBuilderState:
    """World Builder 的中间状态，逐步填充。"""
    step: BuilderStep = BuilderStep.ONE_SENTENCE
    one_sentence: str = ""
    one_paragraph: str = ""
    genre_tags: list[str] = field(default_factory=list)
    needs_world_power: bool = False
    world_power_system: dict[str, Any] = field(default_factory=dict)
    one_page_outline: dict[str, Any] = field(default_factory=dict)
    character_arcs: list[dict[str, Any]] = field(default_factory=list)
    four_pages_outline: dict[str, Any] = field(default_factory=dict)
    confirmed: bool = False

    # AI 对话历史（每步独立存储）
    conversation_history: list[dict[str, str]] = field(default_factory=list)
    # [{"role": "user"|"assistant", "content": "..."}]

    # 冷启动产出（Phase 1 数据结构的初始化seed）
    initial_plot_nodes: list[dict[str, Any]] = field(default_factory=list)
    initial_characters: list[dict[str, Any]] = field(default_factory=list)
    initial_world: dict[str, Any] = field(default_factory=dict)
    # Phase 6 Stage 1: WorldSandboxData 初始种子（供沙盘精修页导入）
    initial_world_sandbox: Any = None


@dataclass
class StepResult:
    """单步执行结果。"""
    step: BuilderStep
    prompt_to_user: str      # 展示给用户的问题/草稿
    draft: dict[str, Any]    # 结构化草稿（供用户审阅/修改）
    ai_feedback: str = ""    # AI 反馈文本（非流式时为完整内容）
    suggestions: list[str] = field(default_factory=list)  # AI 建议列表
    requires_confirmation: bool = True
    skippable: bool = False  # True 时用户可直接回车跳过


class WorldBuilder:
    """
    World Builder 引导器。
    
    使用方式（CLI/API 层调用）：
        builder = WorldBuilder()
        result = builder.start()          # 返回第一个 StepResult
        builder.confirm(user_input)       # 用户确认/修改后推进
        result = builder.next_step()      # 返回下一步 StepResult
    """

    # 触发世界观/力量体系步骤的关键词（来自 planning 模块条件触发逻辑）
    _WORLD_POWER_TRIGGERS = frozenset([
        "异能", "修炼", "系统", "科幻", "魔法", "修真", "斗气", "灵气",
        "超能", "功法", "丹药", "法术", "机甲", "末世", "穿越", "异界",
    ])

    # 类型感知种子模板：当 needs_world_power=True 且用户未自定义力量体系时预填
    _GENRE_POWER_TEMPLATES: dict[str, dict[str, Any]] = {
        "修真": {
            "system_name": "修炼境界",
            "tiers": ["练气", "筑基", "金丹", "元婴", "化神", "合体", "大乘"],
        },
        "系统": {
            "system_name": "系统面板",
            "tiers": ["F级", "E级", "D级", "C级", "B级", "A级", "S级", "SS级"],
        },
        "魔法": {
            "system_name": "魔法体系",
            "tiers": ["学徒", "初阶法师", "法师", "大法师", "法圣", "法神"],
        },
        "异能": {
            "system_name": "异能等级",
            "tiers": ["一阶", "二阶", "三阶", "四阶", "五阶", "超凡"],
        },
        "斗气": {
            "system_name": "斗气境界",
            "tiers": ["斗者", "斗师", "大斗师", "斗灵", "斗王", "斗皇", "斗宗", "斗尊", "斗圣", "斗帝"],
        },
    }

    def __init__(self) -> None:
        self.state = WorldBuilderState()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def start(self) -> StepResult:
        """开始引导，返回第一步的提示。"""
        return StepResult(
            step=BuilderStep.ONE_SENTENCE,
            prompt_to_user=(
                "请用一句话描述你的故事（≤25词）。\n"
                "格式建议：[主角] 在 [世界/困境] 中凭借 [金手指/能力]，\n"
                "为了 [目标] 与 [反派/障碍] 抗争。\n\n"
                "例：落魄少年林枫在修炼者大陆中凭借上古斗技，\n"
                "誓要打倒夺走家族一切的权贵，重铸家族荣光。"
            ),
            draft={},
        )

    def submit_step(self, user_input: str) -> StepResult:
        """
        接收用户对当前步骤的输入，更新状态，返回下一步 StepResult。
        实际生成逻辑在 Phase 2+ 接入 LLM Router 后替换；
        当前返回结构化脚手架供测试。
        """
        step = self.state.step

        if step == BuilderStep.ONE_SENTENCE:
            self.state.one_sentence = user_input.strip()
            self.state.needs_world_power = self._contains_world_power_trigger(user_input)
            # 类型感知：匹配类型标签并预填力量体系模板
            matched_genre = next(
                (g for g in self._GENRE_POWER_TEMPLATES if g in user_input), None
            )
            if (
                self.state.needs_world_power
                and matched_genre
                and not self.state.world_power_system
            ):
                self.state.world_power_system = self._GENRE_POWER_TEMPLATES[matched_genre]
                if matched_genre not in self.state.genre_tags:
                    self.state.genre_tags.append(matched_genre)
            self.state.step = BuilderStep.ONE_PARAGRAPH
            return StepResult(
                step=BuilderStep.ONE_PARAGRAPH,
                prompt_to_user=(
                    "很好！\n请描述 第一卷的落点（结束时主角的核心变化是什么），"
                    "以及全书大方向（最终结局是什么感觉，一两句即可）。"
                ),
                draft={"one_sentence": self.state.one_sentence},
            )

        elif step == BuilderStep.ONE_PARAGRAPH:
            self.state.one_paragraph = user_input.strip()
            # 世界观触发不应仅依赖第一步：若第二步出现体系关键词，也进入 WORLD_POWER。
            self.state.needs_world_power = (
                self.state.needs_world_power
                or self._contains_world_power_trigger(user_input)
            )
            next_step = (
                BuilderStep.WORLD_POWER
                if self.state.needs_world_power
                else BuilderStep.ONE_PAGE
            )
            self.state.step = next_step
            if next_step == BuilderStep.WORLD_POWER:
                return StepResult(
                    step=BuilderStep.WORLD_POWER,
                    prompt_to_user=(
                        "检测到故事包含特殊能力/修炼体系。\n"
                        "请描述力量等级体系（如：炼气→筑基→金丹...）"
                        "及世界的基本规则（法宝、丹药、宗门等）。"
                    ),
                    draft={
                        "one_sentence": self.state.one_sentence,
                        "one_paragraph": self.state.one_paragraph,
                    },
                )
            else:
                return self._one_page_prompt()

        elif step == BuilderStep.WORLD_POWER:
            self.state.world_power_system = {"description": user_input.strip()}
            self.state.step = BuilderStep.ONE_PAGE
            return self._one_page_prompt()

        elif step == BuilderStep.ONE_PAGE:
            self.state.one_page_outline = self._parse_one_page(user_input)
            self.state.step = BuilderStep.CHARACTER_ARCS
            char_names = [
                c["name"] for c in self.state.one_page_outline.get("characters", [])
            ] or ["主角"]
            return StepResult(
                step=BuilderStep.CHARACTER_ARCS,
                prompt_to_user=(
                    "请描述以下角色的弧线（可选，直接回车跳过）：\n"
                    + "\n".join(
                        f"  {name}：初始状态 → 转折点 → 最终状态"
                        for name in char_names
                    )
                ),
                draft=self.state.one_page_outline,
                skippable=True,
            )

        elif step == BuilderStep.CHARACTER_ARCS:
            if user_input.strip():
                self.state.character_arcs = self._parse_character_arcs(
                    user_input, self.state.one_page_outline.get("characters", [])
                )
            self.state.step = BuilderStep.FOUR_PAGES
            return StepResult(
                step=BuilderStep.FOUR_PAGES,
                prompt_to_user=(
                    "请输入四页详细大纲（按卷/章组织，可分段输入），或直接回车跳过。\n"
                    "提示：四页大纲有助于生成更连贯的长篇章节规划。"
                ),
                draft={"character_arcs": self.state.character_arcs},
                skippable=True,
            )

        elif step == BuilderStep.FOUR_PAGES:
            if user_input.strip():
                self.state.four_pages_outline = {"raw_text": user_input.strip()}
            self.state.step = BuilderStep.DONE
            result = self._finalize()
            return StepResult(
                step=BuilderStep.DONE,
                prompt_to_user=(
                    "✅ 冷启动完成！\n"
                    "已生成：初始 PlotGraph + CharacterState[] + WorldState\n"
                    "请确认后进入 Phase 1 数据结构初始化。"
                ),
                draft=result,
                requires_confirmation=True,
            )

        else:
            return StepResult(
                step=BuilderStep.DONE,
                prompt_to_user="World Builder 已完成。",
                draft=self._finalize(),
                requires_confirmation=False,
            )

    def get_seed_data(self) -> dict[str, Any]:
        """
        返回可直接传入 Phase 1 数据结构构造函数的种子数据。
        在 state.step == DONE 时调用。
        """
        return {
            "plot_nodes": self.state.initial_plot_nodes,
            "characters": self.state.initial_characters,
            "world": self.state.initial_world,
            "genre_tags": self.state.genre_tags,
            "one_sentence": self.state.one_sentence,
            "one_paragraph": self.state.one_paragraph,
        }

    # ------------------------------------------------------------------ #
    # AI 对话式世界构建                                                      #
    # ------------------------------------------------------------------ #

    # 每步的 AI 系统提示词（用于引导 LLM 扮演小说策划专家）
    _STEP_SYSTEM_PROMPTS: dict[BuilderStep, str] = {
        BuilderStep.ONE_SENTENCE: (
            "你是一位经验丰富的网文策划编辑。用户正在构思一部新小说，"
            "刚刚输入了一句话核心概念。请你：\n"
            "1. 分析这个概念的优势和潜力\n"
            "2. 指出可能的问题（如市场同质化、逻辑漏洞）\n"
            "3. 提出 2-3 个具体的改进或延伸建议\n"
            "回复简洁有力，不超过 300 字。"
        ),
        BuilderStep.ONE_PARAGRAPH: (
            "你是一位经验丰富的网文策划编辑。用户正在将一句话概念展开为一段话描述，"
            "包括第一卷落点和全书方向。请你：\n"
            "1. 评估卷末落点是否足够有冲击力\n"
            "2. 检查前后逻辑一致性\n"
            "3. 建议如何增强读者期待感\n"
            "回复简洁有力，不超过 300 字。"
        ),
        BuilderStep.WORLD_POWER: (
            "你是一位专精世界观设计的网文策划。用户正在构建力量体系/世界观。请你：\n"
            "1. 检查体系的内在逻辑一致性\n"
            "2. 评估等级划分是否清晰、有辨识度\n"
            "3. 建议如何让力量体系与故事主线更紧密结合\n"
            "4. 指出可能的设定冲突或漏洞\n"
            "回复简洁有力，不超过 400 字。"
        ),
        BuilderStep.ONE_PAGE: (
            "你是一位经验丰富的网文策划编辑。用户正在撰写第一卷大纲。请你：\n"
            "1. 分析情节节奏是否合理（起承转合）\n"
            "2. 检查角色动机是否充分\n"
            "3. 评估冲突是否足够引人入胜\n"
            "4. 建议补充或调整的情节元素\n"
            "回复简洁有力，不超过 400 字。"
        ),
        BuilderStep.CHARACTER_ARCS: (
            "你是一位专精角色塑造的网文策划。用户正在设计角色弧光。请你：\n"
            "1. 分析角色成长轨迹是否合理\n"
            "2. 检查角色间关系是否有足够张力\n"
            "3. 建议如何让角色更立体、更有记忆点\n"
            "回复简洁有力，不超过 300 字。"
        ),
        BuilderStep.FOUR_PAGES: (
            "你是一位经验丰富的网文策划编辑。用户正在撰写四页详细大纲。请你：\n"
            "1. 检查章节间衔接是否流畅\n"
            "2. 评估节奏把控（是否有拖沓或跳跃）\n"
            "3. 验证伏笔和呼应是否到位\n"
            "4. 给出整体评价和改进建议\n"
            "回复简洁有力，不超过 500 字。"
        ),
    }

    def _build_ai_context(self) -> str:
        """根据已积累的 state 构建上下文摘要，传给 LLM 作为背景信息。"""
        parts: list[str] = []
        if self.state.one_sentence:
            parts.append(f"【核心概念】{self.state.one_sentence}")
        if self.state.one_paragraph:
            parts.append(f"【展开方向】{self.state.one_paragraph}")
        if self.state.world_power_system:
            desc = self.state.world_power_system.get("description", "")
            name = self.state.world_power_system.get("system_name", "")
            if desc or name:
                parts.append(f"【力量体系】{name}: {desc}" if name else f"【力量体系】{desc}")
        if self.state.one_page_outline.get("raw_text"):
            parts.append(f"【一页大纲】{self.state.one_page_outline['raw_text'][:500]}")
        if self.state.character_arcs:
            arcs_str = "; ".join(
                f"{a['name']}:{'→'.join(a.get('stages', []))}"
                for a in self.state.character_arcs[:5]
            )
            parts.append(f"【角色弧光】{arcs_str}")
        return "\n".join(parts)

    def _contains_world_power_trigger(self, text: str) -> bool:
        """判断输入是否命中世界观/力量体系触发词。"""
        content = (text or "").strip()
        if not content:
            return False
        return any(kw in content for kw in self._WORLD_POWER_TRIGGERS)

    async def discuss(self, user_input: str) -> AsyncIterator[str]:
        """
        AI 对话式讨论（不推进步骤）。流式 yield 文本块。
        用于用户在当前步骤内与 AI 多轮讨论。
        """
        from narrative_os.execution.llm_router import (
            LLMRequest,
            get_default_routing_strategy,
            router,
        )

        step = self.state.step
        system_prompt = self._STEP_SYSTEM_PROMPTS.get(step, "你是一位经验丰富的小说策划编辑。")
        context = self._build_ai_context()
        if context:
            system_prompt += f"\n\n以下是用户已有的创作信息：\n{context}"

        # 记录用户消息
        self.state.conversation_history.append({"role": "user", "content": user_input})

        # 构建 messages：system + 最近 10 轮对话
        messages = self.state.conversation_history[-10:]

        req = LLMRequest(
            task_type="world_building",
            messages=messages,
            system_prompt=system_prompt,
            strategy=get_default_routing_strategy(),
            max_tokens=1024,
            temperature=0.7,
            skill_name="world_builder_discuss",
        )

        # 流式调用
        full_response = ""
        try:
            async for chunk in router.call_stream(req):
                full_response += chunk
                yield chunk
        except Exception:
            # 流式不可用时，退化为非流式
            resp = await router.call(req)
            full_response = resp.content
            yield full_response

        # 记录 AI 回复
        self.state.conversation_history.append({"role": "assistant", "content": full_response})

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    def _one_page_prompt(self) -> StepResult:
        return StepResult(
            step=BuilderStep.ONE_PAGE,
            prompt_to_user=(
                "请描述第一卷大纲（一页篇幅）：\n"
                "1. 核心目标（主角本卷要完成什么）\n"
                "2. 主要反派/障碍\n"
                "3. 关键情节脉络（3-5个核心事件）\n"
                "4. 主要角色（姓名、阵营、初始目标）"
            ),
            draft={
                "one_sentence": self.state.one_sentence,
                "one_paragraph": self.state.one_paragraph,
                "world_power": self.state.world_power_system,
            },
        )

    def _parse_one_page(self, raw: str) -> dict[str, Any]:
        """
        将用户的一页大纲文本解析为结构化字典。
        提取：角色 / 世界要素 / 情节节点。
        """
        text = raw.strip()
        if not text:
            return {
                "raw_text": "",
                "characters": [],
                "world": {"factions": [], "key_locations": [], "rules": []},
                "plot_nodes": [],
                "volume": 1,
                "status": "draft",
            }

        # ── 角色提取 ─────────────────────────────────────────────────
        # 支持格式：「主角：王晨」「主角/反派/配角：姓名」「角色：姓名（职能）」
        char_patterns = [
            r'(?:主角|反派|配角|角色|男主|女主|男配|女配|villain|hero)[：:] *([^\n，,（(]+)',
        ]
        characters: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        for pattern in char_patterns:
            for m in re.finditer(pattern, text, re.IGNORECASE):
                raw_name = m.group(1).strip().split()[0]  # 取第一个词作为姓名
                role_match = re.search(
                    r'(主角|反派|配角|男主|女主|男配|女配|hero|villain)', m.group(0)
                )
                role = role_match.group(1) if role_match else "配角"
                if raw_name and raw_name not in seen_names:
                    seen_names.add(raw_name)
                    characters.append({"name": raw_name, "role": role, "initial_state": ""})

        # ── 世界要素提取 ─────────────────────────────────────────────
        world: dict[str, list[str]] = {"factions": [], "key_locations": [], "rules": []}
        for m in re.finditer(r'势力[：:]([^\n。！]+)', text):
            world["factions"].append(m.group(1).strip())
        for m in re.finditer(r'(?:地点|场景|地方)[：:]([^\n。！]+)', text):
            world["key_locations"].append(m.group(1).strip())
        for m in re.finditer(r'规则[：:]([^\n。！]+)', text):
            world["rules"].append(m.group(1).strip())

        # ── 情节节点生成 (起/承/转/合) ──────────────────────────────
        # 按段落或句号拆分，取 3-5 段生成节点
        paragraphs = [p.strip() for p in re.split(r'[\n。！]', text) if p.strip()]
        pacing_map = ["rising", "rising", "climax", "falling", "resolution"]
        tension_map = [0.3, 0.5, 0.8, 0.7, 0.6]
        plot_nodes: list[dict[str, Any]] = []
        for i, para in enumerate(paragraphs[:5]):
            plot_nodes.append({
                "id": f"vol01_{i:03d}",
                "summary": para[:80],
                "tension": tension_map[i],
                "pacing_type": pacing_map[i],
                "key_beat": ["引入", "发展", "转折", "高潮", "收尾"][i],
                "status": "pending",
            })
        # 保底：至少 1 个节点
        if not plot_nodes:
            plot_nodes = [{
                "id": "vol01_000",
                "summary": text[:80],
                "tension": 0.3,
                "pacing_type": "rising",
                "key_beat": "引入",
                "status": "pending",
            }]

        return {
            "raw_text": text,
            "characters": characters,
            "world": world,
            "plot_nodes": plot_nodes,
            "volume": 1,
            "status": "draft",
        }

    def _parse_character_arcs(
        self,
        raw: str,
        existing_chars: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """
        解析角色弧光文本。
        支持格式：「姓名：初始 → 转折 → 最终」
        """
        arcs: list[dict[str, Any]] = []
        names = {c["name"] for c in existing_chars}
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            # 尝试解析「姓名：状态 → 状态 → 状态」
            m = re.match(r'([^：:]+)[：:](.+)', line)
            if m:
                name = m.group(1).strip()
                stages_raw = m.group(2)
                stages = [s.strip() for s in re.split(r'[→>]', stages_raw) if s.strip()]
                arcs.append({"name": name, "stages": stages})
            elif names:
                # 无名称前缀，附加到第一个角色
                char_name = next(iter(names))
                stages = [s.strip() for s in re.split(r'[→>]', line) if s.strip()]
                if stages:
                    arcs.append({"name": char_name, "stages": stages})
        return arcs

    def _finalize(self) -> dict[str, Any]:
        """
        生成种子数据并存入 state。

        变更（Phase 6 Stage 1）：
          _finalize() 现在同时生成 WorldSandboxData（初始种子），
          存储在 state.initial_world_sandbox 中，供后续沙盘精修使用。
          原有 state.initial_world 字段保留（向后兼容，已有项目不受影响）。
        """
        parsed = self.state.one_page_outline

        # ── 情节节点 ──────────────────────────────────────────────────
        raw_nodes: list[dict[str, Any]] = parsed.get("plot_nodes", [])
        if not raw_nodes:
            # 保底节点
            raw_nodes = [{
                "id": "vol01_000",
                "summary": self.state.one_sentence or "故事开始",
                "tension": 0.3,
                "pacing_type": "rising",
                "key_beat": "引入",
                "status": "pending",
            }]
        self.state.initial_plot_nodes = raw_nodes

        # ── 角色列表 ──────────────────────────────────────────────────
        raw_chars: list[dict[str, Any]] = parsed.get("characters", [])
        # 合并弧光数据
        arc_map = {a["name"]: a["stages"] for a in self.state.character_arcs}
        for c in raw_chars:
            c["arc_stages"] = arc_map.get(c["name"], [])
        self.state.initial_characters = raw_chars

        # ── 世界状态（向后兼容字段） ──────────────────────────────────
        world_from_parse = parsed.get("world", {})
        self.state.initial_world = {
            "power_system": self.state.world_power_system or {},
            "factions": world_from_parse.get("factions", []),
            "key_locations": world_from_parse.get("key_locations", []),
            "rules": world_from_parse.get("rules", []),
            "outline_raw": parsed.get("raw_text", ""),
            "four_pages_raw": self.state.four_pages_outline.get("raw_text", ""),
        }

        # ── WorldSandboxData（初始种子，Phase 6 Stage 1 新增） ────────
        # 从 one_page_outline 提取的文本数据构建初始沙盘种子，供沙盘精修页使用
        self.state.initial_world_sandbox = self._build_initial_sandbox()

        seed = self.get_seed_data()
        # 在 seed 中附带沙盘数据（用于 API 层直接保存到 DB）
        if self.state.initial_world_sandbox is not None:
            seed["world_sandbox"] = self.state.initial_world_sandbox.model_dump()
        return seed

    def _build_initial_sandbox(self) -> "WorldSandboxData | None":
        """
        从 WorldBuilderState 的积累数据构建 WorldSandboxData 初始种子。
        这个种子会被导入沙盘精修页，由用户进一步完善。
        """
        try:
            from narrative_os.core.world_sandbox import (
                WorldSandboxData,
                Faction,
                PowerSystem as SbPowerSystem,
                PowerLevel as SbPowerLevel,
                FactionScope,
            )

            world_from_parse = self.state.one_page_outline.get("world", {})

            # 初始势力（从一页大纲提取）
            factions: list[Faction] = []
            for raw_faction_name in world_from_parse.get("factions", []):
                if isinstance(raw_faction_name, str) and raw_faction_name.strip():
                    factions.append(
                        Faction(name=raw_faction_name.strip(), scope=FactionScope.INTERNAL)
                    )

            # 初始力量体系（从 world_power_system 提取）
            power_systems: list[SbPowerSystem] = []
            wp = self.state.world_power_system
            if wp:
                ps_name = wp.get("system_name", "力量体系")
                tiers = wp.get("tiers", [])
                desc_raw = wp.get("description", "")
                levels = [
                    SbPowerLevel(name=tier, description="") for tier in tiers
                ] if tiers else []
                if not levels and desc_raw:
                    # 从描述文字中提取境界（如 "炼气→筑基→金丹"）
                    import re as _re
                    parts = [p.strip() for p in _re.split(r'[→>、，,]', desc_raw) if p.strip()]
                    levels = [SbPowerLevel(name=p, description="") for p in parts[:15]]
                if levels or ps_name:
                    power_systems.append(
                        SbPowerSystem(name=ps_name or "力量体系", levels=levels)
                    )

            # 世界规则
            world_rules: list[str] = list(world_from_parse.get("rules", []))

            # 世界描述
            world_desc = self.state.one_paragraph or self.state.one_sentence or ""

            return WorldSandboxData(
                world_name=self.state.one_sentence[:50] if self.state.one_sentence else "",
                world_description=world_desc,
                factions=factions,
                power_systems=power_systems,
                world_rules=world_rules,
            )
        except Exception:
            return None
