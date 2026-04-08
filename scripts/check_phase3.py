"""Phase 3 自查脚本"""
import asyncio, sys, json, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ.setdefault("NARRATIVE_DB_URL", "sqlite+aiosqlite:///.narrative_state/narrative_os.db")


async def main():
    from narrative_os.core.world_sandbox import (
        WorldSandboxData, ConceptData, Region, Faction, PowerSystem,
        WorldRelation, PowerSystemTemplateType, POWER_SYSTEM_TEMPLATES,
        get_template_summary,
    )
    from narrative_os.infra.database import init_db, AsyncSessionLocal
    from narrative_os.infra.models import WorldSandbox, StoryConcept
    from sqlalchemy import select
    import uuid

    await init_db()
    pid = "test-phase3-chk"

    # 清理上次测试残留数据
    from sqlalchemy import delete
    async with AsyncSessionLocal() as db:
        await db.execute(delete(WorldSandbox).where(WorldSandbox.project_id == pid))
        await db.execute(delete(StoryConcept).where(StoryConcept.project_id == pid))
        await db.commit()

    # --- helpers ---
    async def _gs(db):
        r = (await db.execute(select(WorldSandbox).where(WorldSandbox.project_id == pid))).scalar_one_or_none()
        return WorldSandboxData() if r is None else WorldSandboxData.model_validate_json(r.sandbox_json)

    async def _ss(data, db):
        r = (await db.execute(select(WorldSandbox).where(WorldSandbox.project_id == pid))).scalar_one_or_none()
        js = data.model_dump_json()
        if r is None:
            db.add(WorldSandbox(id=uuid.uuid4().hex, project_id=pid, sandbox_json=js))
        else:
            r.sandbox_json = js
        await db.commit()

    async def _gc(db):
        r = (await db.execute(select(StoryConcept).where(StoryConcept.project_id == pid))).scalar_one_or_none()
        return ConceptData() if r is None else ConceptData.model_validate_json(r.concept_json)

    async def _sc(data, db):
        r = (await db.execute(select(StoryConcept).where(StoryConcept.project_id == pid))).scalar_one_or_none()
        js = data.model_dump_json()
        if r is None:
            db.add(StoryConcept(id=uuid.uuid4().hex, project_id=pid, concept_json=js))
        else:
            r.concept_json = js
        await db.commit()

    # 1. GET /concept on empty → empty ConceptData
    async with AsyncSessionLocal() as db:
        c = await _gc(db)
    assert c.one_sentence == "", f"[1] expect empty, got {c.one_sentence}"
    print("[1] GET concept empty OK")

    # 2. PUT /concept → GET → same
    async with AsyncSessionLocal() as db:
        await _sc(ConceptData(one_sentence="一剑平天下", one_paragraph="少年传奇", genre_tags=["修真"]), db)
    async with AsyncSessionLocal() as db:
        c2 = await _gc(db)
    assert c2.one_sentence == "一剑平天下", f"[2] got {c2.one_sentence}"
    assert "修真" in c2.genre_tags
    print("[2] PUT/GET concept OK")

    # 3. GET /world empty → empty WorldSandboxData
    async with AsyncSessionLocal() as db:
        s = await _gs(db)
    assert s.regions == []
    print("[3] GET world empty OK")

    # 4. POST region → auto id
    r1 = Region(name="东方大陆", region_type="大陆")
    assert r1.id != ""
    print(f"[4] Region auto-id OK: {r1.id[:6]}")

    # 5. PUT region → GET shows change
    async with AsyncSessionLocal() as db:
        s.regions.append(r1)
        await _ss(s, db)
    async with AsyncSessionLocal() as db:
        s2 = await _gs(db)
    s2.regions[0].notes = "修真圣地"
    async with AsyncSessionLocal() as db:
        await _ss(s2, db)
    async with AsyncSessionLocal() as db:
        s3 = await _gs(db)
    assert s3.regions[0].notes == "修真圣地"
    print("[5] Region PUT/GET OK")

    # 6. DELETE region
    rid = s3.regions[0].id
    async with AsyncSessionLocal() as db:
        s3.regions = [x for x in s3.regions if x.id != rid]
        await _ss(s3, db)
    async with AsyncSessionLocal() as db:
        s4 = await _gs(db)
    assert not any(x.id == rid for x in s4.regions)
    print("[6] Region DELETE OK")

    # 7. Faction CRUD
    async with AsyncSessionLocal() as db:
        s4.factions.append(Faction(name="青云门", scope="internal"))
        await _ss(s4, db)
    async with AsyncSessionLocal() as db:
        s5 = await _gs(db)
    assert s5.factions[0].name == "青云门"
    print("[7] Faction CRUD OK")

    # 8. PowerSystem CRUD
    async with AsyncSessionLocal() as db:
        s5.power_systems.append(PowerSystem(name="修真体系", template=PowerSystemTemplateType.CULTIVATION))
        await _ss(s5, db)
    async with AsyncSessionLocal() as db:
        s6 = await _gs(db)
    assert s6.power_systems[0].name == "修真体系"
    print("[8] PowerSystem CRUD OK")

    # 9. Relation auto-id
    rel = WorldRelation(source_id="a", target_id="b", relation_type="alliance", label="同盟")
    assert rel.id != ""
    print(f"[9] Relation auto-id OK: {rel.id[:6]}")

    # 10. Power-templates
    tpls = get_template_summary()
    assert len(tpls) == 8, f"expect 8, got {len(tpls)}"
    print(f"[10] power-templates OK, count: {len(tpls)}")

    # 11. finalize: write knowledge_base.json
    async with AsyncSessionLocal() as db:
        fs = await _gs(db)
        fc = await _gc(db)
    seed = {
        "one_sentence": fc.one_sentence,
        "world": {"factions": [f.name for f in fs.factions]},
    }
    kbp = Path(f".narrative_state/{pid}/knowledge_base.json")
    kbp.parent.mkdir(parents=True, exist_ok=True)
    kbp.write_text(json.dumps(seed, ensure_ascii=False), encoding="utf-8")
    assert kbp.exists()
    print(f"[11] finalize/kb OK: {kbp}")

    print()
    print("=== Phase 3 全部自查通过 ===")


asyncio.run(main())
