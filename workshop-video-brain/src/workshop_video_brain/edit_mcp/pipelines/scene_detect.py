"""Scene-cut detection pipeline (``clips_detect_scenes``).

Thin layer over the single ffmpeg scene scorer,
:func:`workshop_video_brain.edit_mcp.adapters.ffmpeg.scene.scan_scene_cuts`,
returning a list of ``{time, score}`` shot boundaries. An agent (or
``media_segment_at_silence``) can then split the recording, and each shot lands
in the b-roll index as its own entry.

The ``scene`` value is on the familiar 0..1 scale (0 = identical to previous
frame, 1 = completely different), which matches the ``threshold`` contract.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegNotFound
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import (
    SceneScanError,
    build_scan_command,
    build_select_filter,
    parse_scene_scores as _parse_hits,
    scan_scene_cuts,
)

logger = logging.getLogger(__name__)

__all__ = [
    "build_scan_command",
    "build_select_filter",
    "detect_scenes",
    "parse_scene_scores",
]


def parse_scene_scores(stats_text: str) -> list[dict]:
    """Parse ``metadata=print`` output into ``[{time, score}]`` (score 0..1)."""
    return [_cut(t, score) for t, score in _parse_hits(stats_text)]


def _cut(time: float, score: float) -> dict:
    return {"time": round(time, 3), "score": round(score, 4)}


def detect_scenes(
    source: Path,
    threshold: float = 0.4,
    dry_run: bool = False,
) -> dict:
    """Detect scene cuts in *source*; return cut points and metadata."""
    source = Path(source)

    if dry_run:
        return {"success": True, "source": str(source), "threshold": threshold,
                "command": build_scan_command(source, threshold), "cuts": []}

    try:
        hits = scan_scene_cuts(source, threshold)
    except FFmpegNotFound:
        # ffmpeg binary itself missing -- an environment error, not "no cuts".
        return {
            "success": False,
            "source": str(source),
            "threshold": threshold,
            "error": "ffmpeg binary not found on PATH.",
            "error_type": "missing_binary",
        }
    except SceneScanError as exc:
        # Do NOT report a false success with zero cuts for an undecodable source.
        return {
            "success": False,
            "source": str(source),
            "threshold": threshold,
            "error": str(exc),
            "error_type": "media_unreadable",
        }

    cuts = [_cut(t, score) for t, score in hits]
    return {
        "success": True,
        "source": str(source),
        "threshold": threshold,
        "cut_count": len(cuts),
        "cuts": cuts,
    }
