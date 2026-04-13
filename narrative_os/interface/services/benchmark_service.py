"""services/benchmark_service.py — Benchmark Phase 2 应用服务。"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from narrative_os.core.benchmark_repository import (
    BenchmarkRepository,
    get_benchmark_repository,
)
from narrative_os.infra.models import (
    ArtifactRecord,
    AuthorSkillRecord,
    BenchmarkProfileRecord,
    BenchmarkScoreRecord,
    BenchmarkSnippetRecord,
    BenchmarkSourceRecord,
    RunRecord,
    RunStepRecord,
)
from narrative_os.interface.services.project_service import ProjectService, get_project_service
from narrative_os.interface.services.trace_service import TraceService, get_trace_service
from narrative_os.infra.cost import cost_ctrl
from narrative_os.schemas.benchmark import (
    AuthorSkillProfile,
    BenchmarkJobCreateRequest,
    BenchmarkJobCreateResponse,
    BenchmarkJobDetailResponse,
    BenchmarkSkillApplyMode,
    BenchmarkSkillApplyRequest,
    BenchmarkSkillApplyResponse,
    BenchmarkSkillListResponse,
    BenchmarkJobType,
    BenchmarkProfile,
    BenchmarkProfileActivateRequest,
    BenchmarkProfileStatus,
    BenchmarkSceneType,
    BenchmarkScore,
    BenchmarkSnippet,
    BenchmarkSnippetListResponse,
    BenchmarkSource,
    BenchmarkSourceType,
)
from narrative_os.schemas.traces import ArtifactType, RunStatus, RunType

_DEFAULT_CHAPTER_PATTERN = r"^第[零一二三四五六七八九十百千\d]+章.*$"
_AUTHOR_SKILL_APPLICATION_KEY = "benchmark.author_skill_application"
_AUTHOR_DISTILLATION_MIN_SOURCES = 3
_AUTHOR_DISTILLATION_MIN_CHARS = 60
_DEFAULT_BENCHMARK_TOKEN_BUDGET = 40000
_DEFAULT_BENCHMARK_JOB_TIMEOUT_SEC = 15.0
_SCENE_RULES: list[tuple[BenchmarkSceneType, tuple[str, ...]]] = [
    (BenchmarkSceneType.BATTLE, ("战", "杀", "剑", "刀", "拳", "血", "斩", "冲")),
    (BenchmarkSceneType.EMOTION, ("心", "眼", "泪", "呼吸", "沉默", "笑", "哭", "痛")),
    (BenchmarkSceneType.REVEAL, ("真相", "秘密", "原来", "发现", "揭开", "线索", "证据")),
    (BenchmarkSceneType.DAILY, ("日常", "吃饭", "回家", "清晨", "街上", "闲聊", "房间")),
    (BenchmarkSceneType.ENSEMBLE, ("众人", "大家", "所有人", "围观", "人群", "同伴")),
]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


class BenchmarkService:
    def __init__(
        self,
        repository: BenchmarkRepository | None = None,
        trace_service: TraceService | None = None,
        project_service: ProjectService | None = None,
    ) -> None:
        self._repository = repository or get_benchmark_repository()
        self._trace_service = trace_service or get_trace_service()
        self._project_service = project_service or get_project_service()

    async def create_job(
        self,
        db: AsyncSession,
        project_id: str,
        req: BenchmarkJobCreateRequest,
    ) -> BenchmarkJobCreateResponse:
        self._project_service.load_project_or_404(project_id)

        created_sources = await self._create_sources(db, project_id, req)
        existing_sources = await self._repository.get_sources_by_ids(db, project_id, req.source_ids)
        if req.source_ids and len(existing_sources) != len(set(req.source_ids)):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": "部分 benchmark source 不存在。", "code": "NOT_FOUND"},
            )

        all_sources = self._dedupe_sources([*existing_sources, *created_sources])
        if not all_sources:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={"detail": "缺少可用 benchmark source。", "code": "VALIDATION_ERROR"},
            )
        if req.job_type == BenchmarkJobType.AUTHOR_DISTILLATION:
            self._validate_author_distillation_sources(req, all_sources)

        now = datetime.now(timezone.utc)
        run_id = uuid.uuid4().hex
        run_type = self._map_run_type(req.job_type)
        source_ids = [item.id for item in all_sources]
        profile_id = uuid.uuid4().hex
        profile_name = self._build_profile_name(req, all_sources, now)

        await self._ensure_benchmark_budget(db, project_id)
        timeout_seconds = await self._resolve_benchmark_timeout(db, project_id)
        try:
            async with asyncio.timeout(timeout_seconds):
                snippets = await asyncio.to_thread(
                    self._extract_snippets,
                    project_id,
                    profile_id,
                    all_sources,
                    req.extract_snippets,
                )
                synthesized = await asyncio.to_thread(self._synthesize_profile, req, all_sources, snippets)
        except asyncio.TimeoutError as exc:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail={"detail": "benchmark job 执行超时，当前结果已隔离且未污染 active profile。", "code": "TIMEOUT"},
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"detail": f"benchmark job 执行失败，但不会影响主写作链路：{exc}", "code": "JOB_FAILED"},
            ) from exc

        run = RunRecord(
            id=run_id,
            project_id=project_id,
            run_type=run_type.value,
            status=RunStatus.COMPLETED.value,
            correlation_id=uuid.uuid4().hex[:8],
            started_at=now,
            ended_at=now,
        )
        step_ingest = RunStepRecord(
            id=uuid.uuid4().hex,
            run_id=run_id,
            step_index=0,
            agent_name="benchmark_ingest",
            status=RunStatus.COMPLETED.value,
            correlation_id=run.correlation_id,
            started_at=now,
            ended_at=now,
        )
        step_synthesis = RunStepRecord(
            id=uuid.uuid4().hex,
            run_id=run_id,
            step_index=1,
            agent_name="benchmark_synthesis",
            status=RunStatus.COMPLETED.value,
            correlation_id=run.correlation_id,
            started_at=now,
            ended_at=now,
        )

        profile = BenchmarkProfileRecord(
            id=profile_id,
            project_id=project_id,
            run_id=run_id,
            profile_type=req.job_type.value,
            profile_name=profile_name,
            source_ids_json=json.dumps(source_ids, ensure_ascii=False),
            stable_traits_json=json.dumps(synthesized["stable_traits"], ensure_ascii=False),
            conditional_traits_json=json.dumps(synthesized["conditional_traits"], ensure_ascii=False),
            anti_traits_json=json.dumps(synthesized["anti_traits"], ensure_ascii=False),
            scene_anchors_json=json.dumps(synthesized["scene_anchors"], ensure_ascii=False),
            humanness_baseline_json=json.dumps(synthesized["humanness_baseline"], ensure_ascii=False),
            status=BenchmarkProfileStatus.DRAFT.value,
            created_at=now,
        )

        author_skill: AuthorSkillRecord | None = None
        if req.job_type == BenchmarkJobType.AUTHOR_DISTILLATION:
            author_skill = AuthorSkillRecord(
                id=uuid.uuid4().hex,
                project_id=project_id,
                run_id=run_id,
                skill_name=profile_name,
                author_name=req.author_name or (all_sources[0].author_name or ""),
                source_ids_json=json.dumps(source_ids, ensure_ascii=False),
                stable_rules_json=json.dumps(synthesized["stable_traits"], ensure_ascii=False),
                conditional_rules_json=json.dumps(synthesized["conditional_traits"], ensure_ascii=False),
                anti_rules_json=json.dumps(synthesized["anti_traits"], ensure_ascii=False),
                dialogue_rules_json=json.dumps(synthesized["dialogue_rules"], ensure_ascii=False),
                scene_patterns_json=json.dumps(synthesized["scene_anchors"], ensure_ascii=False),
                chapter_hook_patterns_json=json.dumps(synthesized["hook_patterns"], ensure_ascii=False),
                humanness_baseline_json=json.dumps(synthesized["humanness_baseline"], ensure_ascii=False),
                confidence_map_json=json.dumps(synthesized["confidence_map"], ensure_ascii=False),
                status=BenchmarkProfileStatus.DRAFT.value,
                created_at=now,
            )

        artifacts = [
            ArtifactRecord(
                id=uuid.uuid4().hex,
                run_id=run_id,
                step_id=step_ingest.id,
                artifact_type=ArtifactType.BENCHMARK_SNIPPET.value,
                agent_name="benchmark_ingest",
                input_summary=f"{len(all_sources)} sources",
                output_content=json.dumps(
                    {
                        "source_ids": source_ids,
                        "snippet_count": len(snippets),
                        "extract_snippets": req.extract_snippets,
                    },
                    ensure_ascii=False,
                ),
                correlation_id=run.correlation_id,
                quality_scores=json.dumps({"snippet_count": float(len(snippets))}, ensure_ascii=False),
                created_at=now,
            ),
            ArtifactRecord(
                id=uuid.uuid4().hex,
                run_id=run_id,
                step_id=step_synthesis.id,
                artifact_type=(
                    ArtifactType.AUTHOR_SKILL.value
                    if req.job_type == BenchmarkJobType.AUTHOR_DISTILLATION
                    else ArtifactType.BENCHMARK_PROFILE.value
                ),
                agent_name="benchmark_synthesis",
                input_summary=profile_name,
                output_content=json.dumps(
                    {
                        "profile_id": profile_id,
                        "profile_name": profile_name,
                        "scene_anchor_count": len(synthesized["scene_anchors"]),
                        "stable_trait_count": len(synthesized["stable_traits"]),
                    },
                    ensure_ascii=False,
                ),
                correlation_id=run.correlation_id,
                quality_scores=json.dumps(
                    {
                        "stable_trait_count": float(len(synthesized["stable_traits"])),
                        "conditional_trait_count": float(len(synthesized["conditional_traits"])),
                    },
                    ensure_ascii=False,
                ),
                created_at=now,
            ),
        ]

        await self._repository.create_run_with_profile(
            db,
            run=run,
            profile=profile,
            snippets=snippets,
            author_skill=author_skill,
            step_records=[step_ingest, step_synthesis],
            artifact_records=artifacts,
        )

        snippet_count = len(snippets)
        serialized_author_skill = self._serialize_author_skill(author_skill) if author_skill is not None else None
        return BenchmarkJobCreateResponse(
            run_id=run_id,
            status=RunStatus.COMPLETED.value,
            profile=self._serialize_profile(profile, snippet_count=snippet_count),
            author_skill=serialized_author_skill,
            source_ids=source_ids,
            snippet_count=snippet_count,
            message=(
                "Author skill 已生成，可继续查看 skill 详情并应用到当前项目。"
                if req.job_type == BenchmarkJobType.AUTHOR_DISTILLATION
                else "Benchmark profile 已生成，可继续查看 snippets 或激活为当前项目对标。"
            ),
        )

    async def get_job(
        self,
        db: AsyncSession,
        project_id: str,
        run_id: str,
    ) -> BenchmarkJobDetailResponse:
        run = await self._trace_service.get_run(db, run_id, include_steps=True)
        if run.project_id != project_id or run.run_type not in {
            RunType.BENCHMARK_ANALYSIS,
            RunType.AUTHOR_DISTILLATION,
        }:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Benchmark job '{run_id}' 不存在。", "code": "NOT_FOUND"},
            )

        profile_record = await self._repository.get_profile_by_run(db, run_id)
        author_skill_record = await self._repository.get_author_skill_by_run(db, run_id)
        skill_application = await self._get_skill_application(db, project_id)
        profile = None
        author_skill = None
        snippets: list[BenchmarkSnippet] = []
        sources: list[BenchmarkSource] = []
        if profile_record is not None:
            snippet_records = await self._repository.list_snippets_by_profile(
                db,
                project_id,
                profile_record.id,
                limit=12,
            )
            profile = self._serialize_profile(profile_record, snippet_count=len(snippet_records))
            source_records = await self._repository.get_sources_by_ids(db, project_id, profile.source_ids)
            source_map = {item.id: item for item in source_records}
            sources = [self._serialize_source(item) for item in source_records]
            snippets = [self._serialize_snippet(item, source_hit_verified=self._verify_snippet_hit(source_map.get(item.source_id), item)) for item in snippet_records]
        if author_skill_record is not None:
            author_skill = self._serialize_author_skill(author_skill_record, application=skill_application)

        return BenchmarkJobDetailResponse(
            run=run,
            profile=profile,
            author_skill=author_skill,
            sources=sources,
            snippets=snippets,
            message=(
                "Author distillation 已完成，可继续查看 skill 结构并应用到当前项目。"
                if run.run_type == RunType.AUTHOR_DISTILLATION.value
                else "Phase 2 已支持 ingest、snippet extraction、profile synthesis 与激活前预览。"
            ),
        )

    async def get_profile(self, db: AsyncSession, project_id: str) -> BenchmarkProfile | None:
        profile = await self._repository.get_active_profile(db, project_id)
        if profile is None:
            profile = await self._repository.get_latest_profile(db, project_id)
        if profile is None:
            return None
        snippet_count = await self._repository.count_snippets_by_profile(db, profile.id)
        return self._serialize_profile(profile, snippet_count=snippet_count)

    async def list_snippets(
        self,
        db: AsyncSession,
        project_id: str,
        profile_id: str | None = None,
        scene_type: str | None = None,
        limit: int = 60,
    ) -> BenchmarkSnippetListResponse:
        profile_record = None
        if profile_id:
            profile_record = await self._repository.get_profile(db, project_id, profile_id)
        if profile_record is None:
            profile_record = await self._repository.get_active_profile(db, project_id)
        if profile_record is None:
            profile_record = await self._repository.get_latest_profile(db, project_id)
        if profile_record is None:
            return BenchmarkSnippetListResponse(profile=None, items=[])

        snippets = await self._repository.list_snippets_by_profile(
            db,
            project_id,
            profile_record.id,
            scene_type=scene_type,
            limit=limit,
        )
        source_records = await self._repository.get_sources_by_ids(
            db,
            project_id,
            {item.source_id for item in snippets},
        )
        source_map = {item.id: item for item in source_records}
        return BenchmarkSnippetListResponse(
            profile=self._serialize_profile(profile_record, snippet_count=len(snippets)),
            items=[
                self._serialize_snippet(item, source_hit_verified=self._verify_snippet_hit(source_map.get(item.source_id), item))
                for item in snippets
            ],
        )

    async def activate_profile(
        self,
        db: AsyncSession,
        project_id: str,
        req: BenchmarkProfileActivateRequest,
    ) -> BenchmarkProfile:
        profile = await self._repository.get_profile(db, project_id, req.profile_id)
        if profile is None or profile.profile_type != BenchmarkJobType.PROJECT_BENCHMARK.value:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Benchmark profile '{req.profile_id}' 不存在。", "code": "NOT_FOUND"},
            )
        activated = await self._repository.activate_profile(
            db,
            project_id,
            req.profile_id,
            activated_at=datetime.now(timezone.utc),
        )
        if activated is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"detail": "profile 激活失败。", "code": "ACTIVATE_FAILED"},
            )
        snippet_count = await self._repository.count_snippets_by_profile(db, activated.id)
        return self._serialize_profile(activated, snippet_count=snippet_count)

    async def list_skills(
        self,
        db: AsyncSession,
        project_id: str,
        *,
        author_name: str | None = None,
        limit: int = 50,
    ) -> BenchmarkSkillListResponse:
        self._project_service.load_project_or_404(project_id)
        application = await self._get_skill_application(db, project_id)
        records = await self._repository.list_author_skills(db, author_name=author_name, limit=limit)
        return BenchmarkSkillListResponse(
            items=[self._serialize_author_skill(item, application=application) for item in records],
            active_skill_id=application.get("skill_id") if application else None,
            active_mode=self._parse_skill_apply_mode(application.get("mode")) if application else None,
        )

    async def get_skill(
        self,
        db: AsyncSession,
        project_id: str,
        skill_id: str,
    ) -> AuthorSkillProfile:
        self._project_service.load_project_or_404(project_id)
        record = await self._repository.get_author_skill(db, skill_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Author skill '{skill_id}' 不存在。", "code": "NOT_FOUND"},
            )
        application = await self._get_skill_application(db, project_id)
        return self._serialize_author_skill(record, application=application)

    async def apply_skill(
        self,
        db: AsyncSession,
        project_id: str,
        skill_id: str,
        req: BenchmarkSkillApplyRequest,
    ) -> BenchmarkSkillApplyResponse:
        self._project_service.load_project_or_404(project_id)
        record = await self._repository.get_author_skill(db, skill_id)
        if record is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={"detail": f"Author skill '{skill_id}' 不存在。", "code": "NOT_FOUND"},
            )
        application = {
            "skill_id": skill_id,
            "mode": req.mode.value,
            "applied_at": _iso(datetime.now(timezone.utc)),
        }
        await self._repository.upsert_project_setting(db, project_id, _AUTHOR_SKILL_APPLICATION_KEY, application)
        return BenchmarkSkillApplyResponse(
            skill=self._serialize_author_skill(record, application=application),
            mode=req.mode,
            message=f"Author skill 已按 {req.mode.value} 模式应用到当前项目。",
        )

    async def get_active_profile_summary(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> dict[str, Any] | None:
        profile = await self.get_profile(db, project_id)
        if profile is None or profile.status != BenchmarkProfileStatus.ACTIVE:
            return None
        scene_hints: list[str] = []
        for scene_name, anchors in profile.scene_anchors.items():
            if not anchors:
                continue
            scene_hints.append(f"{scene_name} 场景优先参考已抽出的 anchor 节奏。")
        return {
            "profile_id": profile.profile_id,
            "profile_name": profile.profile_name,
            "mode": profile.profile_type.value,
            "top_rules": [item.get("summary", "") for item in profile.stable_traits[:3] if item.get("summary")],
            "anti_rules": [item.get("summary", "") for item in profile.anti_traits[:2] if item.get("summary")],
            "scene_hints": scene_hints,
            "active_scene_anchor_count": sum(len(items) for items in profile.scene_anchors.values()),
        }

    async def get_active_author_skill_summary(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> dict[str, Any] | None:
        application = await self._get_skill_application(db, project_id)
        if not application:
            return None

        skill_id = str(application.get("skill_id") or "")
        mode_raw = str(application.get("mode") or BenchmarkSkillApplyMode.HYBRID.value)
        if not skill_id:
            return None

        record = await self._repository.get_author_skill(db, skill_id)
        if record is None:
            return None

        mode = self._parse_skill_apply_mode(mode_raw) or BenchmarkSkillApplyMode.HYBRID
        skill = self._serialize_author_skill(record, application=application)
        scene_hints = [
            f"{scene_name} 场景可借鉴 {skill.skill_name} 的推进模板。"
            for scene_name, anchors in skill.scene_patterns.items()
            if anchors
        ]
        top_rule_limit = 2 if mode == BenchmarkSkillApplyMode.GUIDE else 3
        anti_rule_limit = 1 if mode == BenchmarkSkillApplyMode.GUIDE else 2
        return {
            "profile_id": skill.skill_id,
            "profile_name": skill.skill_name,
            "mode": "author_skill",
            "application_mode": mode.value,
            "top_rules": [item.get("summary", "") for item in skill.stable_rules[:top_rule_limit] if item.get("summary")],
            "anti_rules": [item.get("summary", "") for item in skill.anti_rules[:anti_rule_limit] if item.get("summary")],
            "scene_hints": scene_hints[: (1 if mode == BenchmarkSkillApplyMode.GUIDE else 2)],
            "active_scene_anchor_count": sum(
                len(items) for items in skill.scene_patterns.values() if isinstance(items, list)
            ),
        }

    async def score_text(
        self,
        db: AsyncSession,
        project_id: str,
        *,
        chapter: int,
        text: str,
        run_id: str | None = None,
    ) -> BenchmarkScore | None:
        profile_record = await self._repository.get_active_profile(db, project_id)
        if profile_record is None:
            return None

        profile = self._serialize_profile(
            profile_record,
            snippet_count=await self._repository.count_snippets_by_profile(db, profile_record.id),
        )
        baseline = profile.humanness_baseline
        sentence_lengths = self._sentence_lengths(text)
        paragraph_lengths = [len(item) for item in self._split_paragraphs(text) if item]
        avg_sentence = mean(sentence_lengths) if sentence_lengths else 0.0
        avg_paragraph = mean(paragraph_lengths) if paragraph_lengths else 0.0
        dialogue_ratio = (text.count("“") + text.count('"')) / max(len(text), 1)
        exclamation_density = (text.count("！") + text.count("!")) / max(len(sentence_lengths), 1)
        dominant_scene = max(
            (baseline.get("scene_distribution") or {}).items(),
            key=lambda item: item[1],
            default=(BenchmarkSceneType.GENERAL.value, 0),
        )[0]
        current_scene, _ = self._classify_scene(text)
        punctuation_variety = len({token for token in "，。！？；：“”……" if token in text}) / 8
        sentence_variety = 0.0
        if sentence_lengths:
            sentence_variety = min(1.0, (max(sentence_lengths) - min(sentence_lengths)) / max(avg_sentence, 1))

        dimension_scores = {
            "sentence_rhythm": self._score_closeness(
                avg_sentence,
                float(baseline.get("avg_sentence_length") or avg_sentence or 1.0),
                max(6.0, float(baseline.get("avg_sentence_length") or 1.0) * 0.35),
            ),
            "paragraph_breath": self._score_closeness(
                avg_paragraph,
                float(baseline.get("avg_paragraph_length") or avg_paragraph or 1.0),
                max(22.0, float(baseline.get("avg_paragraph_length") or 1.0) * 0.4),
            ),
            "dialogue_balance": self._score_closeness(
                dialogue_ratio,
                float(baseline.get("dialogue_ratio") or dialogue_ratio),
                0.045,
            ),
            "scene_alignment": 1.0 if dominant_scene in {current_scene.value, BenchmarkSceneType.GENERAL.value} else 0.58,
        }
        adherence_score = round(sum(dimension_scores.values()) / len(dimension_scores), 3)
        humanness_score = round(
            min(
                1.0,
                0.32 * punctuation_variety
                + 0.38 * sentence_variety
                + 0.15 * min(1.0, len(paragraph_lengths) / 4)
                + 0.15 * (1 - min(abs(dialogue_ratio - 0.08) / 0.08, 1.0)),
            ),
            3,
        )

        violations: list[str] = []
        if any(item.get("name") == "avoid_excessive_exclamation" for item in profile.anti_traits) and exclamation_density > 0.12:
            violations.append("感叹号密度高于 benchmark 基线。")
        if any(item.get("name") == "avoid_dialogue_flood" for item in profile.anti_traits) and dialogue_ratio > float(baseline.get("dialogue_ratio") or 0.02) + 0.03:
            violations.append("对白密度偏高，超过当前 benchmark 的推荐区间。")
        if any(item.get("name") == "avoid_over_explaining" for item in profile.anti_traits) and avg_sentence > float(baseline.get("avg_sentence_length") or avg_sentence) + 8:
            violations.append("句长明显偏长，存在解释性过强风险。")

        recommendations = [
            f"补强 {dimension}，当前得分 {score:.2f}。"
            for dimension, score in dimension_scores.items()
            if score < 0.68
        ]

        created_at = datetime.now(timezone.utc)
        score_record = BenchmarkScoreRecord(
            id=uuid.uuid4().hex,
            project_id=project_id,
            run_id=run_id,
            chapter=chapter,
            profile_id=profile.profile_id,
            humanness_score=humanness_score,
            adherence_score=adherence_score,
            dimension_scores_json=json.dumps(dimension_scores, ensure_ascii=False),
            violations_json=json.dumps(violations, ensure_ascii=False),
            recommendations_json=json.dumps(recommendations, ensure_ascii=False),
            created_at=created_at,
        )

        artifact: ArtifactRecord | None = None
        if run_id:
            target_step = await self._repository.get_step_by_run_and_agent(db, run_id, "maintenance")
            if target_step is None:
                target_step = await self._repository.get_last_step(db, run_id)
            if target_step is not None:
                artifact = ArtifactRecord(
                    id=uuid.uuid4().hex,
                    run_id=run_id,
                    step_id=target_step.id,
                    artifact_type=ArtifactType.BENCHMARK_SCORE.value,
                    agent_name="benchmark_scoring",
                    input_summary=profile.profile_name,
                    output_content=json.dumps(
                        {
                            "chapter": chapter,
                            "violations": violations,
                            "recommendations": recommendations,
                        },
                        ensure_ascii=False,
                    ),
                    correlation_id="",
                    quality_scores=json.dumps(
                        {
                            "benchmark_adherence": adherence_score,
                            "benchmark_humanness": humanness_score,
                        },
                        ensure_ascii=False,
                    ),
                    created_at=created_at,
                )

        await self._repository.create_score(db, score_record, artifact=artifact)
        return BenchmarkScore(
            score_id=score_record.id,
            project_id=project_id,
            run_id=run_id,
            chapter=chapter,
            profile_id=profile.profile_id,
            humanness_score=humanness_score,
            adherence_score=adherence_score,
            dimension_scores=dimension_scores,
            violations=violations,
            recommendations=recommendations,
            created_at=_iso(created_at) or "",
        )

    async def _create_sources(
        self,
        db: AsyncSession,
        project_id: str,
        req: BenchmarkJobCreateRequest,
    ) -> list[BenchmarkSourceRecord]:
        if not req.sources:
            return []
        source_type = self._map_source_type(req.job_type)
        records: list[BenchmarkSourceRecord] = []
        for item in req.sources:
            content = item.text.strip()
            digest_input = content or f"{item.file_name}:{item.title}:{req.job_type.value}"
            records.append(
                BenchmarkSourceRecord(
                    id=uuid.uuid4().hex,
                    project_id=project_id,
                    corpus_group=item.corpus_group or req.corpus_group or "",
                    title=item.title,
                    author_name=item.author_name or req.author_name,
                    file_name=item.file_name,
                    sha256=hashlib.sha256(digest_input.encode("utf-8")).hexdigest(),
                    char_count=len(content),
                    chapter_sep=item.chapter_sep or req.chapter_sep,
                    source_type=source_type.value,
                    text_content=content,
                )
            )
        return await self._repository.create_sources(db, records)

    def _extract_snippets(
        self,
        project_id: str,
        profile_id: str,
        sources: list[BenchmarkSourceRecord],
        extract_snippets: bool,
    ) -> list[BenchmarkSnippetRecord]:
        if not extract_snippets:
            return []
        snippets: list[BenchmarkSnippetRecord] = []
        for source in sources:
            text = source.text_content.strip()
            if not text:
                continue
            for chapter_num, chapter_text in self._split_chapters(text, source.chapter_sep):
                for paragraph in self._split_paragraphs(chapter_text):
                    if len(paragraph) < 48:
                        continue
                    scene_type, purity_score = self._classify_scene(paragraph)
                    anchor_score = self._score_anchor(paragraph)
                    distinctiveness_score = self._score_distinctiveness(paragraph)
                    offset_start = text.find(paragraph)
                    offset_end = offset_start + len(paragraph) if offset_start >= 0 else len(paragraph)
                    snippets.append(
                        BenchmarkSnippetRecord(
                            id=uuid.uuid4().hex,
                            project_id=project_id,
                            profile_id=profile_id,
                            source_id=source.id,
                            scene_type=scene_type.value,
                            chapter=chapter_num,
                            offset_start=max(offset_start, 0),
                            offset_end=max(offset_end, 0),
                            char_count=len(paragraph),
                            anchor_score=anchor_score,
                            purity_score=purity_score,
                            distinctiveness_score=distinctiveness_score,
                            text=paragraph,
                        )
                    )

        snippets.sort(
            key=lambda item: (item.anchor_score, item.purity_score, item.distinctiveness_score),
            reverse=True,
        )
        return snippets[:60]

    def _split_chapters(self, text: str, chapter_sep: str | None) -> list[tuple[int | None, str]]:
        pattern = chapter_sep or _DEFAULT_CHAPTER_PATTERN
        try:
            matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
        except re.error:
            matches = []
        if not matches:
            return [(1, text)]
        sections: list[tuple[int | None, str]] = []
        for index, match in enumerate(matches):
            start = match.start()
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections.append((index + 1, text[start:end].strip()))
        return sections or [(1, text)]

    def _split_paragraphs(self, text: str) -> list[str]:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
        if len(paragraphs) > 1:
            return paragraphs
        sentences = [part.strip() for part in re.split(r"(?<=[。！？!?])", text) if part.strip()]
        if not sentences:
            return [text.strip()]
        chunks: list[str] = []
        buffer = ""
        for sentence in sentences:
            if len(buffer) + len(sentence) < 150:
                buffer += sentence
                continue
            if buffer:
                chunks.append(buffer.strip())
            buffer = sentence
        if buffer:
            chunks.append(buffer.strip())
        return chunks or [text.strip()]

    def _classify_scene(self, text: str) -> tuple[BenchmarkSceneType, float]:
        best_scene = BenchmarkSceneType.GENERAL
        best_hits = 0
        total_hits = 0
        for scene_type, keywords in _SCENE_RULES:
            hits = sum(text.count(keyword) for keyword in keywords)
            total_hits += hits
            if hits > best_hits:
                best_hits = hits
                best_scene = scene_type
        purity = round(min(best_hits / max(len(text) / 80, 1.0), 1.0), 3)
        if total_hits == 0:
            return BenchmarkSceneType.GENERAL, 0.25
        return best_scene, max(purity, 0.35)

    def _score_anchor(self, text: str) -> float:
        sentence_lengths = self._sentence_lengths(text)
        sentence_count = max(len(sentence_lengths), 1)
        target_len = 160
        length_score = max(0.2, 1 - abs(len(text) - target_len) / target_len)
        punctuation_variety = len({token for token in "，。！？；：“”……" if token in text}) / 8
        dialogue_bonus = 0.12 if "“" in text or '"' in text else 0.0
        return round(
            min(1.0, length_score * 0.6 + punctuation_variety * 0.28 + dialogue_bonus + 0.12 / sentence_count),
            3,
        )

    def _score_distinctiveness(self, text: str) -> float:
        sentence_lengths = self._sentence_lengths(text)
        unique_ratio = len(set(text)) / max(len(text), 1)
        long_sentence_ratio = sum(1 for length in sentence_lengths if length >= 28) / max(len(sentence_lengths), 1)
        return round(min(1.0, unique_ratio * 0.75 + long_sentence_ratio * 0.25), 3)

    def _score_closeness(self, actual: float, expected: float, tolerance: float) -> float:
        if tolerance <= 0:
            return 1.0
        return round(max(0.0, 1 - abs(actual - expected) / tolerance), 3)

    def _synthesize_profile(
        self,
        req: BenchmarkJobCreateRequest,
        sources: list[BenchmarkSourceRecord],
        snippets: list[BenchmarkSnippetRecord],
    ) -> dict[str, Any]:
        texts = [item.text_content for item in sources if item.text_content.strip()]
        merged_text = "\n".join(texts)
        sentence_lengths = self._sentence_lengths(merged_text)
        paragraphs = [snippet.text for snippet in snippets] or self._split_paragraphs(merged_text)
        paragraph_lengths = [len(item) for item in paragraphs if item]
        dialogue_ratio = round((merged_text.count("“") + merged_text.count('"')) / max(len(merged_text), 1), 3)
        ellipsis_density = round((merged_text.count("……") + merged_text.count("...")) / max(len(sentence_lengths), 1), 3)
        exclamation_density = round((merged_text.count("！") + merged_text.count("!")) / max(len(sentence_lengths), 1), 3)
        scene_counter = Counter(snippet.scene_type for snippet in snippets)
        avg_sentence = round(mean(sentence_lengths), 2) if sentence_lengths else 0.0
        avg_paragraph = round(mean(paragraph_lengths), 2) if paragraph_lengths else 0.0
        short_sentence_ratio = round(
            sum(1 for length in sentence_lengths if length <= 18) / max(len(sentence_lengths), 1),
            3,
        )

        humanness_baseline = {
            "phase": 2,
            "source_count": len(sources),
            "snippet_count": len(snippets),
            "avg_sentence_length": avg_sentence,
            "avg_paragraph_length": avg_paragraph,
            "dialogue_ratio": dialogue_ratio,
            "ellipsis_density": ellipsis_density,
            "exclamation_density": exclamation_density,
            "scene_distribution": dict(scene_counter),
            "target_platform": req.target_platform or "general",
        }

        stable_traits = [
            {
                "dimension": "micro_language",
                "name": "sentence_rhythm",
                "summary": f"平均句长约 {avg_sentence} 字，短句占比 {short_sentence_ratio:.0%}。",
                "value": avg_sentence,
            },
            {
                "dimension": "paragraph",
                "name": "paragraph_breath",
                "summary": f"段落平均长度约 {avg_paragraph} 字，适合按呼吸点切段。",
                "value": avg_paragraph,
            },
            {
                "dimension": "dialogue",
                "name": "dialogue_density",
                "summary": f"对白符号密度 {dialogue_ratio:.1%}，可作为对白/叙述平衡参考。",
                "value": dialogue_ratio,
            },
        ]

        conditional_traits: list[dict[str, Any]] = []
        for scene_name, count in scene_counter.most_common(3):
            if scene_name == BenchmarkSceneType.GENERAL.value:
                continue
            conditional_traits.append(
                {
                    "dimension": "scene",
                    "name": f"scene_{scene_name}",
                    "summary": f"{scene_name} 场景切片 {count} 条，可优先作为 few-shot anchor。",
                    "value": count,
                }
            )

        anti_traits: list[dict[str, Any]] = []
        if dialogue_ratio < 0.02:
            anti_traits.append(
                {
                    "dimension": "dialogue",
                    "name": "avoid_dialogue_flood",
                    "summary": "参考文本对白密度较低，避免连续对白堆叠。",
                }
            )
        if exclamation_density < 0.08:
            anti_traits.append(
                {
                    "dimension": "punctuation",
                    "name": "avoid_excessive_exclamation",
                    "summary": "参考文本较少依赖感叹号，避免通过标点强行抬情绪。",
                }
            )
        if avg_sentence <= 26:
            anti_traits.append(
                {
                    "dimension": "narrative_control",
                    "name": "avoid_over_explaining",
                    "summary": "参考文本更偏动作/结果推进，避免长句过度解释。",
                }
            )

        scene_anchors: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for snippet in snippets:
            if len(scene_anchors[snippet.scene_type]) >= 3:
                continue
            scene_anchors[snippet.scene_type].append(
                {
                    "snippet_id": snippet.id,
                    "source_id": snippet.source_id,
                    "chapter": snippet.chapter,
                    "text": snippet.text[:180],
                    "anchor_score": snippet.anchor_score,
                }
            )

        return {
            "stable_traits": stable_traits,
            "conditional_traits": conditional_traits,
            "anti_traits": anti_traits,
            "scene_anchors": dict(scene_anchors),
            "humanness_baseline": humanness_baseline,
            "dialogue_rules": [item for item in stable_traits if item["dimension"] == "dialogue"],
            "hook_patterns": [
                {
                    "name": "chapter_tail_pressure",
                    "summary": "优先保留章尾悬念或情绪余波，避免机械收束。",
                }
            ],
            "confidence_map": {
                "stable_traits": 0.72,
                "conditional_traits": 0.64,
                "anti_traits": 0.68,
            },
        }

    def _sentence_lengths(self, text: str) -> list[int]:
        chunks = [item.strip() for item in re.split(r"[。！？!?；;\n]+", text) if item.strip()]
        return [len(item) for item in chunks]

    def _validate_author_distillation_sources(
        self,
        req: BenchmarkJobCreateRequest,
        sources: list[BenchmarkSourceRecord],
    ) -> None:
        if len(sources) < _AUTHOR_DISTILLATION_MIN_SOURCES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "detail": f"author_distillation 至少需要 {_AUTHOR_DISTILLATION_MIN_SOURCES} 部作品。",
                    "code": "VALIDATION_ERROR",
                },
            )

        short_sources = [item.title for item in sources if item.char_count < _AUTHOR_DISTILLATION_MIN_CHARS]
        if short_sources:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "detail": f"以下作品未达到最低有效字数门槛：{', '.join(short_sources)}。",
                    "code": "VALIDATION_ERROR",
                },
            )

        expected_corpus_group = (req.corpus_group or "").strip()
        expected_author_name = (req.author_name or "").strip()
        source_corpus_groups = {(item.corpus_group or "").strip() for item in sources if (item.corpus_group or "").strip()}
        source_author_names = {(item.author_name or "").strip() for item in sources if (item.author_name or "").strip()}

        if expected_corpus_group:
            invalid_corpus_sources = [
                item.title for item in sources if (item.corpus_group or "").strip() not in {"", expected_corpus_group}
            ]
            if invalid_corpus_sources:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "detail": "author_distillation 不允许混入不同 corpus_group 的样本。",
                        "code": "VALIDATION_ERROR",
                    },
                )
        elif len(source_corpus_groups) > 1:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "detail": "author_distillation 发现多个 corpus_group，请显式指定 corpus_group。",
                    "code": "VALIDATION_ERROR",
                },
            )

        if expected_author_name:
            invalid_author_sources = [
                item.title for item in sources if (item.author_name or "").strip() not in {"", expected_author_name}
            ]
            if invalid_author_sources:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={
                        "detail": "author_distillation 不允许默认混入跨作者样本。",
                        "code": "VALIDATION_ERROR",
                    },
                )
        elif len(source_author_names) > 1 and not expected_corpus_group:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "detail": "author_distillation 发现多个 author_name，请显式指定 corpus_group 或 author_name。",
                    "code": "VALIDATION_ERROR",
                },
            )

    def _serialize_profile(
        self,
        record: BenchmarkProfileRecord,
        *,
        snippet_count: int = 0,
    ) -> BenchmarkProfile:
        return BenchmarkProfile(
            profile_id=record.id,
            project_id=record.project_id,
            profile_type=BenchmarkJobType(record.profile_type),
            profile_name=record.profile_name,
            source_ids=self._loads_list(record.source_ids_json),
            stable_traits=self._loads_list(record.stable_traits_json),
            conditional_traits=self._loads_list(record.conditional_traits_json),
            anti_traits=self._loads_list(record.anti_traits_json),
            scene_anchors=self._loads_dict(record.scene_anchors_json),
            humanness_baseline=self._loads_dict(record.humanness_baseline_json),
            status=BenchmarkProfileStatus(record.status),
            snippet_count=snippet_count,
            created_at=_iso(record.created_at) or "",
            activated_at=_iso(record.activated_at),
        )

    def _serialize_author_skill(
        self,
        record: AuthorSkillRecord,
        *,
        application: dict[str, Any] | None = None,
    ) -> AuthorSkillProfile:
        applied = bool(application and application.get("skill_id") == record.id)
        application_mode = self._parse_skill_apply_mode(application.get("mode")) if applied and application else None

        return AuthorSkillProfile(
            skill_id=record.id,
            origin_project_id=record.project_id,
            run_id=record.run_id,
            skill_name=record.skill_name,
            author_name=record.author_name,
            source_ids=self._loads_list(record.source_ids_json),
            stable_rules=self._loads_list(record.stable_rules_json),
            conditional_rules=self._loads_list(record.conditional_rules_json),
            anti_rules=self._loads_list(record.anti_rules_json),
            dialogue_rules=self._loads_list(record.dialogue_rules_json),
            scene_patterns=self._loads_dict(record.scene_patterns_json),
            chapter_hook_patterns=self._loads_list(record.chapter_hook_patterns_json),
            humanness_baseline=self._loads_dict(record.humanness_baseline_json),
            confidence_map=self._loads_dict(record.confidence_map_json),
            status=BenchmarkProfileStatus(record.status),
            created_at=_iso(record.created_at) or "",
            applied=applied,
            application_mode=application_mode,
        )

    def _serialize_source(self, record: BenchmarkSourceRecord) -> BenchmarkSource:
        return BenchmarkSource(
            source_id=record.id,
            project_id=record.project_id,
            corpus_group=record.corpus_group,
            title=record.title,
            author_name=record.author_name,
            file_name=record.file_name,
            sha256=record.sha256,
            char_count=record.char_count,
            chapter_sep=record.chapter_sep,
            source_type=BenchmarkSourceType(record.source_type),
            created_at=_iso(record.created_at) or "",
        )

    def _serialize_snippet(
        self,
        record: BenchmarkSnippetRecord,
        *,
        source_hit_verified: bool = False,
    ) -> BenchmarkSnippet:
        return BenchmarkSnippet(
            snippet_id=record.id,
            profile_id=record.profile_id,
            project_id=record.project_id,
            source_id=record.source_id,
            scene_type=BenchmarkSceneType(record.scene_type),
            chapter=record.chapter,
            offset_start=record.offset_start,
            offset_end=record.offset_end,
            char_count=record.char_count,
            anchor_score=record.anchor_score,
            purity_score=record.purity_score,
            distinctiveness_score=record.distinctiveness_score,
            source_hit_verified=source_hit_verified,
            text=record.text,
        )

    def _build_profile_name(
        self,
        req: BenchmarkJobCreateRequest,
        sources: list[BenchmarkSourceRecord],
        now: datetime,
    ) -> str:
        seed_name = sources[0].title if sources else req.job_type.value
        suffix = now.strftime("%Y%m%d%H%M%S")
        if req.job_type == BenchmarkJobType.AUTHOR_DISTILLATION:
            author = req.author_name or sources[0].author_name or "author"
            return f"{author}-skill-{suffix}"
        return f"{seed_name}-benchmark-{suffix}"

    def _map_run_type(self, job_type: BenchmarkJobType) -> RunType:
        if job_type == BenchmarkJobType.AUTHOR_DISTILLATION:
            return RunType.AUTHOR_DISTILLATION
        return RunType.BENCHMARK_ANALYSIS

    def _map_source_type(self, job_type: BenchmarkJobType) -> BenchmarkSourceType:
        if job_type == BenchmarkJobType.AUTHOR_DISTILLATION:
            return BenchmarkSourceType.AUTHOR_REFERENCE
        return BenchmarkSourceType.PROJECT_REFERENCE

    def _loads_list(self, raw: str) -> list[Any]:
        try:
            value = json.loads(raw or "[]")
        except json.JSONDecodeError:
            return []
        return value if isinstance(value, list) else []

    def _loads_dict(self, raw: str) -> dict[str, Any]:
        try:
            value = json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}

    async def _ensure_benchmark_budget(self, db: AsyncSession, project_id: str) -> None:
        budget = await self._resolve_benchmark_budget(db, project_id)
        used = int(cost_ctrl.summary().get("used", 0))
        if budget <= 0 or used >= budget:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "detail": f"benchmark budget 不足，已跳过本次运行：{used} / {budget}。",
                    "code": "BUDGET_EXCEEDED",
                },
            )

    async def _resolve_benchmark_budget(self, db: AsyncSession, project_id: str) -> int:
        setting_value = await self._repository.get_project_setting(db, project_id, "benchmark_token_budget")
        if isinstance(setting_value, (int, float)):
            return max(int(setting_value), 0)
        return max(int(os.environ.get("BENCHMARK_TOKEN_BUDGET", str(_DEFAULT_BENCHMARK_TOKEN_BUDGET))), 0)

    async def _resolve_benchmark_timeout(self, db: AsyncSession, project_id: str) -> float:
        setting_value = await self._repository.get_project_setting(db, project_id, "benchmark_job_timeout_sec")
        if isinstance(setting_value, (int, float)):
            return max(float(setting_value), 0.1)
        return max(float(os.environ.get("BENCHMARK_JOB_TIMEOUT_SEC", str(_DEFAULT_BENCHMARK_JOB_TIMEOUT_SEC))), 0.1)

    def _verify_snippet_hit(
        self,
        source: BenchmarkSourceRecord | None,
        snippet: BenchmarkSnippetRecord,
    ) -> bool:
        if source is None:
            return False
        if snippet.offset_start < 0 or snippet.offset_end < snippet.offset_start:
            return False
        return source.text_content[snippet.offset_start:snippet.offset_end] == snippet.text

    def _parse_skill_apply_mode(self, raw: Any) -> BenchmarkSkillApplyMode | None:
        if raw is None:
            return None
        try:
            return BenchmarkSkillApplyMode(str(raw))
        except ValueError:
            return None

    async def _get_skill_application(
        self,
        db: AsyncSession,
        project_id: str,
    ) -> dict[str, Any] | None:
        value = await self._repository.get_project_setting(db, project_id, _AUTHOR_SKILL_APPLICATION_KEY)
        return value if isinstance(value, dict) else None

    def _dedupe_sources(
        self,
        sources: list[BenchmarkSourceRecord],
    ) -> list[BenchmarkSourceRecord]:
        seen: set[str] = set()
        ordered: list[BenchmarkSourceRecord] = []
        for item in sources:
            if item.id in seen:
                continue
            seen.add(item.id)
            ordered.append(item)
        return ordered


_benchmark_service: BenchmarkService | None = None


def get_benchmark_service() -> BenchmarkService:
    global _benchmark_service
    if _benchmark_service is None:
        _benchmark_service = BenchmarkService()
    return _benchmark_service