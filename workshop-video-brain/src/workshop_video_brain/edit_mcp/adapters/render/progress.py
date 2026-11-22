"""The render progress callback, shared by every render engine."""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class RenderProgress:
    frame: int  # last frame rendered, 0-based
    total_frames: int  # 0 when unknown
    percent: float  # 0..100
    engine: str  # "mlt" | "melt"


ProgressCallback = Callable[[RenderProgress], None]


class Throttle:
    """Forward at most once a second, or when percent moves by 1 or more, and always at 100.

    Job progress persists through a SQLite ``BEGIN IMMEDIATE`` per call, so an
    unthrottled render would hammer it.
    """

    def __init__(self, callback: ProgressCallback, clock: Callable[[], float] = time.monotonic) -> None:
        self._callback = callback
        self._clock = clock
        self._last_time: float | None = None
        self._last_percent = 0.0

    def __call__(self, update: RenderProgress) -> None:
        now = self._clock()
        if (
            self._last_time is None
            or update.percent >= 100.0
            or now - self._last_time >= 1.0
            or abs(update.percent - self._last_percent) >= 1.0
        ):
            self._last_time, self._last_percent = now, update.percent
            self._callback(update)


_MELT_PROGRESS = re.compile(r"Current Frame:\s*(\d+),\s*percentage:\s*(\d+)")


def parse_melt_progress(chunk: str) -> list[tuple[int, int]]:
    """``(frame, percent)`` for every melt progress report in *chunk*.

    melt writes ``Current Frame:  31, percentage:  62`` to stderr, ended by
    ``\\r`` by default and by ``\\n`` with ``-progress2``; both are split on.
    melt never reports 100: the caller sets it once the output is verified.
    """
    found: list[tuple[int, int]] = []
    for segment in re.split(r"[\r\n]", chunk or ""):
        match = _MELT_PROGRESS.search(segment)
        if match:
            found.append((int(match.group(1)), int(match.group(2))))
    return found


class MeltProgressReader:
    """Feed raw stderr chunks; complete progress lines go to *on_progress*.

    A chunk can end mid-line, so the unfinished tail is kept for the next one.
    """

    def __init__(self, on_progress: ProgressCallback, total_frames: int = 0) -> None:
        self._on_progress = on_progress
        self._total = total_frames
        self._pending = ""

    def feed(self, chunk: str) -> None:
        text = self._pending + chunk
        cut = max(text.rfind("\r"), text.rfind("\n"))
        if cut < 0:
            self._pending = text
            return
        self._pending = text[cut + 1:]
        for frame, percent in parse_melt_progress(text[:cut]):
            total = self._total or (round(frame * 100 / percent) if percent > 0 else 0)
            self._on_progress(RenderProgress(frame=frame, total_frames=total,
                                             percent=float(percent), engine="melt"))
