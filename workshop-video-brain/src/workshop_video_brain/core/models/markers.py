"""Marker models."""
from __future__ import annotations

from uuid import UUID, uuid4

from pydantic import Field

from ._base import SerializableMixin
from .enums import MarkerCategory


class Marker(SerializableMixin):
    model_config = {"use_enum_values": True}

    id: UUID = Field(default_factory=uuid4)
    category: MarkerCategory
    confidence_score: float = 0.0
    source_method: str = ""
    reason: str = ""
    clip_ref: str = ""
    start_seconds: float = 0.0
    end_seconds: float = 0.0
    suggested_label: str = ""


class MarkerGroup(SerializableMixin):
    model_config = {"use_enum_values": True}

    markers: list[Marker] = Field(default_factory=list)
    category: MarkerCategory
    source: str = ""


class MarkerRule(SerializableMixin):
    """A rule that maps keywords to a marker category with a base confidence."""

    model_config = {"use_enum_values": True}

    keywords: list[str]
    category: MarkerCategory
    base_confidence: float


class MarkerConfig(SerializableMixin):
    """Configuration for the auto-marker pipeline."""

    model_config = {"use_enum_values": True}

    rules: list[MarkerRule] = Field(default_factory=list)
    category_weights: dict[str, float] = Field(default_factory=dict)
    silence_threshold_seconds: float = 2.0
    segment_merge_gap_seconds: float = 3.0
