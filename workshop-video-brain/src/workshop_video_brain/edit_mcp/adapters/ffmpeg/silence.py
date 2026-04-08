"""Silence detection adapter using ffmpeg's silencedetect filter."""
from __future__ import annotations

import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_SILENCE_START_RE = re.compile(r"silence_start:\s*([\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*([\d.]+)")


def detect_silence(
    path: Path,
    threshold_db: float = -30.0,
    min_duration: float = 2.0,
) -> list[tuple[float, float]]:
    """Detect silence gaps in an audio or video file.

    Runs ffmpeg's ``silencedetect`` filter and parses the stderr output.

    Args:
        path: Path to the media file.
        threshold_db: Noise threshold in dBFS (e.g. ``-30.0``).
        min_duration: Minimum silence duration in seconds.

    Returns:
        List of ``(start_seconds, end_seconds)`` tuples for each silence gap
        that meets both the threshold and duration criteria.
    """
    path = Path(path)

    result = subprocess.run(
        [
            "ffmpeg",
            "-i", str(path),
            "-af", f"silencedetect=noise={threshold_db}dB:d={min_duration}",
            "-f", "null",
            "-",
        ],
        capture_output=True,
        text=True,
        # ffmpeg returns non-zero when writing to /dev/null equivalent; ignore
        check=False,
    )

    # ffmpeg writes filter output to stderr
    stderr = result.stderr

    starts: list[float] = []
    ends: list[float] = []

    for line in stderr.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            starts.append(float(start_match.group(1)))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match:
            ends.append(float(end_match.group(1)))

    # Pair up starts and ends; if the file ends during silence there may be
    # an unmatched start -- skip it.
    pairs: list[tuple[float, float]] = []
    for start, end in zip(starts, ends):
        pairs.append((start, end))

    logger.debug(
        "Detected %d silence gap(s) in %s (threshold=%sdB, min_dur=%ss)",
        len(pairs),
        path,
        threshold_db,
        min_duration,
    )
    return pairs
