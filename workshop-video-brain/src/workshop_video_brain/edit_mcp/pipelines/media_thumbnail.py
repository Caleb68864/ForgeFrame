"""One still from a plain video file: at a time, or the most representative frame (prompt 32).

For a thumbnail with title text use ``thumbnail_generate`` (workspace tool).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_files import require_streams

_FORMAT_ARGS = {".png": [], ".jpg": ["-q:v", "2"], ".jpeg": ["-q:v", "2"], ".webp": ["-c:v", "libwebp", "-quality", "85"]}


def thumbnail_args(at_seconds: float | None, width: int, fps: float, window_seconds: float, ext: str) -> list[str]:
    """Output args: a scale (``width`` 0 = native), the ``thumbnail`` picker in auto mode, one frame."""
    if ext.lower() not in _FORMAT_ARGS:
        raise ValueError(f"unsupported image format {ext!r}; use .png, .jpg or .webp")
    filters = []
    if at_seconds is None:
        filters.append(f"thumbnail=n={max(1, round(window_seconds * (fps or 25)))}")
    if width:
        filters.append(f"scale={width}:-2")
    return (["-vf", ",".join(filters)] if filters else []) + ["-frames:v", "1", *_FORMAT_ARGS[ext.lower()]]


def thumbnail_file(source: Path, output: Path, at_seconds: float | None = None, width: int = 1280,
                   window_seconds: float = 4.0) -> dict:
    asset = probe_media(source)
    require_streams(asset, video=True)
    duration, fps = asset.duration_seconds or 0.0, asset.fps or 25.0
    if at_seconds is not None:
        # Seeking into the very last frame can decode nothing (ffmpeg writes no
        # packet); stay a few frames clear of the end.
        last = max(0.0, duration - max(3.0 / fps, 0.1)) if duration > 0 else at_seconds
        seek = min(max(0.0, at_seconds), last)
        searched = None
    else:
        seek = searched = round(0.1 * duration, 3)
    result = run_ffmpeg(thumbnail_args(at_seconds, width, fps, window_seconds, output.suffix), source, output,
                        overwrite=True, pre_input_args=["-hide_banner", "-ss", f"{seek:.3f}"])
    return {"result": result, "mode": "at" if at_seconds is not None else "auto",
            "at_seconds": round(seek, 3) if at_seconds is not None else None, "searched_from_seconds": searched}
