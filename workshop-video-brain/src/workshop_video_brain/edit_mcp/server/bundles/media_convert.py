"""``media_convert``: change a plain media file's container and codecs (no workspace)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import run_file_tool
from workshop_video_brain.edit_mcp.server.errors import tool_guard


@mcp.tool()
@tool_guard
def media_convert(source: str, format: str = "mp4", preset: str = "", crf: int = -1, max_height: int = 0,
                  audio_bitrate: str = "192k", output_path: str = "", output_dir: str = "",
                  overwrite: bool = False) -> dict:
    """Convert to another container/codec, picked by the output extension (``output_path`` wins over ``format``).

    Video: mp4/mkv/mov = H.264 + AAC (crf 20; ``preset="hevc"`` = H.265 for
    mp4/mkv; ``preset="prores"`` = ProRes HQ + PCM for mov), webm = VP9 + Opus.
    ``max_height`` scales a taller source down. Audio: wav/flac keep the
    source's rate and channels; mp3/m4a/aac/ogg/opus at ``audio_bitrate``.
    For variable-frame-rate phone footage use ``media_transcode_cfr``.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_convert import convert_file

    ext = Path(output_path).suffix if output_path else "." + format.lstrip(".")
    return run_file_tool(source, suffix="_converted", ext=ext, output_path=output_path, output_dir=output_dir,
                         overwrite=overwrite,
                         run=lambda s, o: convert_file(s, o, preset=preset, crf=crf if crf >= 0 else None,
                                                       max_height=max_height, audio_bitrate=audio_bitrate),
                         what="Conversion", extra={"preset": preset or "default"})
