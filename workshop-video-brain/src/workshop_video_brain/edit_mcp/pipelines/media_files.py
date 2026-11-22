"""Shared helpers for tools that work on plain media files (no workspace).

Phase 5 tools lead with ``source``, write to ``output_path`` / ``output_dir``,
and never write into ``media/raw/`` or ``projects/source/`` -- not even a new
file (stricter than ``run_ffmpeg``, which only refuses to overwrite there).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.utils.paths import assert_not_protected

#: House defaults for re-encodes.
ENCODE_VIDEO_ARGS = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]
ENCODE_AUDIO_ARGS = ["-c:a", "aac", "-b:a", "192k"]


def default_output_dir(source: Path) -> Path:
    """``<ws>/media/processed/`` for a source under ``<ws>/media/raw/``, else the source's folder."""
    source = Path(source).resolve()
    parts = source.parts
    for i in range(len(parts) - 1, 0, -1):
        if parts[i] == "raw" and parts[i - 1] == "media":
            return Path(*parts[:i]) / "processed"
    return source.parent


def resolve_output(
    source: Path,
    output_path: str = "",
    output_dir: str = "",
    suffix: str = "_out",
    ext: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Where a tool writes its result. Absolute ``output_path`` is preferred (relative = current dir)."""
    source = Path(source)
    if output_path:
        result = Path(output_path)
    else:
        folder = Path(output_dir) if output_dir else default_output_dir(source)
        result = folder / f"{source.stem}{suffix}{ext or source.suffix}"
    result = result.resolve()
    assert_not_protected(result, "media output")
    if source.exists() and result == source.resolve():
        raise ValueError(f"The output would overwrite the source: {result}. Choose another output_path.")
    if result.exists() and not overwrite:
        raise ValueError(f"The output already exists: {result}. Pass overwrite=true to replace it.")
    result.parent.mkdir(parents=True, exist_ok=True)
    return result


def has_audio(asset) -> bool:
    return bool(getattr(asset, "channels", 0) or getattr(asset, "audio_codec", ""))


def has_video(asset) -> bool:
    return bool(getattr(asset, "width", 0))


def require_streams(asset, *, video: bool = False, audio: bool = False) -> None:
    if video and not has_video(asset):
        raise ValueError(f"source has no video stream: {asset.path}")
    if audio and not has_audio(asset):
        raise ValueError(f"source has no audio stream: {asset.path}")


def output_summary(path: Path) -> dict:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    asset = probe_media(Path(path))
    return {
        "output_path": str(path),
        "duration_seconds": round(asset.duration_seconds or 0.0, 3),
        "width": asset.width,
        "height": asset.height,
        "fps": asset.fps,
        "has_audio": has_audio(asset),
        "sample_rate": asset.sample_rate,
        "channels": asset.channels,
        "size_bytes": Path(path).stat().st_size,
    }
