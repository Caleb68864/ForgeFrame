"""``media_speed``: play a plain media file faster or slower (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import run_file_tool
from workshop_video_brain.edit_mcp.server.errors import tool_guard


@mcp.tool()
@tool_guard
def media_speed(source: str, factor: float, keep_pitch: bool = True, output_path: str = "",
                output_dir: str = "", overwrite: bool = False) -> dict:
    """Write *source* at ``factor`` x speed (0.25-4.0; 2 = twice as fast).

    The sound keeps its pitch (``atempo``) unless ``keep_pitch=false``, which
    shifts it like a tape. Default output ``<name>_x<factor>``.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_edit import speed_file

    return run_file_tool(source, suffix=f"_x{factor:g}", ext=None, output_path=output_path, output_dir=output_dir,
                         overwrite=overwrite, run=lambda s, o: speed_file(s, o, factor, keep_pitch=keep_pitch),
                         what="Speed change", extra={"factor": factor, "keep_pitch": keep_pitch})
