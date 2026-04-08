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

from pydantic import BaseModel, Field

from narrative_os.agents.critic import CriticReport
from narrative_os.agents.planner import PlannerOutput
from narrative_os.agents.writer import ChapterDraft
from narrative_os.core.character import ArcStage, CharacterState
from narrative_os.core.memory import MemorySystem
from narrative_os.core.plot import NodeStatus, PlotGraph
from narrative_os.infra.logging import logger


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
    next_hook: str = ""
    completed_nodes: list[str] = Field(default_factory=list)
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
    ) -> MaintenanceOutput:
        warnings: list[str] = []

        # 1. 推进角色弧
        updated = self._update_arcs(
            inp.characters,
            inp.critic_report,
            inp.advance_arcs,
            warnings,
        )

        # 2. 标记本章节点已完成
        completed = self._mark_completed_nodes(
            plot_graph,
            inp.chapter_draft.chapter,
            warnings,
        )

        # 3. 压缩短期记忆 → mid 层
        mem_summary = self._compress_memory(memory, inp.chapter_draft, warnings)

        # 4. 提取下一章钩子
        hook = self._extract_next_hook(inp.chapter_draft)

        logger.info(
            "maintenance_done",
            chapter=inp.chapter_draft.chapter,
            arc_advanced=len(updated),
            completed_nodes=len(completed),
            warnings=len(warnings),
        )

        return MaintenanceOutput(
            chapter=inp.chapter_draft.chapter,
            updated_characters=updated,
            memory_summary=mem_summary,
            next_hook=hook,
            completed_nodes=completed,
            warnings=warnings,
        )

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
            )
        except Exception as exc:
            warnings.append(f"记忆写入失败: {exc}")
            return ""

        return summary

    # ---------------------------------------------------------------- #
    # 钩子提取                                                            #
    # ---------------------------------------------------------------- #

    def _extract_next_hook(self, draft: ChapterDraft) -> str:
        """取草稿末尾 60 字作为下一章钩子提示。"""
        text = draft.draft_text.strip()
        if not text:
            return ""
        return text[-60:] if len(text) > 60 else text
