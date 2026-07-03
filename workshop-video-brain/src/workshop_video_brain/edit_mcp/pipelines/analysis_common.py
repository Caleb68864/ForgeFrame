"""Shared helpers for the analysis/sorting pipelines.

Pure path + report plumbing used by the five "ingest brain" analysis tools
(``media_thumbnail_sheet``, ``clips_qc_scan``, ``clips_detect_scenes``,
``media_segment_at_silence``, ``audio_loudness_scan``). No ffmpeg execution
lives here -- just source resolution and JSON-report helpers so the pipelines
do not duplicate boilerplate.

New module; imported (never modifies) by the analysis pipelines.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import DEFAULT_EXTENSIONS

# Extensions treated as video for the frame/segment tools.
VIDEO_EXTS: set[str] = {
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts",
}


def resolve_under_workspace(workspace_path: Path, source: str) -> Path:
    """Resolve *source* to an absolute path, relative to the workspace."""
    p = Path(source)
    if not p.is_absolute():
        p = Path(workspace_path) / source
    return p


def iter_media_files(
    target: Path,
    extensions: set[str] | None = None,
) -> list[Path]:
    """Return media files for *target*.

    A single file yields ``[file]``; a directory yields all matching media
    files (recursive, sorted). A missing path yields ``[]``.
    """
    extensions = extensions or DEFAULT_EXTENSIONS
    target = Path(target)
    if target.is_dir():
        return sorted(
            f for f in target.rglob("*")
            if f.is_file() and f.suffix.lower() in extensions
        )
    if target.is_file():
        return [target]
    return []


def reports_dir(workspace_path: Path) -> Path:
    """Return (and create) the workspace ``reports/`` directory."""
    d = Path(workspace_path) / "reports"
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_json_report(workspace_path: Path, name: str, payload: dict) -> Path:
    """Write *payload* as pretty JSON into ``reports/<name>`` and return path."""
    path = reports_dir(workspace_path) / name
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def timestamp_slug() -> str:
    """A filesystem-safe timestamp for report filenames."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")
