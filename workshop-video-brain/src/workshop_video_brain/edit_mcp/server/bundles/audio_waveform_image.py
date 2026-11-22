"""``audio_waveform_image``: a PNG waveform of a plain file's audio (no workspace)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, media_unreadable, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def audio_waveform_image(source: str, width: int = 1600, height: int = 300, color: str = "0x3399ff",
                         split_channels: bool = False, start_seconds: float = 0.0, duration_seconds: float = -1.0,
                         output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Draw the audio waveform as an image (64-8000 px each way; png or jpg).

    Handy for spotting silence or clipping, or for a thumbnail. ``color`` is
    0xRRGGBB[AA] or a colour name; ``split_channels`` draws each channel
    separately. Default output ``<name>_waveform.png``.
    """
    from workshop_video_brain.edit_mcp.pipelines.audio_files import waveform_image
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        ext = Path(output_path).suffix if output_path else ".png"
        out = resolve_output(src, output_path, output_dir, suffix="_waveform", ext=ext, overwrite=overwrite)
        done = waveform_image(src, out, width, height, color, split_channels, start_seconds,
                              duration_seconds if duration_seconds > 0 else None)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), "width/height 64-8000, color 0xRRGGBB or a name, output .png or .jpg.")
    problem = ffmpeg_ok_or_error(done["result"], out, "Waveform")
    if problem:
        return problem
    return _ok({"output_path": str(out), "width": done["width"], "height": done["height"],
                "size_bytes": out.stat().st_size, "source": str(src)})
