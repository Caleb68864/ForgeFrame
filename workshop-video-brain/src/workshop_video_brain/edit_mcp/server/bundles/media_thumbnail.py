"""``media_thumbnail``: one still from a plain video file (no workspace)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, media_unreadable, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_thumbnail(source: str, at_seconds: float = -1.0, width: int = 1280, format: str = "jpg",
                    output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Save one frame as an image: at ``at_seconds`` (clamped to the last frame), or with -1 the most
    representative frame of a 4 s window starting at 10 % of the video (ffmpeg's ``thumbnail`` filter).

    ``width`` 0 keeps the native size. jpg (default), png or webp. For a
    YouTube-style thumbnail with title text use ``thumbnail_generate``.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output
    from workshop_video_brain.edit_mcp.pipelines.media_thumbnail import thumbnail_file

    src = source_path(source)
    if isinstance(src, dict):
        return src
    ext = Path(output_path).suffix if output_path else "." + format.lstrip(".")
    try:
        out = resolve_output(src, output_path, output_dir, suffix="_thumb", ext=ext, overwrite=overwrite)
        done = thumbnail_file(src, out, at_seconds=at_seconds if at_seconds >= 0 else None, width=width)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), "Use format jpg, png or webp and a non-negative width.")
    problem = ffmpeg_ok_or_error(done["result"], out, "Thumbnail")
    if problem:
        return problem
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_frame_geometry
    w, h, _frames = probe_frame_geometry(out)
    return _ok({"output_path": str(out), "width": w, "height": h, "size_bytes": out.stat().st_size,
                "mode": done["mode"], "at_seconds": done["at_seconds"],
                "searched_from_seconds": done["searched_from_seconds"]})
