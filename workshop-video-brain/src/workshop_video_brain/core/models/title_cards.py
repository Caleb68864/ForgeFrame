"""Title card models."""
from __future__ import annotations

from ._base import SerializableMixin


class TitleCard(SerializableMixin):
    """Represents a title card to be shown at a specific point in the video."""

    chapter_title: str
    timestamp_seconds: float
    subtitle: str = ""
    duration_seconds: float = 3.0
    style: str = "standard"  # standard, minimal, bold
