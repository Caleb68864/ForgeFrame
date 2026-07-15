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


def write_loudness_to_library(vault_path: Path, rows: list[dict]) -> dict:
    """Optionally fold measured LUFS into matching B-roll library entries.

    Matches each scanned clip to a library entry by ``source_path`` and writes
    its integrated loudness into ``BRollEntry.loudness_lufs`` (added to the
    model so extra keys are no longer dropped). Clips with no matching entry --
    or no successful measurement -- are skipped. Returns
    ``{"matched": int, "updated": int}``. Purely additive: the scan works fully
    without a library, and unrelated entry fields are never touched.
    """
    from workshop_video_brain.edit_mcp.pipelines.broll_library import (
        load_library,
        save_library,
    )

    library = load_library(Path(vault_path))
    by_path = {e.source_path: e for e in library.entries if e.source_path}
    updated = 0
    for row in rows:
        if not row.get("ok") or row.get("lufs") is None:
            continue
        entry = by_path.get(row.get("clip"))
        if entry is not None:
            entry.loudness_lufs = float(row["lufs"])
            updated += 1
    if updated:
        save_library(Path(vault_path), library)
    return {"matched": len(by_path), "updated": updated}


def scan_loudness(sources: list[Path]) -> dict:
    """Measure every clip in *sources* and return a table + summary."""
    rows = [measure_clip(s) for s in sources]
    return {
        "clips_scanned": len(rows),
        "summary": summarize(rows),
        "results": rows,
    }
