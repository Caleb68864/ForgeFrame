"""Build a jump-cut ``.kdenlive`` timeline from keep-ranges (``timeline_build_jump_cut``)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.utils.naming import slugify
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegCommandError
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.pipelines import silence_cut
from workshop_video_brain.edit_mcp.pipelines.project_profile import profile_from_media
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import build_ranges_project, cut_guides


def _failure(message: str, error_type: str, source: Path) -> dict:
    return {"success": False, "source": str(source), "error": message, "error_type": error_type}


def build_jump_cut(
    workspace_root: Path,
    source: Path,
    *,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
    ranges: list[tuple[float, float]] | None = None,
    add_cut_guides: bool = False,
) -> dict:
    """Write a new versioned working copy playing only the kept parts of *source*.

    Given no *ranges*, they come from :func:`silence_cut.keep_ranges`. An explicit
    list skips detection, and is reported as engine ``"explicit"``.
    """
    source = Path(source)
    try:
        asset = probe_media(source)
    except (FFmpegCommandError, OSError, ValueError) as exc:
        return _failure(f"Could not read {source.name}: {exc}", "media_unreadable", source)
    if not asset.video_codec or not asset.duration or asset.duration <= 0:
        return _failure(f"{source.name} has no video stream to cut.", "media_unreadable", source)

    engine_used = "explicit"
    if ranges is None:
        engine_used, ranges, _duration = silence_cut.keep_ranges(
            source, engine=engine, threshold_db=threshold_db, min_silence=min_silence, margin=margin,
        )
    clamped = [
        (max(0.0, start), min(asset.duration, end))
        for start, end in ranges
        if start < asset.duration and end > 0
    ]
    profile = profile_from_media([source])
    has_audio = bool(asset.audio_codec or asset.channels)
    project = build_ranges_project(
        source.resolve(), clamped,
        profile=profile,
        has_audio=has_audio,
        title=f"Jump Cut {source.stem}",
        source_frames=round(asset.duration * profile.fps),
    )
    video_entries = project.playlists[0].entries
    if not video_entries:
        return _failure("Nothing to keep: no range covers a whole frame.", "invalid_input", source)
    if add_cut_guides:
        project.guides = cut_guides(project)

    slug = slugify(f"jump_cut_{source.stem}") or "jump_cut"
    path = serialize_versioned(project, Path(workspace_root), slug)
    timeline_frames = sum(entry.out_point - entry.in_point + 1 for entry in video_entries)
    return {
        "success": True,
        "kdenlive_path": str(path),
        "engine": engine_used,
        "keep_ranges": [list(item) for item in clamped],
        "kept_seconds": round(timeline_frames / profile.fps, 6),
        "timeline_frames": timeline_frames,
        "profile": {"width": profile.width, "height": profile.height, "fps": profile.fps},
        "audio_placed": has_audio,
    }
