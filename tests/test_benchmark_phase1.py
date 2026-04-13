from __future__ import annotations

import asyncio
import time

from fastapi.testclient import TestClient
import pytest

from narrative_os.core.state import ChapterMeta, StateManager
from narrative_os.core.benchmark_repository import get_benchmark_repository
from narrative_os.infra.database import AsyncSessionLocal, ensure_database_runtime
from narrative_os.interface.api import app
from narrative_os.interface.services.benchmark_service import get_benchmark_service


@pytest.fixture()
def benchmark_runtime_db(tmp_path, monkeypatch):
    db_url = f"sqlite+aiosqlite:///{tmp_path / 'benchmark_phase1.db'}"
    monkeypatch.setenv("NARRATIVE_DB_URL", db_url)
    return db_url


@pytest.fixture()
def client(benchmark_runtime_db):
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def _init_project(client: TestClient, project_id: str) -> None:
    resp = client.post(
        "/projects/init",
        json={
            "project_id": project_id,
            "title": "Benchmark Phase 1",
            "genre": "fantasy",
            "description": "phase1 scaffold test",
        },
    )
    assert resp.status_code == 201


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _create_and_activate_benchmark(client: TestClient, project_id: str) -> dict:
    create_resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "project_benchmark",
            "mode": "multi_work",
            "extract_snippets": True,
            "target_platform": "tomato",
            "sources": [
                {
                    "title": "参考文本 A",
                    "file_name": "a.txt",
                    "text": "第一章，夜雨打在窗沿上，屋内的人没有立刻开口。主角盯着桌上的旧信，先是沉默，然后慢慢抬手，把信纸重新折好，像是在压住即将失控的情绪。",
                },
                {
                    "title": "参考文本 B",
                    "file_name": "b.txt",
                    "text": "第二章，街上的灯火被风吹得摇晃，巡夜人经过时只听见一声极轻的叹息。她没有转身，只把斗篷拢紧，继续沿着石阶往下走，像是已经决定了今晚必须面对的真相。",
                },
            ],
        },
    )
    assert create_resp.status_code == 202
    create_body = create_resp.json()

    activate_resp = client.post(
        f"/projects/{project_id}/benchmark/profile/activate",
        json={"profile_id": create_body["profile"]["profile_id"]},
    )
    assert activate_resp.status_code == 200
    return create_body


def test_create_and_query_project_benchmark_job(client: TestClient):
    project_id = "benchmark-phase1-project"
    _init_project(client, project_id)

    create_body = _create_and_activate_benchmark(client, project_id)
    assert create_body["status"] == "completed"
    assert create_body["profile"]["profile_type"] == "project_benchmark"
    assert create_body["profile"]["status"] == "draft"
    assert create_body["profile"]["stable_traits"]
    assert create_body["profile"]["snippet_count"] > 0
    assert len(create_body["source_ids"]) == 2

    detail_resp = client.get(
        f"/projects/{project_id}/benchmark/jobs/{create_body['run_id']}"
    )
    assert detail_resp.status_code == 200
    detail_body = detail_resp.json()
    assert detail_body["run"]["run_type"] == "benchmark_analysis"
    assert detail_body["run"]["status"] == "completed"
    assert detail_body["profile"]["profile_id"] == create_body["profile"]["profile_id"]
    assert len(detail_body["snippets"]) > 0
    assert [item["title"] for item in detail_body["sources"]] == ["参考文本 A", "参考文本 B"]

    snippets_resp = client.get(f"/projects/{project_id}/benchmark/snippets")
    assert snippets_resp.status_code == 200
    snippets_body = snippets_resp.json()
    assert snippets_body["profile"]["profile_id"] == create_body["profile"]["profile_id"]
    assert len(snippets_body["items"]) > 0

    activated_profile = client.get(f"/projects/{project_id}/benchmark/profile").json()
    assert activated_profile["status"] == "active"

    current_profile_resp = client.get(f"/projects/{project_id}/benchmark/profile")
    assert current_profile_resp.status_code == 200
    assert current_profile_resp.json()["profile_id"] == create_body["profile"]["profile_id"]
    assert current_profile_resp.json()["status"] == "active"


def test_create_author_distillation_job_records_author_run_type(client: TestClient):
    project_id = "benchmark-phase1-author"
    _init_project(client, project_id)

    create_resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "author_distillation",
            "mode": "multi_work",
            "author_name": "测试作者",
            "corpus_group": "author_test_group",
            "sources": [
                {
                    "title": "作者作品 1",
                    "file_name": "work1.txt",
                    "text": "作者作品一正文。雨后的院子还带着泥气，人物没有直接表态，而是先看向远处熄灭的灯，再用一句很轻的话把冲突往前推了一格。院门半开，脚步声被压得很轻，真正的情绪都藏在停顿里。",
                },
                {
                    "title": "作者作品 2",
                    "file_name": "work2.txt",
                    "text": "作者作品二正文。群像场面里，每个人都只说半句话，真正的压力落在停顿和动作上，读者会比角色更早察觉即将到来的翻转。视角始终贴着核心人物的呼吸，不急着解释结论。",
                },
                {
                    "title": "作者作品 3",
                    "file_name": "work3.txt",
                    "text": "作者作品三正文。章末往往不直接收束，而是留下一道尚未说破的缝隙，让人物关系在沉默里继续发酵。下一场冲突的火星通常埋在一句看似平常的对白后面。",
                },
            ],
        },
    )
    assert create_resp.status_code == 202
    create_body = create_resp.json()
    assert create_body["profile"]["profile_type"] == "author_distillation"
    assert create_body["author_skill"]["author_name"] == "测试作者"
    skill_id = create_body["author_skill"]["skill_id"]

    detail_resp = client.get(
        f"/projects/{project_id}/benchmark/jobs/{create_body['run_id']}"
    )
    assert detail_resp.status_code == 200
    detail_body = detail_resp.json()
    assert detail_body["run"]["run_type"] == "author_distillation"
    assert detail_body["profile"]["source_ids"] == create_body["source_ids"]
    assert detail_body["profile"]["stable_traits"]
    assert detail_body["author_skill"]["skill_id"] == skill_id
    assert all(item["source_type"] == "author_reference" for item in detail_body["sources"])

    list_resp = client.get(f"/projects/{project_id}/benchmark/skills")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["items"][0]["skill_id"] == skill_id
    assert list_body["active_skill_id"] is None

    skill_resp = client.get(f"/projects/{project_id}/benchmark/skills/{skill_id}")
    assert skill_resp.status_code == 200
    assert skill_resp.json()["scene_patterns"]

    apply_resp = client.post(
        f"/projects/{project_id}/benchmark/skills/{skill_id}/apply",
        json={"mode": "hybrid"},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["mode"] == "hybrid"

    applied_list_resp = client.get(f"/projects/{project_id}/benchmark/skills")
    assert applied_list_resp.status_code == 200
    applied_list_body = applied_list_resp.json()
    assert applied_list_body["active_skill_id"] == skill_id
    assert applied_list_body["active_mode"] == "hybrid"
    assert applied_list_body["items"][0]["applied"] is True
    assert applied_list_body["items"][0]["application_mode"] == "hybrid"


def test_author_distillation_rejects_mixed_corpus_group(client: TestClient):
    project_id = "benchmark-phase4-invalid-corpus"
    _init_project(client, project_id)

    resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "author_distillation",
            "mode": "multi_work",
            "author_name": "测试作者",
            "corpus_group": "author_group_a",
            "sources": [
                {
                    "title": "作者作品 1",
                    "file_name": "work1.txt",
                    "corpus_group": "author_group_a",
                    "text": "这是一段足够长的文本，用来保证作者蒸馏的最低门槛满足要求，并且保持统一作者与统一语气。人物的动作、停顿、视线与未说出口的话会被反复书写，确保有效字数明显超过最低限制。",
                },
                {
                    "title": "作者作品 2",
                    "file_name": "work2.txt",
                    "corpus_group": "author_group_b",
                    "text": "这也是一段足够长的文本，用来触发 corpus_group 校验失败，因为它来自不同的分组。文本继续展开动作与场景细节，确保请求不会先被最低有效字数门槛拦下。",
                },
                {
                    "title": "作者作品 3",
                    "file_name": "work3.txt",
                    "corpus_group": "author_group_a",
                    "text": "第三段文本继续满足最小长度要求，但因为第二段混入了其他 corpus_group，整个请求应被拒绝。这里继续补充句子长度和段落信息，确保真正命中分组冲突校验。",
                },
            ],
        },
    )

    assert resp.status_code == 422
    assert "corpus_group" in str(resp.json())


def test_writing_context_includes_active_benchmark(client: TestClient):
    project_id = "benchmark-phase3-writing-context"
    _init_project(client, project_id)
    create_body = _create_and_activate_benchmark(client, project_id)

    resp = client.get(f"/projects/{project_id}/writing-context", params={"chapter": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["active_benchmark"]["profile_id"] == create_body["profile"]["profile_id"]
    assert data["active_benchmark"]["profile_name"] == create_body["profile"]["profile_name"]
    assert data["active_benchmark"]["top_rules"]


def test_writing_context_includes_applied_author_skill(client: TestClient):
    project_id = "benchmark-phase4-writing-context"
    _init_project(client, project_id)

    create_resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "author_distillation",
            "mode": "multi_work",
            "author_name": "测试作者",
            "corpus_group": "phase4_author_group",
            "sources": [
                {
                    "title": "作者作品 1",
                    "file_name": "work1.txt",
                    "text": "作者作品一正文。人物总在动作完成之后才补上一句解释，情绪会先落在空白和停顿里。门外雨声不断，真正的决定藏在一句极轻的话后。",
                },
                {
                    "title": "作者作品 2",
                    "file_name": "work2.txt",
                    "text": "作者作品二正文。群像场面里，每个人都只说半句话，叙述会把注意力压到视线与呼吸的变化上。读者通常比角色更早看到即将来的转折。",
                },
                {
                    "title": "作者作品 3",
                    "file_name": "work3.txt",
                    "text": "作者作品三正文。章尾并不急着落锁，而是先留下一点未解决的压力，让下一章的冲突自然接力。真正的钩子往往埋在很平静的收束里。",
                },
            ],
        },
    )
    assert create_resp.status_code == 202
    skill_id = create_resp.json()["author_skill"]["skill_id"]

    apply_resp = client.post(
        f"/projects/{project_id}/benchmark/skills/{skill_id}/apply",
        json={"mode": "strict"},
    )
    assert apply_resp.status_code == 200

    resp = client.get(f"/projects/{project_id}/writing-context", params={"chapter": 1})

    assert resp.status_code == 200
    data = resp.json()
    assert data["active_author_skill"]["profile_id"] == skill_id
    assert data["active_author_skill"]["application_mode"] == "strict"
    assert data["active_author_skill"]["top_rules"]


def test_metrics_history_includes_benchmark_scores(client: TestClient):
    project_id = "benchmark-phase3-metrics"
    _init_project(client, project_id)
    create_body = _create_and_activate_benchmark(client, project_id)

    mgr = StateManager(project_id=project_id)
    state = mgr.load_state()
    state.current_chapter = 1
    state.chapters = [
        ChapterMeta(
            chapter=1,
            summary="主角在夜雨中完成首次试探。",
            quality_score=0.82,
            hook_score=0.74,
            word_count=2140,
        )
    ]
    mgr.save_state()

    async def _seed_score() -> None:
        await ensure_database_runtime()
        async with AsyncSessionLocal() as session:
            score = await get_benchmark_service().score_text(
                session,
                project_id,
                chapter=1,
                text=(
                    "夜雨沿着旧城墙一路流下，沈烬盯着手里的残图，没有急着说出猜测。"
                    "他先把图纸折回袖中，听完巡夜人的脚步，再低声提醒同伴不要回头。"
                    "短暂的停顿之后，真正的决定才被推到台面上。"
                ),
            )
        assert score is not None
        assert score.profile_id == create_body["profile"]["profile_id"]

    _run(_seed_score())

    resp = client.get(f"/projects/{project_id}/metrics/history")

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["benchmark_adherence_score"] > 0
    assert data[0]["benchmark_humanness_score"] > 0


def test_snippets_keep_source_hit_validation(client: TestClient):
    project_id = "benchmark-phase5-snippet-hit"
    _init_project(client, project_id)
    create_body = _create_and_activate_benchmark(client, project_id)

    snippets_resp = client.get(f"/projects/{project_id}/benchmark/snippets")
    assert snippets_resp.status_code == 200
    snippets_body = snippets_resp.json()
    assert snippets_body["items"]
    assert all(item["source_hit_verified"] is True for item in snippets_body["items"])

    async def _verify_offsets() -> None:
        await ensure_database_runtime()
        async with AsyncSessionLocal() as session:
            source_records = await get_benchmark_repository().get_sources_by_ids(
                session,
                project_id,
                create_body["source_ids"],
            )
        source_map = {item.id: item for item in source_records}
        for snippet in snippets_body["items"]:
            source = source_map[snippet["source_id"]]
            assert source.text_content[snippet["offset_start"]:snippet["offset_end"]] == snippet["text"]

    _run(_verify_offsets())


def test_repeated_benchmark_runs_keep_stable_traits(client: TestClient):
    project_id = "benchmark-phase5-repeated-runs"
    _init_project(client, project_id)

    payload = {
        "job_type": "project_benchmark",
        "mode": "multi_work",
        "extract_snippets": True,
        "target_platform": "tomato",
        "sources": [
            {
                "title": "参考文本 A",
                "file_name": "a.txt",
                "text": "第一章，夜雨打在窗沿上，屋内的人没有立刻开口。主角盯着桌上的旧信，先是沉默，然后慢慢抬手，把信纸重新折好，像是在压住即将失控的情绪。",
            },
            {
                "title": "参考文本 B",
                "file_name": "b.txt",
                "text": "第二章，街上的灯火被风吹得摇晃，巡夜人经过时只听见一声极轻的叹息。她没有转身，只把斗篷拢紧，继续沿着石阶往下走，像是已经决定了今晚必须面对的真相。",
            },
        ],
    }

    first = client.post(f"/projects/{project_id}/benchmark/jobs", json=payload)
    second = client.post(f"/projects/{project_id}/benchmark/jobs", json=payload)

    assert first.status_code == 202
    assert second.status_code == 202

    first_names = {item["name"] for item in first.json()["profile"]["stable_traits"]}
    second_names = {item["name"] for item in second.json()["profile"]["stable_traits"]}
    overlap_ratio = len(first_names & second_names) / max(len(first_names | second_names), 1)

    assert overlap_ratio >= 0.85
    assert first.json()["snippet_count"] == second.json()["snippet_count"]


def test_benchmark_budget_guard_skips_job_without_polluting_profile(client: TestClient, monkeypatch):
    project_id = "benchmark-phase5-budget-guard"
    _init_project(client, project_id)
    monkeypatch.setenv("BENCHMARK_TOKEN_BUDGET", "0")

    resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "project_benchmark",
            "mode": "multi_work",
            "extract_snippets": True,
            "sources": [
                {
                    "title": "参考文本 A",
                    "file_name": "a.txt",
                    "text": "夜雨打在窗沿上，人物没有直接开口，而是先通过动作压住情绪，再把真正的决定推到场景后半段。",
                }
            ],
        },
    )

    assert resp.status_code == 409
    assert "budget" in str(resp.json()).lower()

    profile_resp = client.get(f"/projects/{project_id}/benchmark/profile")
    assert profile_resp.status_code == 200
    assert profile_resp.json() is None


def test_benchmark_timeout_is_isolated(client: TestClient, monkeypatch):
    project_id = "benchmark-phase5-timeout"
    _init_project(client, project_id)
    monkeypatch.setenv("BENCHMARK_JOB_TIMEOUT_SEC", "0.01")

    service = get_benchmark_service()
    original_extract = service._extract_snippets

    def _slow_extract(*args, **kwargs):
        time.sleep(0.2)
        return original_extract(*args, **kwargs)

    monkeypatch.setattr(service, "_extract_snippets", _slow_extract)

    resp = client.post(
        f"/projects/{project_id}/benchmark/jobs",
        json={
            "job_type": "project_benchmark",
            "mode": "multi_work",
            "extract_snippets": True,
            "sources": [
                {
                    "title": "参考文本 A",
                    "file_name": "a.txt",
                    "text": "夜雨打在窗沿上，人物没有直接开口，而是先通过动作压住情绪，再把真正的决定推到场景后半段。",
                }
            ],
        },
    )

    assert resp.status_code == 504

    profile_resp = client.get(f"/projects/{project_id}/benchmark/profile")
    assert profile_resp.status_code == 200
    assert profile_resp.json() is None


def test_benchmark_adherence_regression_distinguishes_matching_text(client: TestClient):
    project_id = "benchmark-phase5-adherence"
    _init_project(client, project_id)
    create_body = _create_and_activate_benchmark(client, project_id)

    async def _score_pair() -> tuple[float, float]:
        await ensure_database_runtime()
        async with AsyncSessionLocal() as session:
            matched = await get_benchmark_service().score_text(
                session,
                project_id,
                chapter=1,
                text=(
                        "第一章，夜雨打在窗沿上，屋内的人没有立刻开口。"
                        "主角盯着桌上的旧信，先是沉默，然后慢慢抬手，把信纸重新折好，"
                        "像是在压住即将失控的情绪。"
                ),
            )
            mismatched = await get_benchmark_service().score_text(
                session,
                project_id,
                chapter=2,
                text=(
                        "“冲啊！！冲啊！！冲啊！！”他一边连续大喊，一边把自己的每一个判断、每一层动机、"
                        "每一次担忧都当场解释清楚，完全不给动作和停顿留位置。"
                        "所有信息被挤进同一段密集对白里，没有呼吸，也没有延迟。"
                ),
            )
        assert matched is not None
        assert mismatched is not None
        return matched.adherence_score, mismatched.adherence_score

    matched_score, mismatched_score = _run(_score_pair())
    assert matched_score > mismatched_score
    assert create_body["profile"]["profile_id"]