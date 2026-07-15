"""Keyframe + contact-sheet extraction pipeline (``media_thumbnail_sheet``).

Extracts a handful of *representative* frames from a clip using FFmpeg's
``thumbnail`` filter (which picks the most typical frame per batch), optionally
tiling them into a single contact sheet via ``tile``. The frames are written to
``reports/thumbnails/<clip>/`` so a vision agent can look at them and hand tags
straight to ``broll_library_tag``.

Analysis-only: reads media, writes PNGs into ``reports/`` -- never touches
``media/raw`` or project files.
"""
from __future__ import annotations

import logging
import math
import subprocess
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure planning helpers
# ---------------------------------------------------------------------------

def grid_dimensions(frames: int) -> tuple[int, int]:
    """Return ``(cols, rows)`` for a roughly square tile grid holding *frames*."""
    frames = max(1, int(frames))
    cols = math.ceil(math.sqrt(frames))
    rows = math.ceil(frames / cols)
    return cols, rows


def compute_batch_size(total_frames: int, frames: int) -> int:
    """Pick a ``thumbnail`` batch size so ~*frames* thumbnails span the clip.

    ``thumbnail=n=B`` emits one representative frame per *B* input frames, so a
    batch of ``total_frames // frames`` spreads the requested number of
    thumbnails across the whole clip. Falls back to 1 when the frame count is
    unknown.
    """
    frames = max(1, int(frames))
    if total_frames <= 0:
        return 1
    return max(1, total_frames // frames)


def build_frames_filter(batch: int, width: int) -> str:
    """Filter string for the per-frame extraction pass."""
    return f"thumbnail=n={int(batch)},scale={int(width)}:-1"


def build_sheet_filter(batch: int, width: int, cols: int, rows: int) -> str:
    """Filter string for the single-image contact-sheet pass."""
    return (
        f"thumbnail=n={int(batch)},scale={int(width)}:-1,"
        f"tile={int(cols)}x{int(rows)}"
    )


def sheet_output_dir(workspace_path: Path, source: str | Path) -> Path:
    """Return ``reports/thumbnails/<clip-stem>/`` under the workspace."""
    stem = Path(source).stem
    return Path(workspace_path) / "reports" / "thumbnails" / stem


def _total_frames(path: Path) -> int:
    """Best-effort total frame count via ffprobe (0 when unknown)."""
    try:
        asset = probe_media(Path(path))
        if asset.duration and asset.fps:
            return int(asset.duration * asset.fps)
    except Exception as exc:  # noqa: BLE001
        logger.debug("frame-count probe failed for %s: %s", path, exc)
    return 0


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def generate_thumbnail_sheet(
    source: Path,
    out_dir: Path,
    frames: int = 6,
    grid: bool = True,
    width: int = 320,
    dry_run: bool = False,
) -> dict:
    """Extract representative frames (+ optional contact sheet) for *source*.

    Returns a dict with ``success``, ``frame_paths``, ``sheet_path`` (or None),
    ``output_dir``, ``batch``, ``grid_dims`` and the constructed ``commands``.
    """
    source = Path(source)
    out_dir = Path(out_dir)
    frames = max(1, int(frames))

    total = _total_frames(source)
    batch = compute_batch_size(total, frames)
    cols, rows = grid_dimensions(frames)

    frame_pattern = out_dir / "frame_%03d.png"
    frames_cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-vf", build_frames_filter(batch, width),
        "-frames:v", str(frames),
        "-vsync", "vfr",
        str(frame_pattern),
    ]

    sheet_path = out_dir / "sheet.png"
    sheet_cmd = [
        "ffmpeg", "-y", "-i", str(source),
        "-vf", build_sheet_filter(batch, width, cols, rows),
        "-frames:v", "1",
        str(sheet_path),
    ]

    commands = {"frames": frames_cmd}
    if grid:
        commands["sheet"] = sheet_cmd

    base = {
        "success": True,
        "source": str(source),
        "output_dir": str(out_dir),
        "batch": batch,
        "grid_dims": [cols, rows],
        "width": int(width),
        "commands": commands,
    }

    if dry_run:
        base["frame_paths"] = []
        base["sheet_path"] = None
        return base

    out_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(frames_cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return {**base, "success": False,
                "error": f"frame extraction failed: {proc.stderr[-400:]}",
                # Stable machine key (server/errors.py taxonomy) passed through
                # by the bundle. A failed extraction usually means the source
                # is unreadable/unsupported rather than a code fault.
                "error_type": "media_unreadable"}

    frame_paths = sorted(str(p) for p in out_dir.glob("frame_*.png"))

    sheet_out: str | None = None
    if grid:
        sproc = subprocess.run(sheet_cmd, capture_output=True, text=True, check=False)
        if sproc.returncode == 0 and sheet_path.exists():
            sheet_out = str(sheet_path)
        else:
            logger.warning("contact-sheet pass failed: %s", sproc.stderr[-300:])

    return {**base, "frame_paths": frame_paths, "sheet_path": sheet_out}
