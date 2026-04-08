"""
世界观沙盘数据模型
=================
为可视化沙盘编辑器提供全部枚举类型、Pydantic 数据模型及内置力量体系模板字典。
本模块不依赖现有 world_builder.py，独立存在，不修改旧模型。
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# 枚举类型
# ---------------------------------------------------------------------------

class WorldType(str, Enum):
    CONTINENTAL = "continental"    # 大陆流
    PLANAR = "planar"              # 位面/世界流
    INTERSTELLAR = "interstellar"  # 星际/宇宙流
    MULTI_LAYER = "multi_layer"    # 多层世界


class AlignmentType(str, Enum):
    LAWFUL_GOOD = "lawful_good"          # 秩序善良
    NEUTRAL_GOOD = "neutral_good"        # 中立善良
    CHAOTIC_GOOD = "chaotic_good"        # 混沌善良
    LAWFUL_NEUTRAL = "lawful_neutral"    # 秩序中立
    TRUE_NEUTRAL = "true_neutral"        # 绝对中立
    CHAOTIC_NEUTRAL = "chaotic_neutral"  # 混沌中立
    LAWFUL_EVIL = "lawful_evil"          # 秩序邪恶
    NEUTRAL_EVIL = "neutral_evil"        # 中立邪恶
    CHAOTIC_EVIL = "chaotic_evil"        # 混沌邪恶
    TRANSCENDENT = "transcendent"        # 超越阵营


class FactionScope(str, Enum):
    INTERNAL = "internal"  # 世界内势力
    EXTERNAL = "external"  # 域外势力


class PowerSystemTemplateType(str, Enum):
    CULTIVATION = "cultivation"  # 修真
    SYSTEM = "system"            # 系统
    MAGIC = "magic"              # 魔法
    POWER = "power"              # 异能
    BATTLE_QI = "battle_qi"     # 斗气
    BLOODLINE = "bloodline"     # 血统
    CLASS = "class_"             # 职业（避免与 Python 关键字冲突）
    KNIGHT = "knight"           # 骑士
    CUSTOM = "custom"           # 自定义


# ---------------------------------------------------------------------------
# Pydantic 数据模型
# ---------------------------------------------------------------------------

class RegionGeography(BaseModel):
    """地区地理特征"""
    terrain: str = ""
    climate: str = ""
    special_features: list[str] = Field(default_factory=list)
    landmarks: list[str] = Field(default_factory=list)


class RegionRace(BaseModel):
    """地区种族信息"""
    primary_race: str = ""
    secondary_races: list[str] = Field(default_factory=list)
    is_mixed: bool = False
    race_notes: str = ""


class RegionCivilization(BaseModel):
    """地区文明信仰"""
    name: str = ""
    belief_system: str = ""
    culture_tags: list[str] = Field(default_factory=list)
    govt_type: str = ""


class RegionPowerAccess(BaseModel):
    """地区力量体系接入方式"""
    inherits_global: bool = True          # True=继承全局体系；False=使用专属体系
    custom_system_id: Optional[str] = None  # 当 inherits_global=False 时使用
    power_notes: str = ""


class Region(BaseModel):
    """地区节点（对应 Vue-Flow node）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    region_type: str = ""          # 如：城市、荒野、禁地、海域、宇宙站
    x: float = 0.0               # Vue-Flow 画布坐标
    y: float = 0.0
    geography: RegionGeography = Field(default_factory=RegionGeography)
    race: RegionRace = Field(default_factory=RegionRace)
    civilization: RegionCivilization = Field(default_factory=RegionCivilization)
    power_access: RegionPowerAccess = Field(default_factory=RegionPowerAccess)
    faction_ids: list[str] = Field(default_factory=list)  # 该地区所属势力 id 列表
    alignment: AlignmentType = AlignmentType.TRUE_NEUTRAL
    tags: list[str] = Field(default_factory=list)
    notes: str = ""


class Faction(BaseModel):
    """势力（可为世界内或域外）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    scope: FactionScope = FactionScope.INTERNAL
    description: str = ""
    territory_region_ids: list[str] = Field(default_factory=list)
    alignment: AlignmentType = AlignmentType.TRUE_NEUTRAL
    relation_map: dict[str, float] = Field(default_factory=dict)  # faction_id -> -1.0(盟友)~+1.0(敌对)
    power_system_id: Optional[str] = None
    notes: str = ""


class PowerLevel(BaseModel):
    """力量体系的单个境界/等级"""
    name: str
    description: str = ""
    requirements: str = ""


class PowerSystem(BaseModel):
    """全局力量体系"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    template: PowerSystemTemplateType = PowerSystemTemplateType.CUSTOM
    levels: list[PowerLevel] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    notes: str = ""


class WorldRelation(BaseModel):
    """地区/势力之间的关系（对应 Vue-Flow edge）"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source_id: str    # Region.id 或 Faction.id
    target_id: str
    relation_type: str = "connection"  # 如：贸易、战争、联盟、附属、封锁、传送
    label: str = ""
    description: str = ""


class WorldSandboxData(BaseModel):
    """世界观沙盘完整数据（存储于 world_sandboxes 表的 sandbox_json 字段）"""
    world_name: str = ""
    world_type: WorldType = WorldType.CONTINENTAL
    world_description: str = ""
    regions: list[Region] = Field(default_factory=list)
    factions: list[Faction] = Field(default_factory=list)
    power_systems: list[PowerSystem] = Field(default_factory=list)
    world_rules: list[str] = Field(default_factory=list)  # 绝对规则/硬约束
    relations: list[WorldRelation] = Field(default_factory=list)
    canvas_viewport: dict[str, Any] = Field(default_factory=dict)  # 保存 Vue-Flow 视口位置


class ConceptData(BaseModel):
    """故事概念数据（存储于 story_concepts 表的 concept_json 字段）"""
    one_sentence: str = ""
    one_paragraph: str = ""
    genre_tags: list[str] = Field(default_factory=list)
    world_type: WorldType = WorldType.CONTINENTAL  # 与沙盘 world_type 保持同步


# ---------------------------------------------------------------------------
# 内置力量体系模板字典（8套标准模板）
# ---------------------------------------------------------------------------

POWER_SYSTEM_TEMPLATES: dict[PowerSystemTemplateType, PowerSystem] = {
    PowerSystemTemplateType.CULTIVATION: PowerSystem(
        name="修真体系",
        template=PowerSystemTemplateType.CULTIVATION,
        levels=[
            PowerLevel(name="炼气期", description="修炼基础灵气，打通经脉", requirements="资质达到灵根"),
            PowerLevel(name="筑基期", description="构建灵台，稳固修为根基", requirements="炼气圆满，服用筑基丹"),
            PowerLevel(name="金丹期", description="凝结金丹，突破凡人之躯", requirements="筑基圆满，天地元气充沛"),
            PowerLevel(name="元婴期", description="孕育元婴，神识大幅提升", requirements="金丹期三百年以上"),
            PowerLevel(name="化神期", description="神识化阶，初窥大道", requirements="元婴成熟，与道合一契机"),
            PowerLevel(name="炼虚期", description="虚实相合，掌控空间之力", requirements="悟透虚实之道"),
            PowerLevel(name="合体期", description="与天地融合，道法自然", requirements="法力与自然同频共振"),
            PowerLevel(name="大乘期", description="超凡入圣，渡劫仙途", requirements="天劫渡越，踏上飞升之路"),
        ],
        rules=["灵气是修炼根本", "境界不可跨越，必须逐级突破", "渡劫失败则陨落", "杀孽过重影响修炼"],
        resources=["灵石", "丹药", "法宝", "灵泉", "秘籍"],
    ),

    PowerSystemTemplateType.SYSTEM: PowerSystem(
        name="系统体系",
        template=PowerSystemTemplateType.SYSTEM,
        levels=[
            PowerLevel(name="F级", description="普通人类水平，无特殊能力"),
            PowerLevel(name="E级", description="超越普通人，具备基础战力", requirements="系统认证通过"),
            PowerLevel(name="D级", description="可以应对一般威胁", requirements="完成系统晋级任务"),
            PowerLevel(name="C级", description="出类拔萃，地区级强者"),
            PowerLevel(name="B级", description="国家级威胁等级"),
            PowerLevel(name="A级", description="大陆级强者，屈指可数"),
            PowerLevel(name="S级", description="世界顶尖存在，凤毛麟角"),
            PowerLevel(name="SS级", description="超越人知，接近神话级别"),
        ],
        rules=["等级由系统评定，不可伪造", "等级差距过大时战斗力碾压", "系统奖励随任务完成自动发放"],
        resources=["积分", "技能书", "属性点", "装备", "特殊道具"],
    ),

    PowerSystemTemplateType.MAGIC: PowerSystem(
        name="魔法体系",
        template=PowerSystemTemplateType.MAGIC,
        levels=[
            PowerLevel(name="学徒", description="初学者，掌握基础魔法理论", requirements="通过魔法学院入学测试"),
            PowerLevel(name="法师", description="可施展一至二级法术", requirements="学徒修习两年以上"),
            PowerLevel(name="大法师", description="掌握多系魔法，可独立战斗"),
            PowerLevel(name="法爷", description="领域法术，影响战场走势"),
            PowerLevel(name="大法爷", description="魔法天赋显现，可创造新术式"),
            PowerLevel(name="法王", description="国王级守护力量，各国争相礼遇"),
            PowerLevel(name="法帝", description="改变地形的毁灭级法术"),
            PowerLevel(name="法神", description="接近神明，法力无边，寿与天齐"),
        ],
        rules=["魔法需要魔力支撑，耗尽则虚弱", "部分魔法有元素属性克制关系", "禁咒施展需要多人协助"],
        resources=["魔力水晶", "法典", "魔法材料", "魔力药剂", "魔法阵"],
    ),

    PowerSystemTemplateType.BATTLE_QI: PowerSystem(
        name="斗气体系",
        template=PowerSystemTemplateType.BATTLE_QI,
        levels=[
            PowerLevel(name="斗者", description="初入修炼，凝聚斗气", requirements="天赋觉醒，开始修炼"),
            PowerLevel(name="斗师", description="斗气外放，可凝形为刃"),
            PowerLevel(name="大斗师", description="斗气浑厚，外放半米"),
            PowerLevel(name="斗灵", description="灵府开辟，斗气质变"),
            PowerLevel(name="斗王", description="凝翼飞行，三十里之内称王"),
            PowerLevel(name="斗皇", description="斗皇之威，大城之内无人可挡"),
            PowerLevel(name="斗宗", description="斗技大成，一宗之力"),
            PowerLevel(name="斗尊", description="俯瞰大陆，各大势力争相拉拢"),
            PowerLevel(name="斗圣", description="天地变色，战力登峰造极"),
            PowerLevel(name="斗帝", description="千年一出，举手投足间山河变色"),
        ],
        rules=["斗气来源于天地元气，每日修炼增长", "战斗时消耗斗气，修炼时恢复", "斗技需专项修习"],
        resources=["斗技", "草药", "魂骨", "斗晶", "古典"],
    ),

    PowerSystemTemplateType.BLOODLINE: PowerSystem(
        name="血统体系",
        template=PowerSystemTemplateType.BLOODLINE,
        levels=[
            PowerLevel(name="凡血", description="普通人类血脉，无特殊能力"),
            PowerLevel(name="魔血", description="混入魔族血脉，具备基础异能", requirements="血脉觉醒契机"),
            PowerLevel(name="王血", description="强大种族血统，能力大幅提升", requirements="王血觉醒，需特殊环境"),
            PowerLevel(name="神血", description="神明遗留血脉，拥有神术", requirements="神血完全觉醒"),
            PowerLevel(name="先祖血", description="上古先祖血统，血脉最顶端存在", requirements="先祖认可，血脉回溯"),
        ],
        rules=["血统决定天赋上限，后天无法改变", "血统觉醒需要契机或特殊条件", "高等血统对低等血统有天然压制"],
        resources=["血脉丹", "血统强化液", "先祖记忆碎片", "神族遗物"],
    ),

    PowerSystemTemplateType.POWER: PowerSystem(
        name="异能体系",
        template=PowerSystemTemplateType.POWER,
        levels=[
            PowerLevel(name="一阶", description="能力初显，不稳定，难以控制"),
            PowerLevel(name="二阶", description="能力稳定，可主动使用"),
            PowerLevel(name="三阶", description="能力进化，出现变体效果"),
            PowerLevel(name="四阶", description="能力专精，效率倍增"),
            PowerLevel(name="五阶", description="超人类巅峰，能力接近自身极限"),
            PowerLevel(name="六阶", description="突破人类框架，能力质变"),
            PowerLevel(name="顿悟级", description="彻悟异能本质，自创独特用法"),
            PowerLevel(name="传说级", description="能力已超出现有认知范畴，存在即威胁"),
        ],
        rules=["每人只能拥有一种基础异能", "使用过度会导致能力反噬", "觉醒概率极低，多为后天变异"],
        resources=["强化液", "异能晶石", "进化药剂", "精神稳定剂"],
    ),

    PowerSystemTemplateType.CLASS: PowerSystem(
        name="职业体系",
        template=PowerSystemTemplateType.CLASS,
        levels=[
            PowerLevel(name="学徒", description="职业入门，学习基础技能", requirements="加入行会，通过资质测试"),
            PowerLevel(name="初级", description="正式从业，掌握核心职业技能"),
            PowerLevel(name="中级", description="熟练运用，开始形成个人风格"),
            PowerLevel(name="高级", description="小有名气，可独当一面"),
            PowerLevel(name="大师", description="领域专家，受人尊敬"),
            PowerLevel(name="宗师", description="开创流派，引领发展方向"),
            PowerLevel(name="神师", description="超凡技艺，被后世奉为典范"),
            PowerLevel(name="超凡", description="已超越职业本身，化为传说"),
        ],
        rules=["职业可以跨职，但跨职后升级更难", "不同职业有天然克制关系", "职业等级由行会认证"],
        resources=["技能书", "职业勋章", "进阶道具", "行会积分"],
    ),

    PowerSystemTemplateType.KNIGHT: PowerSystem(
        name="骑士体系",
        template=PowerSystemTemplateType.KNIGHT,
        levels=[
            PowerLevel(name="见习骑士", description="接受训练，体能强化阶段", requirements="通过骑士团选拔"),
            PowerLevel(name="正式骑士", description="完成骑士授勋，可独立执行任务"),
            PowerLevel(name="精英骑士", description="战场骨干，统领小队"),
            PowerLevel(name="大骑士", description="荣誉卓著，执行关键任务"),
            PowerLevel(name="骑士长", description="统领骑士团分队"),
            PowerLevel(name="圣骑士", description="圣光护体，神圣力量觉醒", requirements="信仰纯粹，神明认可"),
            PowerLevel(name="圣卫", description="王国守护者，圣光极致掌控"),
            PowerLevel(name="神骑", description="神明在世间的行走意志，超越凡人极限"),
        ],
        rules=["骑士须遵守荣誉法典，违背则失去圣光", "圣骑士以上需要神明认可", "骑士团效忠对象决定能力上限"],
        resources=["圣光石", "神圣武器", "骑士勋章", "圣水", "信仰之力"],
    ),
}


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def get_template_summary() -> list[dict]:
    """返回所有内置模板的摘要信息（用于前端模板选择器）"""
    result = []
    for template_type, system in POWER_SYSTEM_TEMPLATES.items():
        result.append({
            "template": template_type.value,
            "name": system.name,
            "level_count": len(system.levels),
            "preview_levels": [lv.name for lv in system.levels[:3]],  # 前3个境界名预览
        })
    return result


def get_alignment_color(alignment: AlignmentType) -> str:
    """返回阵营对应的前端色值（供前端备用，后端可不使用）"""
    if alignment in (AlignmentType.LAWFUL_GOOD, AlignmentType.NEUTRAL_GOOD, AlignmentType.CHAOTIC_GOOD):
        return "#4ade80"   # 绿色 - 善良
    elif alignment in (AlignmentType.LAWFUL_NEUTRAL, AlignmentType.TRUE_NEUTRAL, AlignmentType.CHAOTIC_NEUTRAL):
        return "#9ca3af"   # 灰色 - 中立
    elif alignment in (AlignmentType.LAWFUL_EVIL, AlignmentType.NEUTRAL_EVIL, AlignmentType.CHAOTIC_EVIL):
        return "#f87171"   # 红色 - 邪恶
    else:
        return "#c084fc"   # 紫色 - 超越阵营


ALIGNMENT_LABELS: dict[AlignmentType, str] = {
    AlignmentType.LAWFUL_GOOD: "秩序善良",
    AlignmentType.NEUTRAL_GOOD: "中立善良",
    AlignmentType.CHAOTIC_GOOD: "混沌善良",
    AlignmentType.LAWFUL_NEUTRAL: "秩序中立",
    AlignmentType.TRUE_NEUTRAL: "绝对中立",
    AlignmentType.CHAOTIC_NEUTRAL: "混沌中立",
    AlignmentType.LAWFUL_EVIL: "秩序邪恶",
    AlignmentType.NEUTRAL_EVIL: "中立邪恶",
    AlignmentType.CHAOTIC_EVIL: "混沌邪恶",
    AlignmentType.TRANSCENDENT: "超越阵营",
}

WORLD_TYPE_LABELS: dict[WorldType, str] = {
    WorldType.CONTINENTAL: "大陆流",
    WorldType.PLANAR: "位面/世界流",
    WorldType.INTERSTELLAR: "星际/宇宙流",
    WorldType.MULTI_LAYER: "多层世界",
}
