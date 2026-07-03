"""Silence-based segmenting pipeline (``media_segment_at_silence``).

Splits a long recording into per-take files at detected silences using the
``segment`` muxer with stream copy (near-instant, no re-encode). Silence points
come from the existing ``adapters/ffmpeg/silence.detect_silence`` adapter; cut
points are placed at the *midpoint* of each qualifying silence and filtered so
no resulting segment is shorter than ``min_segment``.

Output goes to ``media/processed/<stem>_takes/`` -- never ``media/raw``.

Note: stream-copy segmenting can only cut on keyframes, so the muxer splits at
the first keyframe at/after each requested time. Real footage carries regular
keyframes; synthetic fixtures must force them.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.silence import detect_silence

logger = logging.getLogger(__name__)


def compute_cut_points(
    silences: list[tuple[float, float]],
    duration: float,
    min_segment: float = 2.0,
) -> list[float]:
    """Pick cut timestamps at silence midpoints, honouring *min_segment*.

    A cut is accepted only if it is at least *min_segment* seconds after the
    previous accepted cut (or the clip start) and at least *min_segment*
    before the clip end.
    """
    cuts: list[float] = []
    last = 0.0
    for start, end in silences:
        mid = (start + end) / 2.0
        if mid - last < min_segment:
            continue
        if duration > 0 and (duration - mid) < min_segment:
            continue
        cuts.append(round(mid, 3))
        last = mid
    return cuts


def takes_dir(workspace_path: Path, source: str | Path) -> Path:
    """Return ``media/processed/<stem>_takes/`` under the workspace."""
    stem = Path(source).stem
    return Path(workspace_path) / "media" / "processed" / f"{stem}_takes"


def build_segment_command(
    source: Path,
    out_pattern: Path,
    cut_points: list[float],
) -> list[str]:
    """Build the stream-copy ``segment`` muxer command."""
    times = ",".join(f"{t:g}" for t in cut_points)
    return [
        "ffmpeg", "-y", "-i", str(source),
        "-c", "copy",
        "-map", "0",
        "-f", "segment",
        "-segment_times", times,
        "-reset_timestamps", "1",
        str(out_pattern),
    ]


def segment_at_silence(
    source: Path,
    out_dir: Path,
    noise_db: float = -30.0,
    min_silence: float = 0.6,
    min_segment: float = 2.0,
    dry_run: bool = False,
) -> dict:
    """Split *source* at silence midpoints into *out_dir*.

    Returns a dict with ``success``, ``segment_paths``, ``segment_count``,
    ``cut_points`` and the constructed ``command``.
    """
    source = Path(source)
    out_dir = Path(out_dir)

    try:
        duration = probe_media(source).duration
    except Exception:  # noqa: BLE001
        duration = 0.0

    silences = detect_silence(source, threshold_db=noise_db, min_duration=min_silence)
    cut_points = compute_cut_points(silences, duration, min_segment)

    out_pattern = out_dir / f"{source.stem}_%03d{source.suffix}"
    cmd = build_segment_command(source, out_pattern, cut_points)

    base = {
        "success": True,
        "source": str(source),
        "output_dir": str(out_dir),
        "silence_count": len(silences),
        "cut_points": cut_points,
        "segment_count": len(cut_points) + 1,
        "command": cmd,
    }

    if dry_run:
        base["segment_paths"] = []
        return base

    out_dir.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {**base, "success": False,
                "error": f"segment muxer failed: {proc.stderr[-400:]}"}

    segment_paths = sorted(str(p) for p in out_dir.glob(f"{source.stem}_*{source.suffix}"))
    base["segment_paths"] = segment_paths
    base["segment_count"] = len(segment_paths)
    return base
