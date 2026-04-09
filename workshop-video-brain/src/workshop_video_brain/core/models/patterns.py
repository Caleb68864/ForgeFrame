"""MYOG Pattern Brain data models."""
from __future__ import annotations

from ._base import SerializableMixin


class MaterialItem(SerializableMixin):
    """A single material item extracted from a transcript."""

    name: str
    quantity: str = ""
    notes: str = ""
    timestamp: float = 0.0


class Measurement(SerializableMixin):
    """A measurement extracted from a transcript."""

    value: str      # e.g. "3.5"
    unit: str       # e.g. "inches"
    context: str    # e.g. "cut the fabric to 3.5 inches"
    timestamp: float = 0.0


class BuildStep(SerializableMixin):
    """A numbered build step extracted from a transcript."""

    number: int
    description: str
    timestamp: float = 0.0


class BuildTip(SerializableMixin):
    """A tip or warning extracted from a transcript."""

    text: str
    tip_type: str   # "tip" or "warning"
    timestamp: float = 0.0


class BuildData(SerializableMixin):
    """Aggregated build data extracted from a MYOG project transcript."""

    project_title: str = ""
    materials: list[MaterialItem] = []
    measurements: list[Measurement] = []
    steps: list[BuildStep] = []
    tips: list[BuildTip] = []
