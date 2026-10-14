"""FFmpeg scene-change detection adapter -- the one ffmpeg scene scorer.

:func:`scan_scene_cuts` runs ffmpeg's ``select='gt(scene,threshold)'`` with
``metadata=print`` (logged to stderr, so no stats-file path ever enters the
filtergraph) and returns the real per-cut ``scene`` score on its 0..1 scale.
Both consumers sit on top of it:

* :func:`detect_scene_changes` (visual research) adds a minimum gap between
  detections and falls back to bounded uniform temporal sampling when no
  scene changes are found (e.g. a static source range).
* ``pipelines/scene_detect.detect_scenes`` (``clips_detect_scenes``) reports
  the raw ``{time, score}`` cut list.

ffmpeg's ``metadata=print`` writes, per selected frame::

    [Parsed_metadata_1 @ 0x...] frame:0    pts:20480   pts_time:2
    [Parsed_metadata_1 @ 0x...] lavfi.scene_score=0.657581
"""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

from workshop_video_brain.core.models import SceneChange
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS,
    FFmpegNotFound,
    FFmpegTimeout,
    _FFMPEG_INSTALL_HINT,
    _stderr_tail,
)

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"pts_time:(-?\d+\.?\d*)")
_SCORE_RE = re.compile(r"lavfi\.scene_score=(-?\d+\.?\d*)")

_UNIFORM_FALLBACK_MAX_SAMPLES = 8


class SceneScanError(RuntimeError):
    """ffmpeg exited nonzero without emitting any scores (undecodable source)."""

    def __init__(self, returncode: int, stderr_tail: str) -> None:
        super().__init__(
            "scene detection failed to decode the source "
            f"(ffmpeg rc={returncode}): {stderr_tail}"
        )
        self.returncode = returncode
        self.stderr_tail = stderr_tail


def build_select_filter(threshold: float) -> str:
    """Build the ``select``/``metadata`` scene-scoring filter (threshold clamped to 0..1)."""
    t = max(0.0, min(1.0, float(threshold)))
    return f"select='gt(scene\\,{t:g})',metadata=print"


def build_scan_command(
    video_path: Path,
    threshold: float,
    start_seconds: float = 0.0,
    duration_seconds: float | None = None,
) -> list[str]:
    """Build the analysis-only scene-scan command, optionally range-limited."""
    cmd: list[str] = ["ffmpeg", "-hide_banner"]
    if start_seconds > 0:
        cmd += ["-ss", str(start_seconds)]
    cmd += ["-i", str(video_path)]
    if duration_seconds is not None and duration_seconds > 0:
        cmd += ["-t", str(duration_seconds)]
    cmd += ["-vf", build_select_filter(threshold), "-an", "-f", "null", "-"]
    return cmd


def parse_scene_scores(text: str) -> list[tuple[float, float]]:
    """Parse ``metadata=print`` output into ``[(pts_time, score)]`` pairs."""
    hits: list[tuple[float, float]] = []
    current_time: float | None = None
    for line in text.splitlines():
        tm = _TIME_RE.search(line)
        if tm:
            current_time = float(tm.group(1))
            continue
        sm = _SCORE_RE.search(line)
        if sm and current_time is not None:
            hits.append((current_time, float(sm.group(1))))
            current_time = None
    return hits


def scan_scene_cuts(
    video_path: Path,
    threshold: float,
    start_seconds: float = 0.0,
    end_seconds: float | None = None,
) -> list[tuple[float, float]]:
    """Return ``[(timestamp_seconds, score)]`` for every frame whose scene score clears *threshold*.

    Timestamps are absolute (offset by *start_seconds*). Raises
    :class:`FFmpegNotFound`, :class:`FFmpegTimeout` (``ANALYSIS_TIMEOUT_SECONDS``)
    and :class:`SceneScanError` -- never a silent empty list on failure.
    """
    video_path = Path(video_path)
    start = max(0.0, start_seconds or 0.0)
    duration = (end_seconds - start) if end_seconds is not None else None
    cmd = build_scan_command(video_path, threshold, start, duration)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, check=False,
            timeout=ANALYSIS_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise FFmpegNotFound(
            f"ffmpeg binary not found on PATH (input: {video_path}). "
            f"{_FFMPEG_INSTALL_HINT}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegTimeout(
            f"scene detection timed out after {ANALYSIS_TIMEOUT_SECONDS:.0f}s "
            f"on {video_path.name}."
        ) from exc

    hits = parse_scene_scores(proc.stderr or "")
    # ffmpeg can exit nonzero at a truncated EOF after emitting valid scores;
    # only a nonzero exit with *no* scores means the source was undecodable.
    if proc.returncode != 0 and not hits:
        raise SceneScanError(proc.returncode, _stderr_tail(proc.stderr or "", 6))
    return [(start + t, score) for t, score in hits]


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
    """Scene hits for the range; an undecodable range yields none (-> uniform fallback)."""
    try:
        return scan_scene_cuts(video_path, threshold, range_start, range_end)
    except SceneScanError as exc:
        logger.warning("Scene detection could not decode %s: %s", video_path, exc)
        return []


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
