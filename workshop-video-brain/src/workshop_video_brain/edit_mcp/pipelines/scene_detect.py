"""Scene-cut detection pipeline (``clips_detect_scenes``).

Runs FFmpeg's ``select='gt(scene,threshold)'`` in analysis mode (``-f null -``)
and prints the per-frame ``scene`` score for the frames that clear the
threshold, returning a list of ``{time, score}`` shot boundaries. An agent (or
``media_segment_at_silence``) can then split the recording, and each shot lands
in the b-roll index as its own entry.

The ``scene`` value is on the familiar 0..1 scale (0 = identical to previous
frame, 1 = completely different), which matches the ``threshold`` contract.
FFmpeg's ``metadata=print`` writes, per selected frame::

    frame:0    pts:20480   pts_time:2
    lavfi.scene_score=0.657581
"""
from __future__ import annotations

import logging
import re
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

_TIME_RE = re.compile(r"pts_time:(-?\d+\.?\d*)")
_SCORE_RE = re.compile(r"lavfi\.scene_score=(-?\d+\.?\d*)")


def build_select_filter(threshold: float, stats_file: Path) -> str:
    """Build the ``select``/``metadata`` scene-scoring filter string."""
    t = max(0.0, min(1.0, float(threshold)))
    return f"select='gt(scene\\,{t:g})',metadata=print:file={stats_file}"


def build_scan_command(source: Path, threshold: float, stats_file: Path) -> list[str]:
    """Build the analysis-only scene-detect command."""
    return [
        "ffmpeg", "-i", str(source),
        "-vf", build_select_filter(threshold, stats_file),
        "-an", "-f", "null", "-",
    ]


def parse_scene_scores(stats_text: str) -> list[dict]:
    """Parse the metadata dump into ``[{time, score}]`` (score 0..1)."""
    cuts: list[dict] = []
    current_time: float | None = None
    for line in stats_text.splitlines():
        tm = _TIME_RE.search(line)
        if tm:
            current_time = float(tm.group(1))
            continue
        sm = _SCORE_RE.search(line)
        if sm and current_time is not None:
            cuts.append({
                "time": round(current_time, 3),
                "score": round(float(sm.group(1)), 4),
            })
            current_time = None
    return cuts


def detect_scenes(
    source: Path,
    threshold: float = 0.4,
    dry_run: bool = False,
) -> dict:
    """Detect scene cuts in *source*; return cut points and metadata."""
    source = Path(source)

    with tempfile.TemporaryDirectory(prefix="scenedet_") as tmp:
        stats_file = Path(tmp) / "scenes.txt"
        cmd = build_scan_command(source, threshold, stats_file)

        if dry_run:
            return {"success": True, "source": str(source),
                    "threshold": threshold, "command": cmd, "cuts": []}

        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        except FileNotFoundError:
            # ffmpeg binary itself missing -- an environment error, not "no cuts".
            return {
                "success": False,
                "source": str(source),
                "threshold": threshold,
                "error": "ffmpeg binary not found on PATH.",
                "error_type": "missing_binary",
            }
        stats_text = stats_file.read_text(encoding="utf-8") if stats_file.exists() else ""

        # A nonzero ffmpeg exit means the source could not be decoded -- do NOT
        # report a false success with zero cuts. Only treat rc==0 (or rc!=0 but
        # scores were still emitted, which ffmpeg can do at EOF) as analysable.
        if proc.returncode != 0 and not stats_text.strip():
            return {
                "success": False,
                "source": str(source),
                "threshold": threshold,
                "error": (
                    "scene detection failed to decode the source "
                    f"(ffmpeg rc={proc.returncode}): {_stderr_tail(proc.stderr)}"
                ),
                "error_type": "media_unreadable",
            }

    cuts = parse_scene_scores(stats_text)
    return {
        "success": True,
        "source": str(source),
        "threshold": threshold,
        "cut_count": len(cuts),
        "cuts": cuts,
    }


def _stderr_tail(stderr: str, max_lines: int = 6) -> str:
    lines = [ln for ln in (stderr or "").splitlines() if ln.strip()]
    return "\n".join(lines[-max_lines:])
