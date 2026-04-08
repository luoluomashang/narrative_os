"""plugins/registry.py — 全局插件注册表（集成 SkillRegistry）。"""

from __future__ import annotations

from narrative_os.plugins.base import PluginBase
from narrative_os.plugins.manifest import PluginManifest
from narrative_os.skills.dsl import SkillRegistry, SkillRequest, SkillResponse


class PluginRegistry:
    """
    全局插件注册表（进程级单例）。

    注册插件时自动将其 handler 挂载到 SkillRegistry，
    使插件 skill 可通过标准 SkillRequest 调用。

    用法：
        pr = PluginRegistry.instance()
        pr.register_plugin(my_plugin)
        pr.list_plugins()
        pr.get_plugin("my-plugin")
        pr.unregister_plugin("my-plugin")
    """

    _instance: "PluginRegistry | None" = None

    def __init__(self) -> None:
        self._plugins: dict[str, PluginBase] = {}   # name → plugin

    @classmethod
    def instance(cls) -> "PluginRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ---------------------------------------------------------------- #
    # CRUD                                                               #
    # ---------------------------------------------------------------- #

    def register_plugin(self, plugin: PluginBase) -> None:
        """
        注册插件：
        1. 存入内部字典
        2. 在 SkillRegistry 中注册异步 handler（skill_name）
        """
        m = plugin.manifest
        skill_reg = SkillRegistry.instance()

        # 若 skill_name 已注册则先取消注册（允许热替换）
        if m.skill_name in skill_reg._handlers:
            skill_reg.unregister(m.skill_name)

        async def _async_handler(req: SkillRequest) -> SkillResponse:
            return await plugin.execute(req)

        skill_reg.register_fn(
            m.skill_name,
            _async_handler,
            description=m.description,
            plugin_name=m.name,
            plugin_version=m.version,
        )
        self._plugins[m.name] = plugin

    def list_plugins(self) -> list[PluginManifest]:
        """返回所有已注册插件的 manifest 列表（按名称排序）。"""
        return [p.manifest for p in sorted(self._plugins.values(), key=lambda p: p.manifest.name)]

    def get_plugin(self, name: str) -> PluginBase | None:
        """按插件名查找，不存在返回 None。"""
        return self._plugins.get(name)

    def unregister_plugin(self, name: str) -> bool:
        """
        取消注册插件。
        同时从 SkillRegistry 中移除对应 skill。
        返回 True 表示成功，False 表示插件不存在。
        """
        plugin = self._plugins.pop(name, None)
        if plugin is None:
            return False
        SkillRegistry.instance().unregister(plugin.manifest.skill_name)
        return True
