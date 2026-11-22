"""Container/codec conversion and audio extraction on plain files (prompt 31).

Audio targets delegate to the existing ``adapters/ffmpeg/audio`` functions
(``convert_format`` for wav/flac, ``export_compressed`` for mp3/m4a/aac/ogg/
opus); video targets use :data:`VIDEO_PRESETS`. VFR -> CFR is
``media_transcode_cfr``'s job, not this module's.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import convert_format, export_compressed
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult, run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_files import has_audio, require_streams

LOSSLESS_AUDIO = (".wav", ".flac")
COMPRESSED_AUDIO = (".mp3", ".m4a", ".aac", ".ogg", ".opus")
VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".webm")

#: (video args, audio args) by preset name; ``crf`` is filled in.
VIDEO_PRESETS = {
    "h264": (["-c:v", "libx264", "-preset", "veryfast", "-crf", "{crf}", "-pix_fmt", "yuv420p"], ["-c:a", "aac"]),
    "vp9": (["-c:v", "libvpx-vp9", "-b:v", "0", "-crf", "{crf}", "-row-mt", "1"], ["-c:a", "libopus"]),
    "prores": (["-c:v", "prores_ks", "-profile:v", "3"], ["-c:a", "pcm_s16le"]),
    "hevc": (["-c:v", "libx265", "-crf", "{crf}", "-tag:v", "hvc1", "-pix_fmt", "yuv420p"], ["-c:a", "aac"]),
}
_DEFAULT_CRF = {"h264": 20, "vp9": 32, "hevc": 24}


def pick_preset(ext: str, preset: str = "") -> str:
    ext = ext.lower()
    if ext not in VIDEO_EXTS:
        raise ValueError(f"unsupported output extension {ext!r}; video: {', '.join(VIDEO_EXTS)}; "
                         f"audio: {', '.join(LOSSLESS_AUDIO + COMPRESSED_AUDIO)}")
    if preset == "prores":
        if ext != ".mov":
            raise ValueError("preset 'prores' needs a .mov output")
        return "prores"
    if preset == "hevc":
        if ext not in (".mp4", ".mkv"):
            raise ValueError("preset 'hevc' needs a .mp4 or .mkv output")
        return "hevc"
    if preset:
        raise ValueError(f"unknown preset {preset!r}; use '', 'prores' or 'hevc'")
    return "vp9" if ext == ".webm" else "h264"


def convert_file(source: Path, output: Path, preset: str = "", crf: int | None = None, max_height: int = 0,
                 audio_bitrate: str = "192k") -> FFmpegResult:
    ext = output.suffix.lower()
    asset = probe_media(source)
    if ext in LOSSLESS_AUDIO + COMPRESSED_AUDIO:
        require_streams(asset, audio=True)
        if ext in LOSSLESS_AUDIO:
            return convert_format(source, output, sample_rate=asset.sample_rate or 48000,
                                  channels=asset.channels or 2)
        return export_compressed(source, output, bitrate=audio_bitrate)
    name = pick_preset(ext, preset)
    require_streams(asset, video=True)
    video, audio = VIDEO_PRESETS[name]
    crf_value = str(crf if crf is not None else _DEFAULT_CRF.get(name, 20))
    args = [a.replace("{crf}", crf_value) for a in video]
    if max_height and asset.height > max_height:
        args = ["-vf", f"scale=-2:{max_height}", *args]
    if has_audio(asset):
        args += audio + (["-b:a", audio_bitrate] if name in ("h264", "hevc", "vp9") else [])
    if ext in (".mp4", ".mov"):
        args += ["-movflags", "+faststart"]
    return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])


def extract_audio_file(source: Path, output: Path, sample_rate: int = 0, channels: int = 0,
                       bitrate: str = "192k") -> FFmpegResult:
    """The sound of *source* as its own file (``.wav`` default). 0 keeps the source's rate / channels."""
    asset = probe_media(source)
    require_streams(asset, audio=True)
    ext = output.suffix.lower()
    if ext in LOSSLESS_AUDIO:
        return convert_format(source, output, sample_rate=sample_rate or asset.sample_rate or 48000,
                              channels=channels or asset.channels or 2)
    if ext in COMPRESSED_AUDIO:
        return export_compressed(source, output, bitrate=bitrate)
    raise ValueError(f"unsupported audio extension {ext!r}; use {', '.join(LOSSLESS_AUDIO + COMPRESSED_AUDIO)}")


