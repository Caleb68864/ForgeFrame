"""``media_reframe``: vertical / square / 4:5 versions of a plain video file (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, media_unreadable, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_reframe(source: str, aspect: str = "9:16", mode: str = "smart", focus_x: float = 0.5,
                  focus_y: float = 0.5, height: int = 0, start_seconds: float = 0.0,
                  duration_seconds: float = -1.0, pad_color: str = "black", output_path: str = "",
                  output_dir: str = "", overwrite: bool = False) -> dict:
    """Reframe to ``aspect`` 9:16, 1:1, 4:5 or 16:9.

    Modes: ``smart`` crops around where the motion and detail are (static
    focus, picked automatically); ``crop`` crops around ``focus_x``/``focus_y``
    (0-1; look at a frame from ``media_thumbnail`` first); ``pad`` letterboxes
    in ``pad_color``; ``blur`` fills the bars with a blurred copy. ``height``
    0 = 1920 for 9:16, 1080 for 1:1. A window (``start_seconds``,
    ``duration_seconds``) renders only that part. Default output
    ``<name>_9x16.mp4``.
    """
    from workshop_video_brain.edit_mcp.pipelines._common import check_unit_interval
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output
    from workshop_video_brain.edit_mcp.pipelines.reframe import ASPECTS, MODES, reframe_file

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        if aspect not in ASPECTS:
            raise ValueError(f"aspect must be one of {', '.join(ASPECTS)}, got {aspect!r}")
        if mode not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}, got {mode!r}")
        check_unit_interval("focus_x", focus_x)
        check_unit_interval("focus_y", focus_y)
        out = resolve_output(src, output_path, output_dir, suffix="_" + aspect.replace(":", "x"), ext=".mp4",
                             overwrite=overwrite)
        done = reframe_file(src, out, aspect, mode, focus_x, focus_y, height, start_seconds,
                            duration_seconds if duration_seconds > 0 else None, pad_color)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), "aspect 9:16|1:1|4:5|16:9, mode smart|crop|pad|blur, focus in 0-1.")
    problem = ffmpeg_ok_or_error(done["result"], out, "Reframe")
    if problem:
        return problem
    return _ok({**output_summary(out), "source": str(src), "aspect": aspect, "mode": done["mode"],
                "focus_x": done["focus_x"], "focus_y": done["focus_y"], "crop": done["crop"]})
