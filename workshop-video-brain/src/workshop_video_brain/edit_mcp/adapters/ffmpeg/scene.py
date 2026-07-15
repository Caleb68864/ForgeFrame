"""FFmpeg scene-change detection adapter.

Detects scene changes within an optional time range using ffmpeg's
``select='gt(scene,threshold)'`` filter, enforces a minimum gap between
detections, and falls back to bounded uniform temporal sampling when no
scene changes are found (e.g. a static source range).
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models import SceneChange
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

logger = logging.getLogger(__name__)

_PTS_TIME_RE = re.compile(r"pts_time:([\d.]+)")

_UNIFORM_FALLBACK_MAX_SAMPLES = 8

_SCENE_DETECTION_TIMEOUT_SECONDS = 300


def detect_scene_changes(
    video_path: Path,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    threshold: float = 0.30,
    minimum_gap_seconds: float = 1.0,
) -> list[SceneChange]:
    """Detect scene changes in *video_path*, optionally within a time range.

    Args:
        video_path: Path to the source video.
        start_seconds: Inclusive start of the range to analyze; defaults to
            the start of the video.
        end_seconds: Exclusive end of the range to analyze; defaults to the
            end of the video.
        threshold: ffmpeg ``scene`` filter score threshold (0.0-1.0).
        minimum_gap_seconds: Minimum spacing enforced between consecutive
            detections (and between fallback samples).

    Returns:
        Scene changes sorted by timestamp, at least ``minimum_gap_seconds``
        apart. If ffmpeg finds no scene changes in the range, a bounded,
        non-empty uniform sample across the range is returned instead.
    """
    video_path = Path(video_path)

    try:
        asset = probe_media(video_path)
        total_duration = asset.duration_seconds
    except (subprocess.CalledProcessError, ValueError, OSError):
        logger.warning("Could not probe duration for %s", video_path)
        total_duration = 0.0

    range_start = max(0.0, start_seconds or 0.0)
    if end_seconds is not None:
        range_end = end_seconds
    elif total_duration > 0:
        range_end = total_duration
    else:
        range_end = range_start

    if total_duration > 0:
        range_end = min(range_end, total_duration)
    range_end = max(range_end, range_start)

    raw_timestamps = _run_scene_filter(video_path, range_start, range_end, threshold)

    changes = _enforce_minimum_gap(raw_timestamps, minimum_gap_seconds)

    if changes:
        return changes

    logger.debug(
        "No scene changes detected in %s [%s, %s]; falling back to uniform sampling",
        video_path,
        range_start,
        range_end,
    )
    return _uniform_sample_fallback(range_start, range_end, minimum_gap_seconds)


def _run_scene_filter(
    video_path: Path,
    range_start: float,
    range_end: float,
    threshold: float,
) -> list[tuple[float, float]]:
    """Run ffmpeg's scene-change filter and return raw (timestamp, score) hits."""
    cmd: list[str] = ["ffmpeg"]
    if range_start > 0:
        cmd += ["-ss", str(range_start)]
    cmd += ["-i", str(video_path)]

    duration = range_end - range_start
    if duration > 0:
        cmd += ["-t", str(duration)]

    cmd += [
        "-vf", f"select='gt(scene,{threshold})',showinfo",
        "-f", "null",
        "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=_SCENE_DETECTION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Scene detection timed out for %s", video_path)
        return []

    hits: list[tuple[float, float]] = []
    for line in result.stderr.splitlines():
        match = _PTS_TIME_RE.search(line)
        if not match:
            continue
        relative_time = float(match.group(1))
        hits.append((range_start + relative_time, threshold))

    return hits


def _enforce_minimum_gap(
    hits: list[tuple[float, float]],
    minimum_gap_seconds: float,
) -> list[SceneChange]:
    """Keep hits sorted by time, dropping any within minimum_gap_seconds of the last kept."""
    changes: list[SceneChange] = []
    last_kept: float | None = None
    for timestamp, score in sorted(hits, key=lambda h: h[0]):
        if last_kept is not None and (timestamp - last_kept) < minimum_gap_seconds:
            continue
        changes.append(SceneChange(timestamp_seconds=timestamp, score=score))
        last_kept = timestamp
    return changes


def _uniform_sample_fallback(
    range_start: float,
    range_end: float,
    minimum_gap_seconds: float,
) -> list[SceneChange]:
    """Bounded uniform temporal sampling across [range_start, range_end]."""
    span = range_end - range_start
    if span <= 0:
        return [SceneChange(timestamp_seconds=range_start, score=0.0)]

    max_by_gap = int(span // minimum_gap_seconds) + 1 if minimum_gap_seconds > 0 else _UNIFORM_FALLBACK_MAX_SAMPLES
    sample_count = max(1, min(_UNIFORM_FALLBACK_MAX_SAMPLES, max_by_gap))

    if sample_count == 1:
        return [SceneChange(timestamp_seconds=range_start + span / 2.0, score=0.0)]

    step = span / (sample_count - 1)
    return [
        SceneChange(timestamp_seconds=range_start + i * step, score=0.0)
        for i in range(sample_count)
    ]
