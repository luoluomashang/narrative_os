"""plugins/loader.py — 插件加载器。

提供两种加载方式：
  load_from_dict()       从 manifest dict + callable 创建轻量插件
  load_from_directory()  扫描目录中的 __plugin__.yaml + plugin.py 动态加载
"""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from narrative_os.plugins.base import PluginBase
from narrative_os.plugins.manifest import PluginManifest
from narrative_os.skills.dsl import SkillRequest, SkillResponse


# ------------------------------------------------------------------ #
# FnPlugin — 包装一个 callable 成 PluginBase                            #
# ------------------------------------------------------------------ #

class FnPlugin(PluginBase):
    """
    以函数（同步或异步）构建的最简插件。
    通过 PluginLoader.load_from_dict() 创建。
    """

    def __init__(
        self,
        manifest: PluginManifest,
        handler: Callable[..., Any],
    ) -> None:
        self._manifest = manifest
        self._handler = handler

    @property
    def manifest(self) -> PluginManifest:
        return self._manifest

    async def execute(self, req: SkillRequest) -> SkillResponse:
        import asyncio
        if asyncio.iscoroutinefunction(self._handler):
            return await self._handler(req)
        return self._handler(req)


# ------------------------------------------------------------------ #
# PluginLoader                                                          #
# ------------------------------------------------------------------ #

class PluginLoader:
    """插件加载工具（无状态，所有方法为 @staticmethod）。"""

    @staticmethod
    def load_from_dict(
        config: dict[str, Any],
        handler: Callable[..., Any],
    ) -> FnPlugin:
        """
        从 manifest dict + handler callable 创建 FnPlugin。

        Parameters
        ----------
        config  : 包含 PluginManifest 字段的字典（最少需 name + skill_name）
        handler : 签名为 (SkillRequest) -> SkillResponse 的同步或异步函数
        """
        manifest = PluginManifest(**config)
        return FnPlugin(manifest=manifest, handler=handler)

    @staticmethod
    def load_from_directory(path: str | Path) -> list[PluginBase]:
        """
        扫描目录，发现并加载所有插件。

        每个插件子目录必须包含：
          __plugin__.yaml  — 插件元数据（PluginManifest 字段）
          plugin.py        — 包含 `create_plugin() -> PluginBase` 工厂函数

        目录结构示例：
          plugins_dir/
            my_skill/
              __plugin__.yaml
              plugin.py        # def create_plugin() -> PluginBase: ...
        """
        root = Path(path)
        if not root.is_dir():
            raise NotADirectoryError(f"插件目录不存在: {root}")

        plugins: list[PluginBase] = []
        for subdir in sorted(root.iterdir()):
            if not subdir.is_dir():
                continue
            manifest_path = subdir / "__plugin__.yaml"
            plugin_path = subdir / "plugin.py"
            if not manifest_path.exists() or not plugin_path.exists():
                continue

            # 加载 manifest
            with manifest_path.open(encoding="utf-8") as f:
                manifest_data = yaml.safe_load(f) or {}
            manifest = PluginManifest(**manifest_data)

            # 动态加载 plugin.py
            module_name = f"_plugin_{manifest.name}"
            spec = importlib.util.spec_from_file_location(module_name, plugin_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)  # type: ignore[union-attr]

            if not hasattr(module, "create_plugin"):
                continue
            plugin: PluginBase = module.create_plugin()
            plugins.append(plugin)

        return plugins
