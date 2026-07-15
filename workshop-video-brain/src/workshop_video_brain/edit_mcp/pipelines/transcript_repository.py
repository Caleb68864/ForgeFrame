"""Query/slice/search over parsed transcript segments.

Transcription generation stays in ``adapters/stt/whisper_engine.py`` -- this
module only reads already-parsed :class:`TranscriptSegment` lists.
"""
from __future__ import annotations

from workshop_video_brain.core.models.transcript import TranscriptSegment


class TranscriptRepository:
    """In-memory query layer over a list of transcript segments."""

    def __init__(self, segments: list[TranscriptSegment]):
        self._segments = list(segments)

    @property
    def segments(self) -> list[TranscriptSegment]:
        return list(self._segments)

    def search(self, term: str, case_insensitive: bool = True) -> list[TranscriptSegment]:
        """Return segments whose text contains *term* as a substring."""
        if case_insensitive:
            needle = term.lower()
            return [seg for seg in self._segments if needle in seg.text.lower()]
        return [seg for seg in self._segments if term in seg.text]

    def overlapping(self, start: float, end: float) -> list[TranscriptSegment]:
        """Return segments whose time range intersects ``[start, end]``."""
        return [
            seg
            for seg in self._segments
            if seg.start_seconds < end and seg.end_seconds > start
        ]

    def context_around(self, timestamp: float, seconds: float) -> list[TranscriptSegment]:
        """Return segments intersecting the band ``[timestamp - seconds, timestamp + seconds]``."""
        return self.overlapping(timestamp - seconds, timestamp + seconds)

    def merge_adjacent(self, gap_seconds: float) -> list[TranscriptSegment]:
        """Merge segments separated by a gap of at most *gap_seconds*.

        Segments are merged in chronological order; text is joined with a
        single space. Returns a new list -- the repository's own segments are
        left untouched.
        """
        ordered = sorted(self._segments, key=lambda seg: seg.start_seconds)
        if not ordered:
            return []

        merged: list[TranscriptSegment] = [ordered[0].model_copy(deep=True)]
        for seg in ordered[1:]:
            last = merged[-1]
            if seg.start_seconds - last.end_seconds <= gap_seconds:
                last.end_seconds = max(last.end_seconds, seg.end_seconds)
                last.text = f"{last.text} {seg.text}".strip()
            else:
                merged.append(seg.model_copy(deep=True))
        return merged
