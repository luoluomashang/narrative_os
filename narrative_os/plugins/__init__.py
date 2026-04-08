"""narrative_os.plugins — Phase 5: 插件系统（Plugin System）

提供自定义 Skill 扩展机制：
  PluginManifest  — 插件元数据 Schema（Pydantic）
  PluginBase      — 插件抽象基类
  PluginLoader    — 从 dict / 目录加载插件
  PluginRegistry  — 全局插件注册表（集成 SkillRegistry）
"""

from narrative_os.plugins.manifest import PluginManifest
from narrative_os.plugins.base import PluginBase
from narrative_os.plugins.loader import PluginLoader, FnPlugin
from narrative_os.plugins.registry import PluginRegistry

__all__ = [
    "PluginManifest",
    "PluginBase",
    "PluginLoader",
    "FnPlugin",
    "PluginRegistry",
]
