"""plugins/base.py — 插件抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from narrative_os.plugins.manifest import PluginManifest
from narrative_os.skills.dsl import SkillRequest, SkillResponse


class PluginBase(ABC):
    """
    所有插件必须继承此类。

    子类需要实现：
      manifest — 返回插件元数据
      execute  — 处理 SkillRequest，返回 SkillResponse
    """

    @property
    @abstractmethod
    def manifest(self) -> PluginManifest:
        """返回插件的元数据。"""
        ...

    @abstractmethod
    async def execute(self, req: SkillRequest) -> SkillResponse:
        """
        处理技能调用请求。

        实现必须是 async def；同步逻辑可直接 return 结果。
        """
        ...

    def __repr__(self) -> str:
        m = self.manifest
        return f"<Plugin name={m.name!r} skill={m.skill_name!r} v{m.version}>"
