"""``media_gif``: a looping GIF or WebP from any window of a plain video file (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, media_unreadable, operation_failed, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_gif(source: str, start_seconds: float = 0.0, seconds: float = 3.0, fps: int = 12, width: int = 480,
              format: str = "gif", output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """A looping GIF (two-pass palette, good colour) or animated WebP of ``seconds`` from ``start_seconds``.

    The palette is built in a temporary folder. Default output
    ``<name>_<start>s.gif``. For captioned reaction GIFs see ``gif_render``.
    """
    from workshop_video_brain.edit_mcp.pipelines.clip_preview import render_gif_file
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        out = resolve_output(src, output_path, output_dir, suffix=f"_{start_seconds:g}s",
                             ext="." + format.lstrip("."), overwrite=overwrite)
        done = render_gif_file(src, out, start_seconds, seconds, fps, width, fmt=format.lstrip("."))
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), "Check start/seconds against the clip length, fps 1-50, width >= 2.")
    if not done["success"]:
        out.unlink(missing_ok=True)
        return operation_failed("GIF render failed", cause=done["stderr_tail"],
                                suggestion="ffmpeg's message is in 'cause'.")
    return _ok({"output_path": str(out), "size_bytes": out.stat().st_size, "width": done["width"],
                "height": done["height"], "frame_count": done["frame_count"],
                "expected_frame_count": done["expected_frame_count"], "start_seconds": start_seconds,
                "seconds": done["seconds"], "fps": fps})
