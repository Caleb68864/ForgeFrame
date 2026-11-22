"""``audio_fade_file``: fade a plain file's audio in and/or out (``audio_fade`` is the timeline tool)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import run_file_tool
from workshop_video_brain.edit_mcp.server.errors import tool_guard


@mcp.tool()
@tool_guard
def audio_fade_file(source: str, fade_in_seconds: float = 0.0, fade_out_seconds: float = 0.0, curve: str = "tri",
                    output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Fade the audio of a file in and/or out (``curve``: tri, qsin, esin, hsin, log, exp).

    A video's picture is copied untouched. For a fade on a timeline clip use
    ``audio_fade``. Default output ``<name>_faded<ext>``.
    """
    from workshop_video_brain.edit_mcp.pipelines.audio_files import fade_file

    holder = {}

    def run(src, out):
        done = fade_file(src, out, fade_in_seconds, fade_out_seconds, curve)
        holder.update({k: v for k, v in done.items() if k != "result"})
        return done["result"]

    result = run_file_tool(source, suffix="_faded", ext=None, output_path=output_path, output_dir=output_dir,
                           overwrite=overwrite, run=run, what="Fade")
    if result.get("status") == "success":
        result["data"].update(holder)
    return result
