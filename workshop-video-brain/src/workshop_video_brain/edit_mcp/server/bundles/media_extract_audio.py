"""``media_extract_audio``: pull the sound out of a plain media file (no workspace)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import run_file_tool
from workshop_video_brain.edit_mcp.server.errors import tool_guard


@mcp.tool()
@tool_guard
def media_extract_audio(source: str, format: str = "wav", sample_rate: int = 0, channels: int = 0,
                        bitrate: str = "192k", output_path: str = "", output_dir: str = "",
                        overwrite: bool = False) -> dict:
    """Save the audio of *source* as its own file (wav default; flac, mp3, m4a, aac, ogg, opus).

    ``sample_rate`` / ``channels`` 0 keep the source's; ``bitrate`` is for the
    compressed formats. A file with no audio stream is refused.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_convert import extract_audio_file

    ext = Path(output_path).suffix if output_path else "." + format.lstrip(".")
    return run_file_tool(source, suffix="_audio", ext=ext, output_path=output_path, output_dir=output_dir,
                         overwrite=overwrite,
                         run=lambda s, o: extract_audio_file(s, o, sample_rate=sample_rate, channels=channels,
                                                             bitrate=bitrate),
                         what="Audio extraction")
