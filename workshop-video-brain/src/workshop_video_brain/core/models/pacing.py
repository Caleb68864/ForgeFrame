"""Pacing and energy analysis models."""
from __future__ import annotations

from ._base import SerializableMixin


class PacingSegment(SerializableMixin):
    """Represents a time-based segment of pacing analysis."""

    start: float
    end: float
    wpm: float                    # words per minute
    speech_density: float         # speech_time / duration (0-1)
    word_variety: float           # unique_words / total_words (0-1)
    avg_sentence_length: float    # average words per sentence
    pace: str                     # "fast", "medium", "slow"
    text_preview: str             # first 50 chars


class PacingReport(SerializableMixin):
    """Full pacing analysis report for a transcript."""

    segments: list[PacingSegment]
    overall_wpm: float
    overall_pace: str
    weak_intro: bool
    energy_drops: list[dict]      # [{start, end, duration}]
    summary: str
