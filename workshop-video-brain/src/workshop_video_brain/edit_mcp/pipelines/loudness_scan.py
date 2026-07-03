"""Batch loudness-scan pipeline (``audio_loudness_scan``).

Measures integrated loudness / true-peak / loudness-range across one clip or a
whole directory by reusing ``probe.measure_loudness`` (the existing single-pass
``loudnorm=print_format=json`` measure). Produces a per-clip LUFS table for
consistency sorting plus a JSON report.
"""
from __future__ import annotations

import logging
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import measure_loudness

logger = logging.getLogger(__name__)


def measure_clip(source: Path) -> dict:
    """Measure loudness for one clip; returns a row dict.

    On measurement failure the row carries ``lufs=None`` and ``ok=False``.
    """
    source = Path(source)
    result = measure_loudness(source)
    if result is None:
        return {
            "clip": str(source),
            "ok": False,
            "lufs": None,
            "true_peak": None,
            "lra": None,
        }
    return {
        "clip": str(source),
        "ok": True,
        "lufs": round(result.input_i, 2),
        "true_peak": round(result.input_tp, 2),
        "lra": round(result.input_lra, 2),
    }


def summarize(rows: list[dict]) -> dict:
    """Aggregate a loudness table into a small summary."""
    measured = [r["lufs"] for r in rows if r.get("ok") and r.get("lufs") is not None]
    if not measured:
        return {"measured": 0, "avg_lufs": None, "min_lufs": None,
                "max_lufs": None, "lufs_spread": None}
    return {
        "measured": len(measured),
        "avg_lufs": round(sum(measured) / len(measured), 2),
        "min_lufs": min(measured),
        "max_lufs": max(measured),
        "lufs_spread": round(max(measured) - min(measured), 2),
    }


def scan_loudness(sources: list[Path]) -> dict:
    """Measure every clip in *sources* and return a table + summary."""
    rows = [measure_clip(s) for s in sources]
    return {
        "clips_scanned": len(rows),
        "summary": summarize(rows),
        "results": rows,
    }
