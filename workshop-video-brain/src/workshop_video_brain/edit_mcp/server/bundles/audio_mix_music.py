"""``audio_mix_music``: a music bed under a voice recording, ducked under speech (plain files)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import invalid_input, media_unreadable, missing_file, tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def audio_mix_music(source: str, music: str, music_gain_db: float = -18.0, duck: bool = True,
                    duck_preset: str = "medium", loop_music: bool = True, music_offset_seconds: float = 0.0,
                    fade_in_seconds: float = 1.0, fade_out_seconds: float = 2.0, output_path: str = "",
                    output_dir: str = "", overwrite: bool = False) -> dict:
    """Lay ``music`` under the voice in ``source`` (an audio file or a video; the picture is copied).

    The music sits at ``music_gain_db`` and, with ``duck``, drops under speech
    (``duck_preset`` light / medium / strong, a side-chain compressor; strong
    measured ~9 dB of ducking). It loops if shorter than the voice, starts at
    ``music_offset_seconds``, and fades in/out. The voice level is untouched.
    For ducking on a timeline project use ``audio_duck``. Default output
    ``<name>_music<ext>``.
    """
    from workshop_video_brain.edit_mcp.pipelines.audio_files import mix_music_file
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output

    src = source_path(source)
    if isinstance(src, dict):
        return src
    bed = Path(music).expanduser() if music else None
    if bed is None or not bed.is_file():
        return missing_file(str(music), "music")
    try:
        out = resolve_output(src, output_path, output_dir, suffix="_music", overwrite=overwrite)
        done = mix_music_file(src, bed.resolve(), out, music_gain_db, duck, duck_preset, loop_music,
                              music_offset_seconds, fade_in_seconds, fade_out_seconds)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(exc).split(": ", 1)[-1], exc)
        return invalid_input(str(exc), "duck_preset is light, medium or strong; check the fades and output format.")
    problem = ffmpeg_ok_or_error(done.pop("result"), out, "Music mix")
    if problem:
        return problem
    return _ok({**output_summary(out), "source": str(src), "music": str(bed), **done})
