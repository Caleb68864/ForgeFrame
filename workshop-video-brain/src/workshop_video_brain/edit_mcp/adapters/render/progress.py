"""The render progress callback, shared by every render engine."""
from __future__ import annotations

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
