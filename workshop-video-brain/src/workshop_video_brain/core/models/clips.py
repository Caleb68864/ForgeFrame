"""Clip label model for clip organization."""
from __future__ import annotations

from ._base import SerializableMixin


class ClipLabel(SerializableMixin):
    """Label describing what a clip contains, derived from transcript + markers."""

    clip_ref: str = ""                   # filename
    content_type: str = "unlabeled"      # tutorial_step, materials_overview, talking_head, b_roll, unlabeled
    topics: list[str] = []               # extracted noun phrases from transcript
    shot_type: str = "medium"            # closeup, overhead, medium, b_roll
    has_speech: bool = False
    speech_density: float = 0.0          # speech-time / total-duration (0.0-1.0)
    summary: str = ""                    # first ~100 chars of transcript, cleaned
    tags: list[str] = []                 # union of topics + content_type + shot_type, lowercased
    duration: float = 0.0
    source_path: str = ""
