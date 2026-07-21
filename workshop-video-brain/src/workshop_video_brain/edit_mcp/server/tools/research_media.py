"""Read-only visual-research media tools: probe, frame extraction, scene detect.

Thin shells over the ``edit_mcp/adapters/ffmpeg`` adapters (``probe_media``,
``extract_frame``, ``extract_frame_burst``, ``detect_scene_changes``). No
mutation of project/workspace state -- these tools only read source media and
optionally write extracted frame images.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (
    tool_guard,
    missing_file,
    missing_binary,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegNotFound,
    FFmpegTimeout,
    FFmpegCommandError,
)


@mcp.tool()
@tool_guard
def research_probe_video(video_path: str) -> dict:
    """Probe a video file and return its media metadata.

    Args:
        video_path: Path to the source video file.

    Returns:
        MediaAsset fields as a dict: duration, streams, vfr flag, geometry.
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    try:
        asset = probe_media(path)
    except FFmpegNotFound as exc:
        return missing_binary("ffprobe", str(exc))
    except (FFmpegTimeout, FFmpegCommandError) as exc:
        return from_exception(exc)

    return _ok(asset.model_dump(mode="json"))


@mcp.tool()
@tool_guard
def research_extract_frame(
    video_path: str,
    timestamp_seconds: float,
    output_path: str | None = None,
    quality: str = "high",
    fmt: str = "png",
) -> dict:
    """Extract a single frame from a video at a given timestamp.

    Args:
        video_path: Path to the source video file.
        timestamp_seconds: Timestamp to extract, in seconds.
        output_path: Optional explicit output image path.
        quality: "high" (accurate seek) or "fast" (keyframe seek).
        fmt: Output image format (e.g. "png").

    Returns:
        FrameCandidate as a dict, including the actual extracted timestamp.
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.frames import extract_frame
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media

    clamped_timestamp = timestamp_seconds
    try:
        asset = probe_media(path)
        if asset.duration_seconds > 0:
            frame_span = (1.0 / asset.fps) if asset.fps > 0 else 0.04
            last_valid = max(0.0, asset.duration_seconds - frame_span)
            if clamped_timestamp > last_valid:
                clamped_timestamp = last_valid
        if clamped_timestamp < 0:
            clamped_timestamp = 0.0
    except (FFmpegNotFound, FFmpegTimeout, FFmpegCommandError):
        pass

    out = Path(output_path) if output_path else None
    try:
        candidate = extract_frame(
            path,
            clamped_timestamp,
            output_path=out,
            quality=quality,
            fmt=fmt,
        )
    except FFmpegNotFound as exc:
        return missing_binary("ffmpeg", str(exc))
    except FFmpegTimeout as exc:
        return from_exception(exc)
    except RuntimeError as exc:
        return from_exception(exc)

    data = candidate.model_dump(mode="json")
    data["actual_timestamp_seconds"] = candidate.timestamp_seconds
    return _ok(data)


@mcp.tool()
@tool_guard
def research_extract_frame_burst(
    video_path: str,
    start_seconds: float,
    end_seconds: float,
    interval_seconds: float = 0.5,
    max_frames: int = 20,
) -> dict:
    """Extract a uniform burst of frames across a time range.

    Args:
        video_path: Path to the source video file.
        start_seconds: Start of the burst range, in seconds.
        end_seconds: End of the burst range, in seconds.
        interval_seconds: Nominal spacing between extracted frames.
        max_frames: Maximum number of frames to extract.

    Returns:
        List of FrameCandidate dicts, chronologically ordered.
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.frames import extract_frame_burst

    try:
        candidates = extract_frame_burst(
            path,
            start_seconds,
            end_seconds,
            interval_seconds=interval_seconds,
            max_frames=max_frames,
        )
    except FFmpegNotFound as exc:
        return missing_binary("ffmpeg", str(exc))
    except FFmpegTimeout as exc:
        return from_exception(exc)
    except RuntimeError as exc:
        return from_exception(exc)

    return _ok({
        "frames": [c.model_dump(mode="json") for c in candidates],
        "count": len(candidates),
    })


@mcp.tool()
@tool_guard
def research_detect_scenes(
    video_path: str,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    threshold: float = 0.30,
    minimum_gap_seconds: float = 1.0,
) -> dict:
    """Detect scene changes in a video, optionally within a time range.

    Args:
        video_path: Path to the source video file.
        start_seconds: Inclusive start of the range to analyze.
        end_seconds: Exclusive end of the range to analyze.
        threshold: ffmpeg ``scene`` filter score threshold (0.0-1.0).
        minimum_gap_seconds: Minimum spacing enforced between detections.

    Returns:
        List of scene-change dicts (timestamp_seconds, score), possibly empty.
    """
    path = Path(video_path)
    if not path.exists():
        return missing_file(video_path, "video_path")

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import detect_scene_changes

    try:
        changes = detect_scene_changes(
            path,
            start_seconds=start_seconds,
            end_seconds=end_seconds,
            threshold=threshold,
            minimum_gap_seconds=minimum_gap_seconds,
        )
    except FFmpegNotFound as exc:
        return missing_binary("ffmpeg", str(exc))
    except FFmpegTimeout as exc:
        return from_exception(exc)

    return _ok({
        "scenes": [c.model_dump(mode="json") for c in changes],
        "count": len(changes),
    })
