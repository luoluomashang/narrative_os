"""
tests/test_lorebook.py — Phase 4 自查项

涵盖：
  4.A Lorebook 检索测试
  4.B Lorebook 从沙盘发布测试
"""

from __future__ import annotations

import pytest

from narrative_os.core.lorebook import (
    CanonPolicy,
    LoreEntry,
    LoreEntryType,
    LoreVisibility,
    Lorebook,
)


# ================================================================== #
# 辅助工厂                                                              #
# ================================================================== #

def _make_lorebook_with_entries() -> Lorebook:
    lb = Lorebook()
    lb.add(LoreEntry(
        title="云霄峰禁令",
        entry_type=LoreEntryType.RULE,
        summary="云霄峰核心区域禁止外人进入，违者逐出师门",
        body="完整禁令文本……",
        tags=["规则", "云霄峰"],
        trigger_keywords=["云霄峰", "禁令", "核心区域"],
    ))
    lb.add(LoreEntry(
        title="玄剑宗",
        entry_type=LoreEntryType.FACTION,
        summary="名震大陆的正道宗门，以剑道著称",
        body="玄剑宗详细信息……",
        tags=["势力", "正道"],
        trigger_keywords=["玄剑宗", "宗门"],
    ))
    lb.add(LoreEntry(
        title="炼气境",
        entry_type=LoreEntryType.POWER,
        summary="修仙第一境，修者凝聚灵气入体",
        body="炼气境界详细说明……",
        tags=["力量体系", "修仙"],
        trigger_keywords=["炼气", "灵气", "修仙"],
    ))
    lb.add(LoreEntry(
        title="古剑传说",
        entry_type=LoreEntryType.EVENT,
        summary="三千年前古剑封印世界之战的历史事件",
        body="古剑传说完整记载……",
        tags=["历史", "古剑"],
        trigger_keywords=["古剑", "封印", "三千年"],
    ))
    lb.add(LoreEntry(
        title="林枫公开信息",
        entry_type=LoreEntryType.CHARACTER_PUBLIC,
        summary="玄剑宗天才弟子，天赋异禀，性格刚直",
        body="林枫角色公开资料……",
        tags=["角色", "玄剑宗"],
        trigger_keywords=["林枫"],
        visibility=LoreVisibility(author_visible=True, dm_visible=True, player_visible=True),
    ))
    return lb


# ================================================================== #
# 4.A Lorebook 检索测试                                                 #
# ================================================================== #

class TestLorebookSearch:

    def test_add_and_get(self):
        lb = Lorebook()
        entry = LoreEntry(
            title="测试词条",
            entry_type=LoreEntryType.RULE,
            summary="这是一条测试规则",
            tags=["测试"],
            trigger_keywords=["测试"],
        )
        added = lb.add(entry)
        fetched = lb.get(entry.id)
        assert fetched is not None
        assert fetched.title == "测试词条"

    def test_remove_entry(self):
        lb = Lorebook()
        entry = LoreEntry(
            title="可删除词条",
            entry_type=LoreEntryType.RULE,
        )
        lb.add(entry)
        result = lb.remove(entry.id)
        assert result is True
        assert lb.get(entry.id) is None

    def test_remove_nonexistent_returns_false(self):
        lb = Lorebook()
        assert lb.remove("nonexistent-id") is False

    def test_search_by_keyword(self):
        lb = _make_lorebook_with_entries()
        results = lb.search("云霄峰", top_k=10)
        titles = [e.title for e in results]
        assert "云霄峰禁令" in titles

    def test_search_irrelevant_not_returned(self):
        lb = _make_lorebook_with_entries()
        # 搜索与所有词条完全无关的词
        results = lb.search("海底捞火锅", top_k=10)
        titles = [e.title for e in results]
        # 应该不包含已有词条（无关词）
        assert "玄剑宗" not in titles
        assert "云霄峰禁令" not in titles

    def test_search_by_tags(self):
        lb = _make_lorebook_with_entries()
        results = lb.search_by_tags(["势力"])
        titles = [e.title for e in results]
        assert "玄剑宗" in titles
        # 非"势力"标签的不应出现
        assert "炼气境" not in titles

    def test_search_multiple_tags(self):
        lb = _make_lorebook_with_entries()
        results = lb.search_by_tags(["力量体系", "历史"])
        titles = {e.title for e in results}
        assert "炼气境" in titles
        assert "古剑传说" in titles

    def test_get_for_scene_location(self):
        lb = _make_lorebook_with_entries()
        results = lb.get_for_scene(location="云霄峰")
        titles = [e.title for e in results]
        assert "云霄峰禁令" in titles

    def test_get_for_scene_character(self):
        lb = _make_lorebook_with_entries()
        results = lb.get_for_scene(characters=["林枫"])
        titles = [e.title for e in results]
        assert "林枫公开信息" in titles

    def test_get_for_scene_faction(self):
        lb = _make_lorebook_with_entries()
        results = lb.get_for_scene(factions=["玄剑宗"])
        titles = [e.title for e in results]
        assert "玄剑宗" in titles

    def test_get_for_scene_unrelated_not_returned(self):
        """与场景无关的词条不应出现。"""
        lb = _make_lorebook_with_entries()
        results = lb.get_for_scene(
            location="海底世界",
            characters=["海龙王"],
            factions=["深海帝国"],
        )
        # 没有任何词条匹配这些关键词
        titles = [e.title for e in results]
        assert "云霄峰禁令" not in titles
        assert "玄剑宗" not in titles

    def test_get_for_scene_multiple_triggers(self):
        lb = _make_lorebook_with_entries()
        results = lb.get_for_scene(
            location="古剑封印地",
            characters=["林枫"],
            factions=["玄剑宗"],
        )
        titles = {e.title for e in results}
        assert "林枫公开信息" in titles
        assert "玄剑宗" in titles

    def test_get_for_scene_priority_order(self):
        """get_for_scene 应按类型优先级排序（RULE > LOCATION > FACTION > ...）。"""
        lb = _make_lorebook_with_entries()
        # 添加一个 LOCATION 词条
        lb.add(LoreEntry(
            title="云霄峰位置",
            entry_type=LoreEntryType.LOCATION,
            summary="云霄峰是玄剑宗的圣山",
            tags=["地点"],
            trigger_keywords=["云霄峰"],
        ))
        results = lb.get_for_scene(location="云霄峰")
        # RULE 应在 LOCATION 之前
        types = [e.entry_type for e in results]
        if LoreEntryType.RULE in types and LoreEntryType.LOCATION in types:
            assert types.index(LoreEntryType.RULE) < types.index(LoreEntryType.LOCATION)

    def test_lorebook_serialization(self):
        lb = _make_lorebook_with_entries()
        data = lb.to_dict()
        lb2 = Lorebook.from_dict(data)
        assert len(lb2.all_entries()) == len(lb.all_entries())

    def test_entry_model_fields(self):
        entry = LoreEntry(
            title="测试",
            entry_type=LoreEntryType.FACTION,
            summary="摘要",
            tags=["tag1"],
            trigger_keywords=["kw1"],
            visibility=LoreVisibility(player_visible=True),
            canon_policy=CanonPolicy.AUTHOR_ONLY,
        )
        assert entry.visibility.player_visible is True
        assert entry.canon_policy == CanonPolicy.AUTHOR_ONLY
        assert "tag1" in entry.tags


# ================================================================== #
# 4.B Lorebook 从沙盘发布                                               #
# ================================================================== #

class TestLorebookPublishFromSandbox:

    def _make_sandbox(self):
        from narrative_os.core.world_sandbox import (
            WorldSandboxData,
            Region,
            Faction,
        )
        from narrative_os.core.world import PowerSystem, PowerLevel
        from narrative_os.core.world_sandbox import WorldType

        sandbox = WorldSandboxData(
            world_name="玄天大陆",
            world_type=WorldType.CONTINENTAL,
            world_description="修仙世界",
            world_rules=["灵气是修炼之本", "杀人不可逃天罚", "境界不可逆转"],
            regions=[
                Region(name="北域", description="寒冷贫瘠的北方大地"),
                Region(name="中州", description="天下正道的中心"),
            ],
            factions=[
                Faction(name="玄剑宗", description="正道第一大宗"),
                Faction(name="血魔教", description="邪道最强组织"),
            ],
        )

        # power_systems uses WorldSandbox's PowerSystem (with levels)
        from narrative_os.core.world_sandbox import PowerSystem as SPowerSystem
        sandbox.power_systems = [
            SPowerSystem(
                name="修仙体系",
                levels=[],
                rules=["灵气耗尽则死"],
            )
        ]
        return sandbox

    def test_publish_generates_entries(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        count = lb.publish_from_sandbox(sandbox)
        assert count > 0
        assert len(lb.all_entries()) == count

    def test_publish_creates_rule_entries(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        rule_entries = [e for e in lb.all_entries() if e.entry_type == LoreEntryType.RULE]
        assert len(rule_entries) == len(sandbox.world_rules)

    def test_publish_creates_location_entries(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        location_entries = [e for e in lb.all_entries() if e.entry_type == LoreEntryType.LOCATION]
        assert len(location_entries) == len(sandbox.regions)

    def test_publish_creates_faction_entries(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        faction_entries = [e for e in lb.all_entries() if e.entry_type == LoreEntryType.FACTION]
        assert len(faction_entries) == len(sandbox.factions)
        faction_names = {e.title for e in faction_entries}
        assert "玄剑宗" in faction_names
        assert "血魔教" in faction_names

    def test_publish_creates_power_entries(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        power_entries = [e for e in lb.all_entries() if e.entry_type == LoreEntryType.POWER]
        assert len(power_entries) == len(sandbox.power_systems)

    def test_published_entries_searchable(self):
        """发布后的词条应可以通过 search 检索到。"""
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        results = lb.search("玄剑宗", top_k=10)
        titles = [e.title for e in results]
        assert "玄剑宗" in titles

    def test_published_entries_have_trigger_keywords(self):
        lb = Lorebook()
        sandbox = self._make_sandbox()
        lb.publish_from_sandbox(sandbox)
        faction_entries = [e for e in lb.all_entries() if e.entry_type == LoreEntryType.FACTION]
        for entry in faction_entries:
            assert len(entry.trigger_keywords) > 0
