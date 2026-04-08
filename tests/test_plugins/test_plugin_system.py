"""tests/test_plugins/test_plugin_system.py — Plugin System 测试组。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from narrative_os.plugins.base import PluginBase
from narrative_os.plugins.loader import FnPlugin, PluginLoader
from narrative_os.plugins.manifest import PluginManifest
from narrative_os.plugins.registry import PluginRegistry
from narrative_os.skills.dsl import SkillRegistry, SkillRequest, SkillResponse


# ------------------------------------------------------------------ #
# Helpers                                                               #
# ------------------------------------------------------------------ #

def _make_manifest(**kwargs) -> PluginManifest:
    defaults = {"name": "my-plugin", "skill_name": "my_skill"}
    return PluginManifest(**{**defaults, **kwargs})


def _sync_handler(req: SkillRequest) -> SkillResponse:
    return SkillResponse(skill=req.skill, status="success", output={"echo": req.inputs})


async def _async_handler(req: SkillRequest) -> SkillResponse:
    return SkillResponse(skill=req.skill, status="success", output={"async": True})


# ------------------------------------------------------------------ #
# PluginManifest                                                        #
# ------------------------------------------------------------------ #

class TestPluginManifest:
    def test_minimal(self):
        m = PluginManifest(name="foo", skill_name="foo_skill")
        assert m.version == "1.0.0"
        assert m.author == ""
        assert m.requires == []

    def test_full_fields(self):
        m = PluginManifest(
            name="bar",
            version="2.3.1",
            description="a plugin",
            skill_name="bar_skill",
            author="Alice",
            requires=["scene", "humanize"],
        )
        assert m.requires == ["scene", "humanize"]

    def test_invalid_name_raises(self):
        with pytest.raises(Exception):
            PluginManifest(name="has space!", skill_name="x")

    def test_empty_skill_name_raises(self):
        with pytest.raises(Exception):
            PluginManifest(name="ok", skill_name="   ")

    def test_frozen(self):
        m = PluginManifest(name="x", skill_name="y")
        with pytest.raises(Exception):
            m.name = "z"   # type: ignore[misc]


# ------------------------------------------------------------------ #
# PluginBase abstract enforcement                                        #
# ------------------------------------------------------------------ #

class TestPluginBase:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            PluginBase()  # type: ignore[abstract]

    def test_concrete_subclass_works(self):
        class MyPlugin(PluginBase):
            @property
            def manifest(self) -> PluginManifest:
                return PluginManifest(name="mp", skill_name="mp_skill")

            async def execute(self, req: SkillRequest) -> SkillResponse:
                return SkillResponse(skill=req.skill, status="success")

        p = MyPlugin()
        assert p.manifest.name == "mp"

    def test_repr(self):
        class P(PluginBase):
            @property
            def manifest(self):
                return PluginManifest(name="p", skill_name="s", version="9.0.0")
            async def execute(self, req):
                return SkillResponse(skill=req.skill, status="success")

        assert "9.0.0" in repr(P())


# ------------------------------------------------------------------ #
# FnPlugin & PluginLoader.load_from_dict                                #
# ------------------------------------------------------------------ #

class TestFnPlugin:
    def test_load_from_dict_sync(self):
        plugin = PluginLoader.load_from_dict(
            {"name": "echo", "skill_name": "echo_skill"},
            _sync_handler,
        )
        assert isinstance(plugin, FnPlugin)
        assert plugin.manifest.skill_name == "echo_skill"

    async def test_sync_handler_wrapped_as_async(self):
        plugin = PluginLoader.load_from_dict(
            {"name": "echo2", "skill_name": "echo2_skill"},
            _sync_handler,
        )
        req = SkillRequest(skill="echo2_skill", inputs={"key": "val"})
        resp = await plugin.execute(req)
        assert resp.status == "success"
        assert resp.output["echo"]["key"] == "val"

    async def test_async_handler(self):
        plugin = PluginLoader.load_from_dict(
            {"name": "ap", "skill_name": "ap_skill"},
            _async_handler,
        )
        req = SkillRequest(skill="ap_skill")
        resp = await plugin.execute(req)
        assert resp.output["async"] is True


# ------------------------------------------------------------------ #
# PluginLoader.load_from_directory                                      #
# ------------------------------------------------------------------ #

class TestLoadFromDirectory:
    def test_not_a_directory_raises(self, tmp_path):
        fake = tmp_path / "not_a_dir"
        with pytest.raises(NotADirectoryError):
            PluginLoader.load_from_directory(fake)

    def test_empty_directory_returns_empty(self, tmp_path):
        plugins = PluginLoader.load_from_directory(tmp_path)
        assert plugins == []

    def test_discovers_valid_plugin(self, tmp_path):
        # Create plugin subdir
        pdir = tmp_path / "myplugin"
        pdir.mkdir()
        (pdir / "__plugin__.yaml").write_text(
            "name: disc-plugin\nskill_name: disc_skill\n", encoding="utf-8"
        )
        (pdir / "plugin.py").write_text(
            """
from narrative_os.plugins.loader import PluginLoader
def create_plugin():
    import asyncio
    from narrative_os.skills.dsl import SkillResponse
    return PluginLoader.load_from_dict(
        {"name": "disc-plugin", "skill_name": "disc_skill"},
        lambda req: SkillResponse(skill=req.skill, status="success"),
    )
""",
            encoding="utf-8",
        )
        plugins = PluginLoader.load_from_directory(tmp_path)
        assert len(plugins) == 1
        assert plugins[0].manifest.name == "disc-plugin"

    def test_skips_subdir_missing_yaml(self, tmp_path):
        bad = tmp_path / "bad"
        bad.mkdir()
        (bad / "plugin.py").write_text("", encoding="utf-8")  # no __plugin__.yaml
        plugins = PluginLoader.load_from_directory(tmp_path)
        assert plugins == []


# ------------------------------------------------------------------ #
# PluginRegistry                                                        #
# ------------------------------------------------------------------ #

class TestPluginRegistry:
    @pytest.fixture(autouse=True)
    def isolated_registry(self):
        """Each test gets a fresh PluginRegistry + SkillRegistry."""
        PluginRegistry._instance = None
        old_sr = SkillRegistry._instance
        SkillRegistry._instance = None
        yield
        PluginRegistry._instance = None
        SkillRegistry._instance = old_sr

    def test_singleton(self):
        r1 = PluginRegistry.instance()
        r2 = PluginRegistry.instance()
        assert r1 is r2

    def test_register_and_list(self):
        pr = PluginRegistry.instance()
        plugin = PluginLoader.load_from_dict(
            {"name": "p1", "skill_name": "p1_skill"},
            _sync_handler,
        )
        pr.register_plugin(plugin)
        manifests = pr.list_plugins()
        assert any(m.name == "p1" for m in manifests)

    def test_get_plugin(self):
        pr = PluginRegistry.instance()
        plugin = PluginLoader.load_from_dict(
            {"name": "findme", "skill_name": "find_skill"},
            _sync_handler,
        )
        pr.register_plugin(plugin)
        found = pr.get_plugin("findme")
        assert found is plugin

    def test_get_missing_returns_none(self):
        assert PluginRegistry.instance().get_plugin("ghost") is None

    def test_unregister_returns_true(self):
        pr = PluginRegistry.instance()
        plugin = PluginLoader.load_from_dict(
            {"name": "del-me", "skill_name": "del_skill"},
            _sync_handler,
        )
        pr.register_plugin(plugin)
        result = pr.unregister_plugin("del-me")
        assert result is True
        assert pr.get_plugin("del-me") is None

    def test_unregister_missing_returns_false(self):
        assert PluginRegistry.instance().unregister_plugin("nothing") is False

    async def test_skill_registered_in_skill_registry(self):
        pr = PluginRegistry.instance()
        plugin = PluginLoader.load_from_dict(
            {"name": "inte", "skill_name": "inte_skill"},
            _sync_handler,
        )
        pr.register_plugin(plugin)

        sr = SkillRegistry.instance()
        req = SkillRequest(skill="inte_skill", inputs={"x": 1})
        resp = await sr.execute_async(req)
        assert resp.status == "success"

    def test_list_plugins_sorted(self):
        pr = PluginRegistry.instance()
        for name in ["charlie", "alpha", "bravo"]:
            p = PluginLoader.load_from_dict(
                {"name": name, "skill_name": f"{name}_skill"},
                _sync_handler,
            )
            pr.register_plugin(p)
        names = [m.name for m in pr.list_plugins()]
        assert names == sorted(names)
