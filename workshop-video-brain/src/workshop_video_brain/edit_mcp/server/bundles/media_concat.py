"""``media_concat``: join plain media files end to end (no workspace)."""
from __future__ import annotations

import json

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import bad_json_param, invalid_input, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def media_concat(
    sources: str,
    output_path: str = "",
    output_dir: str = "",
    method: str = "auto",
    width: int = 0,
    height: int = 0,
    fps: float = 0.0,
    overwrite: bool = False,
) -> dict:
    """Join media files end to end into one file.

    ``sources`` is a JSON list of paths, in order. ``method="auto"`` stream-
    copies when every file has the same codecs, size, rate and audio format,
    else re-encodes to the first file's geometry (or ``width``/``height``/
    ``fps``) with 48 kHz stereo audio; a file without audio gets silence.
    Default output: ``<first name>_concat`` beside the first file (``.mp4``
    when re-encoding).
    """
    try:
        items = json.loads(sources)
    except (TypeError, json.JSONDecodeError):
        return bad_json_param("sources", '["a.mp4", "b.mp4"]', str(sources))
    if not isinstance(items, list) or len(items) < 2:
        return invalid_input("sources must be a JSON list of at least two files",
                             'Pass e.g. ["a.mp4", "b.mp4"].', param="sources")
    paths = []
    for item in items:
        path = source_path(str(item), "sources")
        if isinstance(path, dict):
            return path
        paths.append(path)
    try:
        return _concat(paths, output_path, output_dir, method, width, height, fps, overwrite)
    except ValueError as exc:
        return invalid_input(str(exc), "Check the method and the files (re-encode needs video in each file).")


def _concat(paths, output_path, output_dir, method, width, height, fps, overwrite) -> dict:
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    from workshop_video_brain.edit_mcp.pipelines.media_edit import _signature, concat_files
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output

    will_copy = method == "copy" or (method == "auto" and not (width or height or fps)
                                     and len({_signature(probe_media(p)) for p in paths}) == 1)
    out = resolve_output(paths[0], output_path, output_dir, suffix="_concat",
                         ext=None if will_copy else ".mp4", overwrite=overwrite)
    done = concat_files(paths, out, method=method, width=width, height=height, fps=fps)
    problem = ffmpeg_ok_or_error(done["result"], out, "Concat")
    if problem:
        return problem
    return _ok({**output_summary(out), "sources": [str(p) for p in paths], "method": done["method"],
                "target": done["target"]})
