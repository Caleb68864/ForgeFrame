"""``media_rotate_flip``: rotate or mirror the picture of a plain media file (no workspace)."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import run_file_tool
from workshop_video_brain.edit_mcp.server.errors import tool_guard


@mcp.tool()
@tool_guard
def media_rotate_flip(source: str, rotate: int = 0, flip: str = "", output_path: str = "",
                      output_dir: str = "", overwrite: bool = False) -> dict:
    """Rotate clockwise (``rotate`` 90/180/270) and/or mirror (``flip`` horizontal/vertical/both).

    ffmpeg already honours a phone clip's rotation tag on input; the output's
    tag is reset so players do not turn it twice. Audio is copied.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_edit import rotate_flip_file

    return run_file_tool(source, suffix="_rotated" if rotate else "_flipped", ext=None, output_path=output_path,
                         output_dir=output_dir, overwrite=overwrite,
                         run=lambda s, o: rotate_flip_file(s, o, rotate=rotate, flip=flip),
                         what="Rotate/flip", extra={"rotate": rotate, "flip": flip})
