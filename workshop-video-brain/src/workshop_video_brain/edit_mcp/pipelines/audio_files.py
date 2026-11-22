"""Audio operations on plain files: music beds with ducking, fades (prompt 34; 35 adds more).

File-level counterparts of the timeline tools ``audio_duck`` (keyframes on a
project) and ``audio_fade`` (a timeline clip fade). Same vocabulary:
ducking depth via a compressor ``ratio``, ``attack`` / ``release`` in ms.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_files import has_video, require_streams

DUCK_PRESETS = {
    "light": {"threshold": 0.02, "ratio": 4, "attack": 20, "release": 400},
    "medium": {"threshold": 0.02, "ratio": 8, "attack": 20, "release": 300},
    "strong": {"threshold": 0.02, "ratio": 20, "attack": 20, "release": 250},
}
FADE_CURVES = ("tri", "qsin", "esin", "hsin", "log", "exp")
_AUDIO_CODECS = {".wav": ["-c:a", "pcm_s16le"], ".m4a": ["-c:a", "aac", "-b:a", "192k"],
                 ".aac": ["-c:a", "aac", "-b:a", "192k"], ".mp3": ["-c:a", "libmp3lame", "-b:a", "192k"],
                 ".flac": ["-c:a", "flac"], ".ogg": ["-c:a", "libvorbis"], ".opus": ["-c:a", "libopus"]}


def audio_codec_args(ext: str) -> list[str]:
    try:
        return _AUDIO_CODECS[ext.lower()]
    except KeyError:
        raise ValueError(f"unsupported audio output {ext!r}; use {', '.join(_AUDIO_CODECS)}") from None


def build_mix_graph(music_gain_db: float, duck: bool, preset: str, loop_music: bool, music_offset: float,
                    fade_in: float, fade_out: float, out_duration: float) -> str:
    """Filtergraph: input 0 = voice, input 1 = music; output label ``[out]``.

    ``amix ... normalize=0`` keeps the voice at its level (amix otherwise halves
    both inputs). ``loop_music`` adds ``aloop`` -- which buffers the whole
    music -- so the caller sets it only when the music is shorter than the voice.
    """
    if preset not in DUCK_PRESETS:
        raise ValueError(f"duck_preset must be one of {', '.join(DUCK_PRESETS)}, got {preset!r}")
    music = []
    if loop_music:
        music.append("aloop=loop=-1:size=2147483647")
    music += [f"atrim=start={music_offset:.3f}", "asetpts=PTS-STARTPTS", "aresample=48000",
              "aformat=channel_layouts=stereo", f"volume={music_gain_db:g}dB"]
    if fade_in > 0:
        music.append(f"afade=t=in:d={fade_in:.3f}")
    if fade_out > 0:
        music.append(f"afade=t=out:st={max(0.0, out_duration - fade_out):.3f}:d={fade_out:.3f}")
    parts = ["[1:a]" + ",".join(music) + "[m]"]
    if duck:
        p = DUCK_PRESETS[preset]
        parts.append("[0:a]aresample=48000,aformat=channel_layouts=stereo,asplit=2[v][sc]")
        parts.append(f"[m][sc]sidechaincompress=threshold={p['threshold']}:ratio={p['ratio']}:"
                     f"attack={p['attack']}:release={p['release']}[d]")
        parts.append("[v][d]amix=inputs=2:duration=first:normalize=0[out]")
    else:
        parts.append("[0:a]aresample=48000,aformat=channel_layouts=stereo[v]")
        parts.append("[v][m]amix=inputs=2:duration=first:normalize=0[out]")
    return ";".join(parts)


def mix_music_file(source: Path, music: Path, output: Path, music_gain_db: float = -18.0, duck: bool = True,
                   duck_preset: str = "medium", loop_music: bool = True, music_offset: float = 0.0,
                   fade_in: float = 1.0, fade_out: float = 2.0) -> dict:
    voice, bed = probe_media(source), probe_media(music)
    require_streams(voice, audio=True)
    require_streams(bed, audio=True)
    duration = voice.duration_seconds or 0.0
    needs_loop = loop_music and (bed.duration_seconds or 0.0) - music_offset < duration
    graph = build_mix_graph(music_gain_db, duck, duck_preset, needs_loop, music_offset, fade_in, fade_out, duration)
    if has_video(voice):
        maps = ["-map", "0:v", "-map", "[out]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    else:
        maps = ["-map", "[out]", *audio_codec_args(output.suffix)]
    result = run_ffmpeg(["-filter_complex", graph, *maps, "-t", f"{duration:.3f}"], source, output, overwrite=True,
                        pre_input_args=["-hide_banner"], extra_inputs=[music])
    return {"result": result, "ducked": duck, "preset": duck_preset if duck else None,
            "music_gain_db": music_gain_db, "music_looped": needs_loop, "graph": graph}


def fade_filter(duration: float, fade_in: float, fade_out: float, curve: str = "tri") -> str:
    if curve not in FADE_CURVES:
        raise ValueError(f"curve must be one of {', '.join(FADE_CURVES)}, got {curve!r}")
    if fade_in < 0 or fade_out < 0 or (fade_in == 0 and fade_out == 0):
        raise ValueError("give a fade_in and/or fade_out longer than 0")
    if duration and fade_in + fade_out > duration:
        raise ValueError(f"fades ({fade_in + fade_out:.2f}s) are longer than the file ({duration:.2f}s)")
    parts = []
    if fade_in > 0:
        parts.append(f"afade=t=in:st=0:d={fade_in:.3f}:curve={curve}")
    if fade_out > 0:
        parts.append(f"afade=t=out:st={duration - fade_out:.3f}:d={fade_out:.3f}:curve={curve}")
    return ",".join(parts)


def fade_file(source: Path, output: Path, fade_in: float = 0.0, fade_out: float = 0.0, curve: str = "tri") -> dict:
    asset = probe_media(source)
    require_streams(asset, audio=True)
    af = fade_filter(asset.duration_seconds or 0.0, fade_in, fade_out, curve)
    if has_video(asset):
        args = ["-c:v", "copy", "-af", af, "-c:a", "aac", "-b:a", "192k"]
    else:
        args = ["-vn", "-af", af, *audio_codec_args(output.suffix)]
    result = run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])
    return {"result": result, "fade_in": fade_in, "fade_out": fade_out, "curve": curve}
