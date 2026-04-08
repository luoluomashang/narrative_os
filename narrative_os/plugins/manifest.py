"""plugins/manifest.py — 插件元数据 Schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PluginManifest(BaseModel):
    """
    插件元数据，对应 __plugin__.yaml 中的字段。

    字段约束
    --------
    name        唯一标识符，仅允许字母数字下划线连字符
    skill_name  在 SkillRegistry 中注册的 Skill 名称
    requires    本插件依赖的其他 Skill 名称列表
    """

    name: str
    version: str = "1.0.0"
    description: str = ""
    skill_name: str
    author: str = ""
    requires: list[str] = Field(default_factory=list)

    model_config = {"frozen": True}

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        import re
        if not re.match(r"^[A-Za-z0-9_\-]+$", v):
            raise ValueError(
                f"Plugin name '{v}' 格式不合法（仅允许字母、数字、下划线、连字符）"
            )
        return v

    @field_validator("skill_name")
    @classmethod
    def _validate_skill_name(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("skill_name 不能为空")
        return v
