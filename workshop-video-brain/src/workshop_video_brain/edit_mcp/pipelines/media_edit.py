"""Edits on plain media files: trim and concat (more added by prompts 31-32)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import FFmpegResult, run_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.media_files import (
    ENCODE_AUDIO_ARGS,
    ENCODE_VIDEO_ARGS,
    has_audio,
    has_video,
)


def _fmt(seconds: float) -> str:
    return f"{seconds:.3f}"


def trim_file(
    source: Path,
    output: Path,
    start: float,
    end: float | None = None,
    duration: float | None = None,
    mode: str = "accurate",
    dry_run: bool = False,
) -> FFmpegResult:
    """Cut ``[start, end)`` (or ``start`` + ``duration``, or to the end) out of *source*.

    ``accurate`` re-encodes (input seek + re-encode is frame accurate);
    ``copy`` stream-copies and therefore snaps to keyframes.
    """
    if mode not in ("accurate", "copy"):
        raise ValueError(f"mode must be 'accurate' or 'copy', got {mode!r}")
    if start < 0:
        raise ValueError(f"start must be >= 0, got {start}")
    if end is not None and duration is not None:
        raise ValueError("Give end or duration, not both.")
    asset = probe_media(source)
    total = asset.duration_seconds or 0.0
    if total and start >= total:
        raise ValueError(f"start {start:.3f}s is past the end of the source ({total:.3f}s)")
    if end is not None:
        if end <= start:
            raise ValueError(f"end ({end}) must be after start ({start})")
        duration = end - start
    if duration is not None and duration <= 0:
        raise ValueError(f"duration must be > 0, got {duration}")
    length = ["-t", _fmt(duration)] if duration is not None else []
    if mode == "copy":
        args = [*length, "-c", "copy", "-avoid_negative_ts", "make_zero"]
    else:
        args = [*length]
        if has_video(asset):
            args += ENCODE_VIDEO_ARGS
        if has_audio(asset):
            args += ENCODE_AUDIO_ARGS
    return run_ffmpeg(args, source, output, overwrite=True, dry_run=dry_run,
                      pre_input_args=["-hide_banner", "-ss", _fmt(start)])


def concat_list_text(sources: list[Path]) -> str:
    """The concat demuxer's list file: ``file '<path>'`` lines, with ``'`` escaped as ``'\\''``."""
    return "".join("file '" + str(Path(s)).replace("'", "'\\''") + "'\n" for s in sources)


def build_concat_graph(inputs: list[dict], width: int, height: int, fps: float) -> tuple[str, bool]:
    """Filtergraph normalising every input to ``width x height @ fps`` + 48 kHz stereo, then concat.

    ``inputs``: ``[{"has_audio": bool, "duration": float}]`` per input.
    Returns ``(graph, with_audio)``; a silent input gets ``anullsrc`` of its
    duration, and if no input has audio the concat has no audio at all.
    """
    with_audio = any(i["has_audio"] for i in inputs)
    parts, labels = [], []
    for n, item in enumerate(inputs):
        parts.append(f"[{n}:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                     f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps:g},format=yuv420p[v{n}]")
        labels.append(f"[v{n}]")
        if with_audio:
            if item["has_audio"]:
                parts.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo[a{n}]")
            else:
                parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={item['duration']:.3f}[a{n}]")
            labels.append(f"[a{n}]")
    parts.append("".join(labels) + f"concat=n={len(inputs)}:v=1:a={1 if with_audio else 0}"
                 + ("[v][a]" if with_audio else "[v]"))
    return ";".join(parts), with_audio


def _signature(asset) -> tuple:
    return (asset.video_codec, asset.width, asset.height, round(asset.fps or 0, 3),
            asset.audio_codec, asset.sample_rate, asset.channels)


def concat_files(
    sources: list[Path],
    output: Path,
    method: str = "auto",
    width: int = 0,
    height: int = 0,
    fps: float = 0.0,
) -> dict:
    """Join *sources* end to end. ``copy`` (concat demuxer) needs identical streams; ``reencode`` normalises."""
    if len(sources) < 2:
        raise ValueError("concat needs at least two sources")
    if method not in ("auto", "copy", "reencode"):
        raise ValueError(f"method must be auto, copy or reencode, got {method!r}")
    assets = [probe_media(Path(s)) for s in sources]
    same = len({_signature(a) for a in assets}) == 1
    if method == "auto":
        method = "copy" if same and not (width or height or fps) else "reencode"
    if method == "copy":
        if not same:
            raise ValueError("copy needs every source to share codecs, size, frame rate and audio format; "
                             "use method='reencode'")
        with tempfile.TemporaryDirectory(prefix="wvb_concat_") as tmp:
            listing = Path(tmp) / "list.txt"
            listing.write_text(concat_list_text(sources), encoding="utf-8")
            result = run_ffmpeg(["-c", "copy"], listing, output, overwrite=True,
                                pre_input_args=["-hide_banner", "-f", "concat", "-safe", "0"])
        return {"method": "copy", "target": None, "result": result}
    if any(not has_video(a) for a in assets):
        raise ValueError("reencode concat needs video in every source; an audio-only file cannot be joined "
                         "here (convert it to video first, or join audio files with an audio tool)")
    first = assets[0]
    w, h = width or first.width, height or first.height
    w, h = w - w % 2, h - h % 2
    rate = fps or first.fps or 25.0
    graph, with_audio = build_concat_graph(
        [{"has_audio": has_audio(a), "duration": a.duration_seconds or 0.0} for a in assets], w, h, rate)
    args = ["-filter_complex", graph, "-map", "[v]"]
    if with_audio:
        args += ["-map", "[a]"]
    args += ENCODE_VIDEO_ARGS + (ENCODE_AUDIO_ARGS if with_audio else [])
    result = run_ffmpeg(args, Path(sources[0]), output, overwrite=True, pre_input_args=["-hide_banner"],
                        extra_inputs=[Path(s) for s in sources[1:]])
    return {"method": "reencode", "target": {"width": w, "height": h, "fps": rate, "audio": with_audio},
            "result": result}


# ---------------------------------------------------------------------------
# speed, rotate / flip (prompt 31)
# ---------------------------------------------------------------------------

def atempo_chain(factor: float) -> str:
    """``atempo`` stages (each within [0.5, 2.0]) whose product is *factor*."""
    if not 0.25 <= factor <= 4.0:
        raise ValueError(f"speed factor must be between 0.25 and 4.0, got {factor}")
    stages = []
    remaining = float(factor)
    while remaining > 2.0:
        stages.append(2.0)
        remaining /= 2.0
    while remaining < 0.5:
        stages.append(0.5)
        remaining /= 0.5
    stages.append(remaining)
    return ",".join(f"atempo={s:.6g}" for s in stages)


def speed_file(source: Path, output: Path, factor: float, keep_pitch: bool = True) -> FFmpegResult:
    """Play *source* at *factor* x (0.25-4.0). Audio keeps its pitch unless ``keep_pitch=False``."""
    atempo = atempo_chain(factor)
    asset = probe_media(source)
    graph, maps = [], []
    if has_video(asset):
        graph.append(f"[0:v]setpts=PTS/{factor:.6g}[v]")
        maps += ["-map", "[v]"]
    if has_audio(asset):
        if keep_pitch:
            chain = atempo
        else:
            rate = asset.sample_rate or 48000
            chain = f"asetrate={int(round(rate * factor))},aresample={rate}"
        graph.append(f"[0:a]{chain}[a]")
        maps += ["-map", "[a]"]
    if not graph:
        raise ValueError("source has no video or audio stream")
    args = ["-filter_complex", ";".join(graph), *maps]
    args += (ENCODE_VIDEO_ARGS if has_video(asset) else []) + (ENCODE_AUDIO_ARGS if has_audio(asset) else [])
    return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])


def rotate_flip_filter(rotate: int = 0, flip: str = "") -> str:
    """The ``-vf`` chain for a clockwise rotation (0/90/180/270) and/or a flip."""
    turns = {0: [], 90: ["transpose=1"], 180: ["hflip", "vflip"], 270: ["transpose=2"]}
    flips = {"": [], "horizontal": ["hflip"], "vertical": ["vflip"], "both": ["hflip", "vflip"]}
    if rotate not in turns:
        raise ValueError(f"rotate must be 0, 90, 180 or 270 (clockwise), got {rotate}")
    if flip not in flips:
        raise ValueError(f"flip must be '', 'horizontal', 'vertical' or 'both', got {flip!r}")
    chain = turns[rotate] + flips[flip]
    if not chain:
        raise ValueError("nothing to do: give rotate (90/180/270) or flip")
    return ",".join(chain)


def rotate_flip_file(source: Path, output: Path, rotate: int = 0, flip: str = "") -> FFmpegResult:
    """Rotate and/or flip the picture; audio is copied.

    ffmpeg already applies a phone clip's rotation tag on input, so the output
    tag is reset to 0 or players would rotate it a second time.
    """
    vf = rotate_flip_filter(rotate, flip)
    asset = probe_media(source)
    if not has_video(asset):
        raise ValueError(f"source has no video stream: {source}")
    args = ["-vf", vf, *ENCODE_VIDEO_ARGS, "-metadata:s:v:0", "rotate=0"]
    args += ["-c:a", "copy"] if has_audio(asset) else []
    return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])
