"""schemas/story_plans.py — 多尺度剧情模型预埋。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from narrative_os.agents.planner import PlannerOutput


class SceneBeat(BaseModel):
    beat_index: int = 0
    beat_key: str = ""
    label: str = ""
    objective: str = ""
    conflict: str = ""
    outcome: str = ""
    tension: float = 0.0
    location: str = ""
    characters: list[str] = Field(default_factory=list)
    source_node_ids: list[str] = Field(default_factory=list)
    estimated_words: int = 0
    user_id: str = "local"


class ChapterPlan(BaseModel):
    project_id: str
    chapter_num: int
    volume_num: int = 1
    title: str = ""
    summary: str = ""
    hook: str = ""
    tension_target: float = 0.0
    dialogue_goals: list[str] = Field(default_factory=list)
    legacy_outline_text: str = ""
    source_run_id: str | None = None
    user_id: str = "local"
    scene_beats: list[SceneBeat] = Field(default_factory=list)

    @classmethod
    def from_planner_output(
        cls,
        *,
        project_id: str,
        chapter_num: int,
        volume_num: int,
        planner_output: PlannerOutput,
        source_run_id: str | None = None,
        estimated_total_words: int = 0,
        user_id: str = "local",
    ) -> "ChapterPlan":
        node_count = max(1, len(planner_output.planned_nodes))
        estimated_words = int(estimated_total_words / node_count) if estimated_total_words > 0 else 0
        beats = [
            SceneBeat(
                beat_index=index,
                beat_key=node.id,
                label=node.type,
                objective=node.summary,
                conflict=node.summary if node.type in {"conflict", "twist"} else "",
                outcome=planner_output.hook_suggestion if index == len(planner_output.planned_nodes) - 1 else "",
                tension=node.tension,
                characters=list(node.characters),
                source_node_ids=[node.id],
                estimated_words=estimated_words,
                user_id=user_id,
            )
            for index, node in enumerate(planner_output.planned_nodes)
        ]

        tension_target = 0.0
        if planner_output.tension_curve:
            tension_target = float(planner_output.tension_curve[-1][1])
        elif planner_output.planned_nodes:
            tension_target = float(planner_output.planned_nodes[-1].tension)

        return cls(
            project_id=project_id,
            chapter_num=chapter_num,
            volume_num=volume_num,
            title=f"第{chapter_num}章",
            summary=planner_output.chapter_outline,
            hook=planner_output.hook_suggestion,
            tension_target=tension_target,
            dialogue_goals=list(planner_output.dialogue_goals),
            legacy_outline_text=planner_output.chapter_outline,
            source_run_id=source_run_id,
            user_id=user_id,
            scene_beats=beats,
        )


class VolumePlan(BaseModel):
    project_id: str
    volume_num: int = 1
    title: str = ""
    premise: str = ""
    arc_summary: str = ""
    user_id: str = "local"
    chapters: list[ChapterPlan] = Field(default_factory=list)


class BookPlan(BaseModel):
    project_id: str
    title: str = ""
    premise: str = ""
    genre: str = ""
    total_volumes: int = 1
    user_id: str = "local"
    volumes: list[VolumePlan] = Field(default_factory=list)