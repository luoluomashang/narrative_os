"""
core/lorebook.py — Phase 4.1: 世界知识检索层（Lorebook）

三类条目结构：
  LoreEntry    — 世界知识词条（规则/地名/势力/力量/角色公开信息/事件）
  LoreVisibility — 词条可见性策略
  CanonPolicy  — 词条正史策略

Lorebook 检索接口：
  search(query, scope, top_k)  — 全文/标签检索
  search_by_tags(tags)          — 按标签检索
  get_for_scene(location, characters, factions)  — 场景驱动召回

集成点：
  publish_from_sandbox(sandbox) — 从 WorldSandboxData 生成词条
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from narrative_os.core.world_sandbox import WorldSandboxData


# ------------------------------------------------------------------ #
# 枚举                                                                  #
# ------------------------------------------------------------------ #

class LoreEntryType(str, Enum):
    RULE = "rule"                          # 世界规则（物理/魔法/社会规则）
    LOCATION = "location"                  # 地区/地点设定
    FACTION = "faction"                    # 势力/组织设定
    POWER = "power"                        # 力量体系/技能
    CHARACTER_PUBLIC = "character_public"  # 角色公开信息
    EVENT = "event"                        # 历史事件


class CanonPolicy(str, Enum):
    IMMUTABLE = "immutable"         # 不可更改的世界基础事实
    REVEAL_AFTER = "reveal_after"   # 到特定章节才公开
    AUTHOR_ONLY = "author_only"     # 仅作者可见（伏笔设定）
    TRPG_VISIBLE = "trpg_visible"   # 互动模式中 DM 可用


# ------------------------------------------------------------------ #
# 数据模型                                                              #
# ------------------------------------------------------------------ #

class LoreVisibility(BaseModel):
    """词条可见性策略。"""
    author_visible: bool = True
    dm_visible: bool = True
    player_visible: bool = False


class LoreEntry(BaseModel):
    """世界知识词条。"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    entry_type: LoreEntryType
    summary: str = ""          # ≤100字摘要，注入用
    body: str = ""             # 完整内容
    tags: list[str] = Field(default_factory=list)
    trigger_keywords: list[str] = Field(default_factory=list)
    # 遇到这些词时自动注入
    visibility: LoreVisibility = Field(default_factory=LoreVisibility)
    canon_policy: CanonPolicy = CanonPolicy.IMMUTABLE
    chapter_reveal: int = 0    # REVEAL_AFTER 策略时的公开章节号

    model_config = {"frozen": False}


# ------------------------------------------------------------------ #
# Lorebook                                                              #
# ------------------------------------------------------------------ #

class Lorebook:
    """
    世界知识检索层。

    用法：
        lb = Lorebook()
        lb.add(entry)
        results = lb.get_for_scene(location="云霄峰", characters=["林枫"], factions=["玄剑宗"])
    """

    def __init__(self) -> None:
        self._entries: dict[str, LoreEntry] = {}   # id → LoreEntry

    # ---------------------------------------------------------------- #
    # CRUD                                                              #
    # ---------------------------------------------------------------- #

    def add(self, entry: LoreEntry) -> LoreEntry:
        """添加词条。若 id 已存在则覆盖。"""
        self._entries[entry.id] = entry
        return entry

    def get(self, entry_id: str) -> LoreEntry | None:
        return self._entries.get(entry_id)

    def remove(self, entry_id: str) -> bool:
        if entry_id in self._entries:
            del self._entries[entry_id]
            return True
        return False

    def all_entries(self) -> list[LoreEntry]:
        return list(self._entries.values())

    # ---------------------------------------------------------------- #
    # 检索接口                                                           #
    # ---------------------------------------------------------------- #

    def search(
        self,
        query: str,
        scope: str = "all",
        top_k: int = 5,
    ) -> list[LoreEntry]:
        """
        全文检索：在 title / summary / body / tags / trigger_keywords 中搜索 query。

        scope: "all" | entry_type value
        """
        query_lower = query.lower()
        results: list[LoreEntry] = []

        for entry in self._entries.values():
            # 类型过滤
            if scope != "all" and entry.entry_type.value != scope:
                continue

            # 关键词匹配
            searchable = " ".join([
                entry.title,
                entry.summary,
                entry.body[:200],
                " ".join(entry.tags),
                " ".join(entry.trigger_keywords),
            ]).lower()

            if any(kw in searchable for kw in query_lower.split()):
                results.append(entry)

        # 按 summary 长度优先（内容越丰富排越前）
        results.sort(key=lambda e: len(e.summary), reverse=True)
        return results[:top_k]

    def search_by_tags(self, tags: list[str]) -> list[LoreEntry]:
        """按标签检索：词条拥有任一 tag 即返回。"""
        tag_set = {t.lower() for t in tags}
        return [
            e for e in self._entries.values()
            if any(t.lower() in tag_set for t in e.tags)
        ]

    def get_for_scene(
        self,
        location: str = "",
        characters: list[str] | None = None,
        factions: list[str] | None = None,
    ) -> list[LoreEntry]:
        """
        场景驱动召回：根据当前地点/在场角色/相关势力自动召回相关词条。
        用于 NarrativeCompiler Gate10 注入。
        """
        characters = characters or []
        factions = factions or []

        trigger_corpus = set()
        trigger_corpus.update(location.lower().split())
        for c in characters:
            trigger_corpus.update(c.lower().split())
        for f in factions:
            trigger_corpus.update(f.lower().split())

        matched: list[LoreEntry] = []
        for entry in self._entries.values():
            entry_corpus = set()
            entry_corpus.update(entry.title.lower().split())
            entry_corpus.update(t.lower() for t in entry.trigger_keywords)
            entry_corpus.update(t.lower() for t in entry.tags)

            # Substring match: trigger token 与 entry keyword 互为子串即命中
            matched_entry = False
            for trigger_token in trigger_corpus:
                for entry_token in entry_corpus:
                    if trigger_token in entry_token or entry_token in trigger_token:
                        matched_entry = True
                        break
                if matched_entry:
                    break
            if matched_entry:
                matched.append(entry)

        # 按类型优先级排序：RULE > LOCATION > FACTION > POWER > EVENT > CHARACTER_PUBLIC
        _priority = {
            LoreEntryType.RULE: 0,
            LoreEntryType.LOCATION: 1,
            LoreEntryType.FACTION: 2,
            LoreEntryType.POWER: 3,
            LoreEntryType.EVENT: 4,
            LoreEntryType.CHARACTER_PUBLIC: 5,
        }
        matched.sort(key=lambda e: _priority.get(e.entry_type, 9))
        return matched

    # ---------------------------------------------------------------- #
    # 从沙盘发布                                                         #
    # ---------------------------------------------------------------- #

    def publish_from_sandbox(self, sandbox: "WorldSandboxData") -> int:
        """
        从 WorldSandboxData 批量生成 LoreEntry。
        返回新生成的词条数量。

        当前提取策略：
          - world_rules      → LoreEntryType.RULE
          - regions          → LoreEntryType.LOCATION
          - factions         → LoreEntryType.FACTION
          - power_systems    → LoreEntryType.POWER
          - timeline_events  → LoreEntryType.EVENT
        """
        count = 0

        # 世界规则提取
        for i, rule in enumerate(sandbox.world_rules):
            entry = LoreEntry(
                title=f"世界规则_{i + 1}",
                entry_type=LoreEntryType.RULE,
                summary=rule[:100],
                body=rule,
                tags=["规则", "世界法则"],
                trigger_keywords=_extract_keywords(rule),
            )
            self.add(entry)
            count += 1

        # 地区/地点提取
        for region in sandbox.regions:
            entry = LoreEntry(
                title=region.name,
                entry_type=LoreEntryType.LOCATION,
                summary=region.description[:100] if hasattr(region, "description") and region.description else region.name,
                body=region.description if hasattr(region, "description") else "",
                tags=["地区", region.name],
                trigger_keywords=[region.name] + (
                    region.sub_regions if hasattr(region, "sub_regions") else []
                ),
            )
            self.add(entry)
            count += 1

        # 势力/组织提取
        for faction in sandbox.factions:
            entry = LoreEntry(
                title=faction.name,
                entry_type=LoreEntryType.FACTION,
                summary=faction.description[:100] if hasattr(faction, "description") and faction.description else faction.name,
                body=faction.description if hasattr(faction, "description") else "",
                tags=["势力", faction.name],
                trigger_keywords=[faction.name],
            )
            self.add(entry)
            count += 1

        # 力量体系提取
        for ps in sandbox.power_systems:
            level_names = [lv.name for lv in ps.levels] if ps.levels else []
            entry = LoreEntry(
                title=ps.name,
                entry_type=LoreEntryType.POWER,
                summary=f"{ps.name}：{'→'.join(level_names[:5])}{'...' if len(level_names) > 5 else ''}",
                body=f"境界：{', '.join(level_names)}\n规则：{'; '.join(ps.rules[:3])}",
                tags=["力量体系", ps.name],
                trigger_keywords=[ps.name] + level_names[:3],
            )
            self.add(entry)
            count += 1

        # 时间轴事件提取
        for event in sandbox.timeline_events:
            entry = LoreEntry(
                title=event.title if hasattr(event, "title") else str(event),
                entry_type=LoreEntryType.EVENT,
                summary=(event.description[:100] if hasattr(event, "description") and event.description else ""),
                body=event.description if hasattr(event, "description") else "",
                tags=["历史事件"],
                trigger_keywords=_extract_keywords(
                    event.title if hasattr(event, "title") else ""
                ),
            )
            self.add(entry)
            count += 1

        return count

    # ---------------------------------------------------------------- #
    # 序列化                                                             #
    # ---------------------------------------------------------------- #

    def to_dict(self) -> dict[str, Any]:
        return {eid: e.model_dump() for eid, e in self._entries.items()}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Lorebook":
        lb = cls()
        for eid, edata in data.items():
            lb._entries[eid] = LoreEntry.model_validate(edata)
        return lb


# ------------------------------------------------------------------ #
# 内部工具                                                              #
# ------------------------------------------------------------------ #

def _extract_keywords(text: str) -> list[str]:
    """从文本提取单字/词关键词（简单实现：按标点和空格分割取≥2字片段）。"""
    import re
    tokens = re.split(r"[，。、；：！？\s,;:!?/]+", text)
    return [t.strip() for t in tokens if len(t.strip()) >= 2]
