"""Shared prompt contracts, context blocks, and parsers for LLM-facing flows."""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Literal


def plain_text_contract(*rules: str) -> str:
    """Render a numbered plain-text output contract."""
    filtered = [rule.strip() for rule in rules if rule and rule.strip()]
    if not filtered:
        return ""

    lines = ["## 输出要求"]
    for index, rule in enumerate(filtered, start=1):
        lines.append(f"{index}. {rule}")
    return "\n".join(lines)


def json_object_contract(schema: str) -> str:
    return "\n".join(
        [
            "请以 JSON 对象格式返回，结构如下：",
            schema,
            "只返回 JSON 对象，不要其他文字。",
        ]
    )


def json_array_contract(item_schema: str, *, empty_response: str | None = None) -> str:
    lines = ["请以 JSON 数组格式返回，每项结构如下：", item_schema]
    if empty_response:
        lines.append(empty_response)
    lines.append("只返回 JSON 数组，不要其他文字。")
    return "\n".join(lines)


def strip_markdown_fence(text: str) -> str:
    """Remove a surrounding markdown code fence if present."""
    candidate = text.strip()
    if not candidate.startswith("```"):
        return candidate

    candidate = re.sub(r"^```(?:json)?\s*", "", candidate, count=1)
    candidate = re.sub(r"\s*```$", "", candidate, count=1)
    return candidate.strip()


def parse_json_response(
    text: str,
    *,
    expect: Literal["object", "array", "either"] = "either",
) -> dict[str, Any] | list[Any] | None:
    """Parse JSON content from raw model output, including fenced payloads."""
    candidate = strip_markdown_fence(text)
    attempts = [candidate]

    if expect in {"object", "either"}:
        match = re.search(r"\{[\s\S]+\}", candidate)
        if match:
            attempts.append(match.group(0))
    if expect in {"array", "either"}:
        match = re.search(r"\[[\s\S]+\]", candidate)
        if match:
            attempts.append(match.group(0))

    seen: set[str] = set()
    for item in attempts:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            parsed = json.loads(normalized)
        except json.JSONDecodeError:
            continue

        if expect == "object" and isinstance(parsed, dict):
            return parsed
        if expect == "array" and isinstance(parsed, list):
            return parsed
        if expect == "either" and isinstance(parsed, (dict, list)):
            return parsed
    return None


def build_character_voice_block(
    *,
    name: str = "",
    personality: str = "",
    speech_style: str = "",
    catchphrases: Iterable[str] | None = None,
    under_pressure: str = "",
    dialogue_examples: Iterable[Any] | None = None,
    include_name: bool = False,
    include_personality: bool = True,
    example_title: str = "历史对话示例",
    empty_example_text: str = "（无示例）",
) -> str:
    """Render a reusable character voice context block."""
    lines: list[str] = []
    phrases = [item for item in (catchphrases or []) if item]

    if include_name and name:
        lines.append(f"角色：{name}")
    if include_personality and personality:
        lines.append(f"性格：{personality}")
    lines.append(f"语言风格：{speech_style or '自然'}")
    lines.append(f"口头禅：{'、'.join(phrases) or '无'}")
    lines.append(f"高压时的说话方式：{under_pressure or '无特殊表现'}")

    rendered_examples: list[str] = []
    for example in (dialogue_examples or []):
        if isinstance(example, dict):
            context = str(example.get("context", "")).strip()
            dialogue = str(example.get("dialogue", "")).strip()
        else:
            context = str(getattr(example, "context", "")).strip()
            dialogue = str(getattr(example, "dialogue", "")).strip()
        if dialogue:
            rendered_examples.append(f"[{context}] {dialogue}" if context else dialogue)

    lines.append(f"{example_title}：")
    lines.append("\n".join(rendered_examples) if rendered_examples else empty_example_text)
    return "\n".join(lines)


def build_world_relations_prompt(faction_descriptions: list[str]) -> str:
    return "\n\n".join(
        [
            "你是一位世界观设计助手。根据以下势力信息，建议它们之间可能存在的关系。",
            "势力列表：\n" + "\n".join(faction_descriptions),
            json_array_contract(
                '{"source_id": "势力ID", "target_id": "势力ID", "relation_type": "alliance|conflict|trade|rivalry|vassal", "reason": "关系成因"}'
            ),
        ]
    )


def build_world_expand_prompt(
    *,
    field: str,
    entity_type: str,
    entity_json: str,
    neighbors: list[str],
    world_name: str,
    world_type: str,
) -> str:
    return "\n\n".join(
        [
            f"你是一位世界观设计助手。请根据以下实体信息和其关联实体，为字段「{field}」生成丰富的内容。",
            "\n".join(
                [
                    f"实体类型：{entity_type}",
                    f"实体数据：{entity_json}",
                    f"关联实体：{', '.join(neighbors) or '无'}",
                    f"世界背景：{world_name} ({world_type})",
                ]
            ),
            plain_text_contract(
                f"只返回「{field}」字段的内容文本，不要 JSON 包装。",
                "不要解释。",
            ),
        ]
    )


def build_world_import_prompt(text: str) -> str:
    schema = (
        '{"regions": [{"name": "...", "region_type": "...", "notes": "..."}], '
        '"factions": [{"name": "...", "scope": "internal/external", "description": "..."}], '
        '"relations": [{"source_name": "...", "target_name": "...", '
        '"relation_type": "alliance/conflict/connection", "label": "..."}]}'
    )
    return "\n\n".join(
        [
            "你是一位世界观解析助手。请从下面的设定文本中提取地区、势力和它们之间的关系。",
            f"文本：\n{text}",
            json_object_contract(schema),
        ]
    )


def build_world_consistency_prompt(world_summary: str) -> str:
    return "\n\n".join(
        [
            "你是一位世界观一致性分析师。请分析以下世界设定中可能存在的逻辑冲突、不一致或不合理之处。",
            world_summary,
            json_array_contract(
                '{"severity": "warning/error", "node_ref": "涉及的实体名", "message": "问题描述"}',
                empty_response="如果没有发现问题，返回空数组 []。",
            ),
        ]
    )


def build_planner_system_prompt() -> str:
    schema = "\n".join(
        [
            "{",
            '  "outline": "章节大纲文本（2-4句话概括主要事件）",',
            '  "nodes": [',
            '    {"id": "ch{章号}_01", "type": "setup|conflict|climax|resolution|branch", "summary": "节点摘要（20字内）", "tension": 0.5, "characters": ["角色名"]}',
            '  ],',
            '  "edges": [',
            '    {"from": "节点id", "to": "节点id", "relation": "causal|temporal|conditional"}',
            '  ],',
            '  "dialogue_goals": ["对话目标1", "对话目标2"],',
            '  "hook": {"description": "结尾钩子描述", "type": "suspense|revelation|cliffhanger|emotional"}',
            "}",
        ]
    )
    return "\n\n".join(
        [
            "你是一位专业的中文网文策划编辑，专注于长篇网文（番茄/起点风格）的剧情结构设计。",
            "你的任务是为指定章节生成结构化剧情骨架。",
            "## 输出格式（严格遵守）\n" + json_object_contract(schema),
            "## 规则\n- 每章生成 3~6 个情节节点\n- tension 值：setup≈0.2, conflict≈0.6, climax≈0.9, resolution≈0.3\n- 最后一个节点必须对应 hook.description\n- 节点 id 格式：ch{章号}_{序号:02d}，如 ch3_01",
        ]
    )


def build_interactive_world_layer(
    *,
    world_rules_text: str,
    factions_text: str,
    world_events_text: str,
) -> list[str]:
    return [
        "## 【第1层：世界层】",
        f"世界背景摘要：{world_rules_text}",
        f"关键势力：{factions_text}",
        f"近期世界事件：{world_events_text}",
        "关键禁忌：任何违反 rules_of_world 的行动须先经裁定层过滤，不得直接执行。",
    ]


def build_interactive_scene_layer(
    *,
    scene_pressure: float,
    density: str,
    recent_summary: str,
    memory_context: str,
) -> list[str]:
    return [
        "## 【第2层：场景层】",
        f"当前场景压力：{scene_pressure:.1f}/10  密度模式：{density}",
        f"最近3轮DM事件摘要：{recent_summary}",
        f"TRPG/Canon 记忆召回：{memory_context}",
        "可交互对象：（由世界状态注入，当前默认开放）",
    ]


def build_interactive_character_layer(*, character_name: str, agenda_text: str) -> list[str]:
    return [
        "## 【第3层：角色层】",
        f"主角名称：{character_name}",
        f"非玩家角色本轮 Agenda：\n{agenda_text}",
        "角色行为约束：角色不得做出与 behavior_constraints 矛盾的行为。",
    ]


def build_interactive_control_layer(
    *,
    control_mode: str,
    mode_hint: str,
    ai_controlled_characters: list[str],
    proxy_allowed: bool,
    density: str,
    length_limit: int,
    density_desc: str,
) -> list[str]:
    return [
        "## 【第4层：控制层】",
        f"当前控制模式：{control_mode}",
        mode_hint,
        f"AI 接管角色：{', '.join(ai_controlled_characters) if ai_controlled_characters else '无（全部由用户控制）'}",
        f"允许AI代主角补全动作：{'是' if proxy_allowed else '否'}",
        f"DM叙事密度：{density}（每片段上限 {length_limit} 字）",
        density_desc,
        "",
        "## 决策选项格式",
        "[选项 A]：{行动描述}",
        "[选项 B]：{行动描述}",
    ]


def build_interactive_safety_layer(*, anti_proxy: str, trunc_rule: str) -> list[str]:
    return [
        "## 【第5层：安全/收束层】",
        anti_proxy,
        trunc_rule,
        "死锁检测：若玩家连续3次输入重复或无效，系统将自动注入解套事件，DM 协助推进。",
        "失控保护：若角色行动与 non_negotiable 底线冲突，DM 须延迟或提示后果，不得直接替玩家解决。",
        "节奏纠偏：连续3轮 scene_pressure >= 8 时，触发 PACING_ALERT；需在后续叙事中主动下压。",
        "SL 建议时机：角色面临死亡/极端后果时，DM 可在叙事末尾加注 [📎存档建议]。",
    ]


def assemble_interactive_system_prompt(
    *,
    intro: str,
    layers: list[list[str]],
    bangui_parts: list[str] | None = None,
) -> str:
    all_parts: list[str] = [intro, ""]
    for index, layer in enumerate(layers):
        all_parts.extend(layer)
        if index != len(layers) - 1:
            all_parts.append("")
    if bangui_parts:
        all_parts.extend(["", *bangui_parts])
    return "\n".join(all_parts)