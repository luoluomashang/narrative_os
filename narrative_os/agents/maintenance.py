"""
agents/maintenance.py — Phase 3 (补全): Maintenance Agent

职责（全局维护，无 LLM 调用）：
  - 推进角色成长弧（arc_stage）— 有一致性问题的角色跳过
  - 标记本章 PlotGraph 节点为 completed
  - 压缩短期记忆 → 中期层（write_memory layer="mid"）
  - 提取下一章钩子（draft 最后文字）
  - 写入结构化日志

输入  MaintenanceInput:
  chapter_draft    ChapterDraft
  critic_report    CriticReport | None
  planner_output   PlannerOutput | None
  characters       list[CharacterState]
  advance_arcs     bool（默认 True）

输出 MaintenanceOutput:
  chapter              int
  updated_characters   list[CharacterState]
  memory_summary       str
  next_hook            str
  completed_nodes      list[str]
  warnings             list[str]
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.planner import PlannerOutput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, CharacterState
from narrative_os.core.memory import MemoryPool, MemorySystem
from narrative_os.core.plot import NodeStatus, PlotGraph
from narrative_os.core.state import StateManager
from narrative_os.infra.database import fire_and_forget
from narrative_os.infra.logging import logger
from narrative_os.schemas.traces import Artifact, ArtifactType


# ArcStage 顺序（对应 ArcStage 常量字符串）
_ARC_ORDER: list[str] = [
    ArcStage.DEFENSIVE,
    ArcStage.CRACKING,
    ArcStage.COMPENSATING,
    ArcStage.ACCEPTING,
    ArcStage.TRANSFORMED,
]


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class MaintenanceInput(BaseModel):
    """Maintenance Agent 输入。"""
    project_id: str = "default"
    chapter_draft: ChapterDraft
    critic_report: CriticReport | None = None
    planner_output: PlannerOutput | None = None
    characters: list[CharacterState] = Field(default_factory=list)
    advance_arcs: bool = True


class MaintenanceOutput(BaseModel):
    """Maintenance Agent 输出。"""
    chapter: int
    updated_characters: list[CharacterState] = Field(default_factory=list)
    memory_summary: str = ""
    memory_anchor: str = ""
    memory_anchors: list[dict[str, Any]] = Field(default_factory=list)
    next_hook: str = ""
    completed_nodes: list[str] = Field(default_factory=list)
    activated_nodes: list[str] = Field(default_factory=list)
    plot_progress: dict[str, Any] = Field(default_factory=dict)
    world_state_delta: list[dict[str, Any]] = Field(default_factory=list)
    canon_pending_changes: list[dict[str, Any]] = Field(default_factory=list)
    changeset_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ #
# MaintenanceAgent                                                      #
# ------------------------------------------------------------------ #

class MaintenanceAgent:
    """
    维护 Agent（本地计算，无 LLM）。

    用法：
        agent = MaintenanceAgent()
        output = agent.maintain(inp, plot_graph=graph, memory=mem)
    """

    def maintain(
        self,
        inp: MaintenanceInput,
        *,
        plot_graph: PlotGraph | None = None,
        memory: MemorySystem | None = None,
        run_context: Any | None = None,
    ) -> MaintenanceOutput:
        warnings: list[str] = []
        successful_steps = 0
        state_manager = StateManager(project_id=inp.project_id, base_dir=".narrative_state")
        try:
            state_manager.load_state()
        except FileNotFoundError:
            state_manager.initialize(project_name=inp.project_id)

        # 1. 推进角色弧
        updated = self._update_arcs(
            inp.characters,
            inp.critic_report,
            inp.advance_arcs,
            warnings,
        )

        # 1.5 动机张力宣泄：若本章涉及关键冲突，降低相关角色 motivation.tension
        updated = self._release_tension(updated, inp.critic_report, warnings)

        if self._persist_characters(inp.project_id, updated, inp, warnings):
            successful_steps += 1

        # 2. 标记本章节点已完成
        completed = self._mark_completed_nodes(
            plot_graph,
            inp.chapter_draft.chapter,
            warnings,
        )
        activated = self._activate_followup_nodes(plot_graph, completed, warnings)
        if completed or activated or plot_graph is not None:
            successful_steps += 1

        # 3. 压缩短期记忆 → mid 层
        mem_summary = self._compress_memory(memory, inp.chapter_draft, warnings)
        anchor_payload = self._write_memory_anchor(memory, inp.chapter_draft, warnings)
        anchor = self._format_memory_anchor(anchor_payload)
        memory_anchors = self._build_memory_anchor_entries(mem_summary, anchor_payload)
        if mem_summary or anchor:
            successful_steps += 1

        changeset_id, canon_pending_changes = self._create_world_changeset(inp, warnings)
        if changeset_id is not None:
            successful_steps += 1

        # 4. 提取下一章钩子
        hook = self._extract_next_hook(inp.chapter_draft)
        if self._persist_hook(state_manager, inp.chapter_draft.chapter, hook, warnings):
            successful_steps += 1

        if successful_steps == 0 and inp.chapter_draft.draft_text.strip():
            raise RuntimeError("Maintenance 所有回写步骤均失败")

        logger.info(
            "maintenance_done",
            chapter=inp.chapter_draft.chapter,
            arc_advanced=len(updated),
            completed_nodes=len(completed),
            changeset_id=changeset_id,
            warnings=len(warnings),
        )

        plot_progress = self._build_plot_progress(plot_graph, completed, activated)
        world_state_delta = self._build_world_state_delta(
            original_characters=inp.characters,
            updated_characters=updated,
            canon_pending_changes=canon_pending_changes,
        )

        result = MaintenanceOutput(
            chapter=inp.chapter_draft.chapter,
            updated_characters=updated,
            memory_summary=mem_summary,
            memory_anchor=anchor,
            memory_anchors=memory_anchors,
            next_hook=hook,
            completed_nodes=completed,
            activated_nodes=activated,
            plot_progress=plot_progress,
            world_state_delta=world_state_delta,
            canon_pending_changes=canon_pending_changes,
            changeset_id=changeset_id,
            warnings=warnings,
        )
        if run_context is not None:
            fire_and_forget(
                run_context.emit_artifact(
                    Artifact(
                        artifact_type=ArtifactType.MAINTENANCE,
                        agent_name="maintenance",
                        input_summary=inp.chapter_draft.draft_text[:200],
                        output_content=result.model_dump_json(),
                        quality_scores={
                            "completed_nodes": float(len(result.completed_nodes)),
                            "warnings": float(len(result.warnings)),
                        },
                    )
                )
            )
        return result

    def _persist_characters(
        self,
        project_id: str,
        characters: list[CharacterState],
        inp: MaintenanceInput,
        warnings: list[str],
    ) -> bool:
        if not characters:
            return False

        from narrative_os.core.character_repository import get_character_repository

        repo = get_character_repository()
        updated_any = False
        key_event = self._summarize_key_event(inp.chapter_draft)
        default_agenda = ""
        if inp.planner_output is not None and inp.planner_output.planned_nodes:
            default_agenda = inp.planner_output.planned_nodes[-1].summary

        for character in characters:
            runtime = character.runtime.model_copy(
                update={
                    "current_location": self._infer_location(inp, character),
                    "current_agenda": default_agenda or character.runtime.current_agenda,
                    "current_pressure": round(
                        max(character.runtime.current_pressure, inp.chapter_draft.avg_tension),
                        3,
                    ),
                    "recent_key_events": [
                        key_event,
                        *character.runtime.recent_key_events,
                    ][:3],
                }
            )
            persisted_character = character.model_copy(update={"runtime": runtime})
            try:
                repo.save_character(project_id, persisted_character)
                updated_any = True
            except Exception as exc:
                warnings.append(f"角色持久化失败：{persisted_character.name} - {exc}")

        return updated_any

    def _infer_location(self, inp: MaintenanceInput, character: CharacterState) -> str:
        if inp.planner_output is not None:
            for node in inp.planner_output.planned_nodes:
                location = getattr(node, "location", "")
                if character.name in node.characters and location:
                    return location
            for node in inp.planner_output.planned_nodes:
                location = getattr(node, "location", "")
                if location:
                    return location
        return character.runtime.current_location

    # ---------------------------------------------------------------- #
    # 角色弧推进                                                          #
    # ---------------------------------------------------------------- #

    def _update_arcs(
        self,
        characters: list[CharacterState],
        report: CriticReport | None,
        advance: bool,
        warnings: list[str],
    ) -> list[CharacterState]:
        if not advance:
            return list(characters)

        # 从 ConsistencyReport 提取有 character 问题的角色名
        blocked: set[str] = set()
        if report and report.consistency_report:
            for issue in report.consistency_report.issues:
                if issue.dimension == "character":
                    for ch in characters:
                        if ch.name in issue.description:
                            blocked.add(ch.name)

        updated: list[CharacterState] = []
        for ch in characters:
            if ch.name in blocked:
                warnings.append(f"角色 {ch.name!r} 有一致性问题，跳过弧推进")
                updated.append(ch)
                continue

            # 推进一步（若未到终点）
            try:
                idx = _ARC_ORDER.index(ch.arc_stage)
            except ValueError:
                # 未知阶段，保持不变
                updated.append(ch)
                continue

            if idx < len(_ARC_ORDER) - 1:
                ch = ch.model_copy(update={"arc_stage": _ARC_ORDER[idx + 1]})

            updated.append(ch)

        return updated

    # ---------------------------------------------------------------- #
    # 动机张力宣泄                                                         #
    # ---------------------------------------------------------------- #

    def _release_tension(
        self,
        characters: list[CharacterState],
        report: CriticReport | None,
        warnings: list[str],
    ) -> list[CharacterState]:
        """
        若本章涉及角色关键冲突事件（从 critic_report 中判断），
        将相关角色的 motivation.tension 降低 0.1（表示冲突得到了宣泄）。
        """
        if not report or not report.consistency_report:
            return characters

        # 收集本章涉及关键冲突的角色名（来自一致性报告中的 character 维度 issue）
        conflict_chars: set[str] = set()
        for issue in report.consistency_report.issues:
            if issue.dimension == "character":
                for ch in characters:
                    if ch.name in issue.description:
                        conflict_chars.add(ch.name)

        if not conflict_chars:
            return characters

        result: list[CharacterState] = []
        for ch in characters:
            if ch.name not in conflict_chars or not ch.motivations:
                result.append(ch)
                continue

            # 降低高张力动机的 tension 值
            new_motivations = []
            tension_reduced = False
            for m in ch.motivations:
                if m.tension >= 0.6:
                    new_tension = max(0.0, round(m.tension - 0.1, 2))
                    new_motivations.append(m.model_copy(update={"tension": new_tension}))
                    tension_reduced = True
                else:
                    new_motivations.append(m)

            if tension_reduced:
                ch = ch.model_copy(update={"motivations": new_motivations})
                warnings.append(f"角色「{ch.name}」本章涉及冲突，高张力动机 tension 已降低 0.1")

            result.append(ch)

        return result

    # ---------------------------------------------------------------- #
    # 节点状态                                                            #
    # ---------------------------------------------------------------- #

    def _mark_completed_nodes(
        self,
        graph: PlotGraph | None,
        chapter: int,
        warnings: list[str],
    ) -> list[str]:
        if graph is None:
            return []

        completed: list[str] = []
        prefix = f"ch{chapter}_"
        for node_id in list(graph._nodes):
            if node_id.startswith(prefix):
                try:
                    graph.update_event_status(node_id, NodeStatus.COMPLETED)
                    completed.append(node_id)
                except Exception as exc:
                    warnings.append(f"节点 {node_id} 更新失败: {exc}")

        return completed

    def _activate_followup_nodes(
        self,
        graph: PlotGraph | None,
        completed: list[str],
        warnings: list[str],
    ) -> list[str]:
        if graph is None or not completed:
            return []
        try:
            return graph.activate_next_nodes(completed)
        except Exception as exc:
            warnings.append(f"后续节点激活失败: {exc}")
            return []

    def _build_plot_progress(
        self,
        graph: PlotGraph | None,
        completed: list[str],
        activated: list[str],
    ) -> dict[str, Any]:
        def _serialize(node_id: str) -> dict[str, Any]:
            node = graph._nodes.get(node_id) if graph is not None else None
            return {
                "node_id": node_id,
                "summary": getattr(node, "summary", ""),
                "node_type": getattr(getattr(node, "type", None), "value", ""),
                "status": getattr(getattr(node, "status", None), "value", ""),
            }

        return {
            "completed": [_serialize(node_id) for node_id in completed],
            "activated": [_serialize(node_id) for node_id in activated],
            "completed_count": len(completed),
            "activated_count": len(activated),
        }

    # ---------------------------------------------------------------- #
    # 记忆压缩                                                            #
    # ---------------------------------------------------------------- #

    def _compress_memory(
        self,
        memory: MemorySystem | None,
        draft: ChapterDraft,
        warnings: list[str],
    ) -> str:
        if memory is None:
            return ""

        snippet = draft.draft_text[:120].strip()
        summary = f"第{draft.chapter}章事件摘要：{snippet}…"
        try:
            memory.write_memory(
                content=summary,
                memory_type="event",
                layer="mid",
                chapter=draft.chapter,
                importance=0.7,
                pool=MemoryPool.AUTHOR,
            )
        except Exception as exc:
            warnings.append(f"记忆写入失败: {exc}")
            return ""

        return summary

    def _write_memory_anchor(
        self,
        memory: MemorySystem | None,
        draft: ChapterDraft,
        warnings: list[str],
    ) -> dict[str, Any] | None:
        if memory is None:
            return None

        key_pivot = self._summarize_key_event(draft)
        next_debt = self._extract_next_hook(draft)
        try:
            anchor = memory.write_anchor(
                chapter=draft.chapter,
                key_pivot=key_pivot,
                burning_question=next_debt,
                protagonist_emotion="承压",
                next_chapter_debt=next_debt,
                hook_type="cliffhanger" if next_debt else "",
            )
        except Exception as exc:
            warnings.append(f"记忆锚点写入失败: {exc}")
            return None

        return anchor

    def _format_memory_anchor(self, anchor: dict[str, Any] | None) -> str:
        if not anchor:
            return ""
        return (
            f"[锚点-章{anchor.get('chapter', 0)}] {anchor.get('key_pivot', '')} | 悬念:{anchor.get('burning_question', '')}"
        )[:150]

    def _build_memory_anchor_entries(
        self,
        memory_summary: str,
        anchor: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if memory_summary:
            entries.append(
                {
                    "type": "summary",
                    "layer": "mid",
                    "content": memory_summary,
                }
            )
        if anchor:
            entries.append(
                {
                    "type": "anchor",
                    "layer": "short",
                    "chapter": anchor.get("chapter", 0),
                    "key_pivot": anchor.get("key_pivot", ""),
                    "burning_question": anchor.get("burning_question", ""),
                    "next_chapter_debt": anchor.get("next_chapter_debt", ""),
                }
            )
        return entries

    def _create_world_changeset(
        self,
        inp: MaintenanceInput,
        warnings: list[str],
    ) -> tuple[str | None, list[dict[str, Any]]]:
        if not inp.chapter_draft.draft_text.strip():
            return None, []

        try:
            from narrative_os.core.evolution import (
                ChangeSource,
                ChangeTag,
                SessionCommitMode,
                WorldChange,
                get_canon_commit,
            )

            cc = get_canon_commit(inp.project_id)
            description = self._summarize_key_event(inp.chapter_draft)
            cs = cc.create_changeset(
                project_id=inp.project_id,
                source=ChangeSource.PIPELINE,
                changes=[
                    WorldChange(
                        source=ChangeSource.PIPELINE,
                        chapter=inp.chapter_draft.chapter,
                        tag=ChangeTag.CANON_PENDING,
                        change_type="timeline_event",
                        description=description,
                        after_value={
                            "chapter": inp.chapter_draft.chapter,
                            "event": description,
                        },
                    )
                ],
                commit_mode=SessionCommitMode.DRAFT_CHAPTER,
            )
            pending_changes = [
                {
                    "change_type": change.change_type,
                    "description": change.description,
                    "tag": getattr(change.tag, "value", str(change.tag)),
                    "chapter": change.chapter,
                    "before_snapshot": change.before_snapshot,
                    "after_value": change.after_value,
                }
                for change in cs.pending_changes()
            ]
            return cs.changeset_id, pending_changes
        except Exception as exc:
            warnings.append(f"WorldChangeSet 创建失败: {exc}")
            return None, []

    def _build_world_state_delta(
        self,
        *,
        original_characters: list[CharacterState],
        updated_characters: list[CharacterState],
        canon_pending_changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deltas: list[dict[str, Any]] = []
        original_by_name = {character.name: character for character in original_characters}
        for updated in updated_characters:
            original = original_by_name.get(updated.name)
            if original is None:
                continue
            if original.arc_stage != updated.arc_stage:
                deltas.append(
                    {
                        "change_type": "character_arc",
                        "target": updated.name,
                        "before": original.arc_stage,
                        "after": updated.arc_stage,
                        "effect": f"角色弧由 {original.arc_stage} 推进到 {updated.arc_stage}",
                    }
                )
            if original.runtime.current_agenda != updated.runtime.current_agenda:
                deltas.append(
                    {
                        "change_type": "character_runtime",
                        "target": updated.name,
                        "before": original.runtime.current_agenda,
                        "after": updated.runtime.current_agenda,
                        "effect": "当前行动议程已更新",
                    }
                )
        for change in canon_pending_changes:
            deltas.append(
                {
                    "change_type": change.get("change_type", "world_change"),
                    "target": change.get("after_value", {}).get("event", "timeline"),
                    "before": "",
                    "after": change.get("description", ""),
                    "effect": "已生成待审批的世界状态变更",
                }
            )
        return deltas

    def _persist_hook(
        self,
        state_manager: StateManager,
        chapter: int,
        hook_text: str,
        warnings: list[str],
    ) -> bool:
        if not hook_text:
            return False
        try:
            state_manager.save_last_hook(chapter, hook_text)
            return True
        except Exception as exc:
            warnings.append(f"Hook 持久化失败: {exc}")
            return False

    # ---------------------------------------------------------------- #
    # 钩子提取                                                            #
    # ---------------------------------------------------------------- #

    def _extract_next_hook(self, draft: ChapterDraft) -> str:
        """取草稿末尾 60 字作为下一章钩子提示。"""
        text = draft.draft_text.strip()
        if not text:
            return ""
        return text[-60:] if len(text) > 60 else text

    def _summarize_key_event(self, draft: ChapterDraft) -> str:
        text = " ".join(draft.draft_text.split())
        return text[:120] if text else f"第{draft.chapter}章推进"
