"""Planning models: shot plans, scripts, review notes, materials."""
from __future__ import annotations

from pydantic import Field

from ._base import SerializableMixin
from .enums import ShotType


class Shot(SerializableMixin):
    model_config = {"use_enum_values": True}

    type: ShotType
    description: str = ""
    beat_ref: str = ""
    priority: int = 0


class ShotPlan(SerializableMixin):
    model_config = {"use_enum_values": True}

    shots: list[Shot] = Field(default_factory=list)


class ScriptDraft(SerializableMixin):
    model_config = {"use_enum_values": True}

    sections: dict[str, str] = Field(default_factory=dict)
    tone: str = ""
    target_length: int = 0


class ReviewNote(SerializableMixin):
    model_config = {"use_enum_values": True}

    pacing_notes: list[str] = Field(default_factory=list)
    repetition_flags: list[str] = Field(default_factory=list)
    insert_suggestions: list[str] = Field(default_factory=list)
    overlay_ideas: list[str] = Field(default_factory=list)
    chapter_breaks: list[str] = Field(default_factory=list)


class MaterialList(SerializableMixin):
    model_config = {"use_enum_values": True}

    materials: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
