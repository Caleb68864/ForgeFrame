"""``media_trim``: cut a range out of a plain media file (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_trim(
    source: str,
    start_seconds: float,
    end_seconds: float = -1.0,
    duration_seconds: float = -1.0,
    mode: str = "accurate",
    output_path: str = "",
    output_dir: str = "",
    overwrite: bool = False,
) -> dict:
    """Cut a range out of a media file into a new file.

    Give ``end_seconds`` or ``duration_seconds`` (-1 = unset; neither = to the
    end). ``mode="accurate"`` re-encodes and is frame exact; ``"copy"`` is
    fast but snaps to keyframes. Output: ``output_path``, or
    ``<output_dir>/<name>_trim<ext>``; by default beside the source, or in
    ``media/processed/`` for a source in ``media/raw/`` (never written).
    """
    from workshop_video_brain.edit_mcp.pipelines.media_edit import trim_file
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        out = resolve_output(src, output_path, output_dir, suffix="_trim", overwrite=overwrite)
        result = trim_file(src, out, start_seconds,
                           end=end_seconds if end_seconds >= 0 else None,
                           duration=duration_seconds if duration_seconds >= 0 else None, mode=mode)
    except ValueError as exc:
        return invalid_input(str(exc), "Check the times against the file's duration and the output options.")
    problem = ffmpeg_ok_or_error(result, out, "Trim")
    if problem:
        return problem
    return _ok({**output_summary(out), "source": str(src), "mode": mode})
