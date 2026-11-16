"""Captioned reaction GIFs: find a line in subtitles, pin the frames, render.

Rebuilds the owner's vault ``make_gif.py`` three-step flow
(``find`` -> ``scene`` -> ``gif``) as a pipeline. Everything here works from
evidence -- subtitle cues, contact sheets, shot-cut times, waveforms -- never
guessed timestamps.

Pure builders (``parse_srt``, ``search_srt``, ``caption_metrics``,
``build_*_args``, ``parse_showinfo_cuts``) are separated from the runners
(``detect_scene_cuts``, ``make_contact_sheet``, ``make_waveform``,
``render_gif``, ``make_check_strip``), which shell out through
``adapters.ffmpeg.runner.run_ffmpeg``. The yt-dlp side lives in
``adapters.youtube.ytdlp_cli``; ``find_line`` and ``fetch_scene`` glue it in.

Key rules (from the workflow note):

* Subtitle times run about 3 s ahead of the picture, so the suggested scene
  window is centred on ``cue.start + picture_offset``.
* An apostrophe in the caption breaks filter parsing, so the caption is
  always written to a file and passed as ``drawtext=textfile=``.
* Caption: font size ~ width/10, border ~ size/12, bottom margin ~ size/3.
* 15 fps, 480 px, lanczos, two-pass palette (``stats_mode=diff`` ->
  ``dither=bayer:bayer_scale=4``).
* To stop right before a cutaway, end ~0.04 s before the cut.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    ANALYSIS_TIMEOUT_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    FFmpegCommandError,
    run_ffmpeg,
)
from workshop_video_brain.edit_mcp.pipelines._common import (
    escape_filter_path,
    seconds_to_mmss,
)

DEFAULT_FONT = "/usr/share/fonts/liberation/LiberationSans-Bold.ttf"
DEFAULT_FPS = 15
DEFAULT_WIDTH = 480
PICTURE_OFFSET_SECONDS = 3.0
SCENE_WINDOW_SECONDS = 30.0
CUT_GUARD_SECONDS = 0.04
SCENE_THRESHOLD = 0.3
GALLERY_ENV = "WVB_GIF_GALLERY"


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------


def parse_time(value: str | float | int) -> float:
    """Parse ``SS``, ``SS.ss``, ``MM:SS(.ss)`` or ``HH:MM:SS(.ss)`` to seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    parts = text.split(":")
    if not text or len(parts) > 3:
        raise ValueError(f"Not a time: {value!r} (use SS, MM:SS or HH:MM:SS)")
    try:
        nums = [float(p) for p in parts]
    except ValueError:
        raise ValueError(f"Not a time: {value!r} (use SS, MM:SS or HH:MM:SS)") from None
    total = 0.0
    for n in nums:
        total = total * 60 + n
    return total


def end_before_cut(cut_time: float, guard: float = CUT_GUARD_SECONDS) -> float:
    """End time that stops on the frame before a shot cut."""
    return round(cut_time - guard, 3)


def _fmt(seconds: float) -> str:
    return f"{seconds:.3f}"


# ---------------------------------------------------------------------------
# SRT parsing and search
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SrtCue:
    index: int
    start: float
    end: float
    text: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["start_mmss"] = seconds_to_mmss(self.start)
        return d


_TS = r"(\d+):(\d{2}):(\d{2})[,.](\d{1,3})"
_TIMING_RE = re.compile(_TS + r"\s*-->\s*" + _TS)
_TAG_RE = re.compile(r"<[^>]+>|\{\\[^}]*\}")


def _ts(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000.0


def parse_srt(text: str) -> list[SrtCue]:
    """Parse SRT text into cues (file order). Markup tags are stripped."""
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[SrtCue] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.split("\n")]
        timing_at = next((i for i, ln in enumerate(lines) if _TIMING_RE.search(ln)), None)
        if timing_at is None:
            continue
        g = _TIMING_RE.search(lines[timing_at]).groups()
        idx_line = lines[timing_at - 1].strip() if timing_at > 0 else ""
        index = int(idx_line) if idx_line.isdigit() else len(cues) + 1
        body = "\n".join(_TAG_RE.sub("", ln).strip() for ln in lines[timing_at + 1:])
        cues.append(SrtCue(index, _ts(*g[:4]), _ts(*g[4:]), body.strip()))
    return cues


def _normalise(text: str) -> str:
    text = text.replace("’", "'").replace("‘", "'").replace("`", "'")
    return " ".join(text.casefold().split())


def search_srt(
    cues: list[SrtCue],
    query: str,
    *,
    context: int = 4,
    picture_offset: float = PICTURE_OFFSET_SECONDS,
    window: float = SCENE_WINDOW_SECONDS,
) -> list[dict]:
    """Find every cue containing *query* (case-insensitive).

    Each match carries the ``context`` preceding cues (lines repeat; context
    tells the candidates apart), ``picture_time`` (cue start plus the
    subtitle-ahead-of-picture offset) and a ``suggested_window`` of *window*
    seconds centred on it, for ``fetch_scene``.
    """
    needle = _normalise(query)
    if not needle:
        raise ValueError("Search text is empty.")
    matches = []
    for i, cue in enumerate(cues):
        if needle not in _normalise(cue.text):
            continue
        pic = cue.start + picture_offset
        start = max(0.0, pic - window / 2)
        end = start + window
        matches.append(
            {
                "cue": cue.as_dict(),
                "context": [c.as_dict() for c in cues[max(0, i - context):i]],
                "picture_time": round(pic, 3),
                "suggested_window": {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "start_mmss": seconds_to_mmss(start),
                    "end_mmss": seconds_to_mmss(end),
                },
            }
        )
    return matches


# ---------------------------------------------------------------------------
# Caption + GIF filtergraph
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaptionMetrics:
    fontsize: int
    borderw: int
    margin: int


def caption_metrics(width: int) -> CaptionMetrics:
    """Font size ~ width/10, border ~ size/12, bottom margin ~ size/3."""
    size = max(8, round(width / 10))
    return CaptionMetrics(size, max(1, round(size / 12)), max(1, round(size / 3)))


def write_caption_file(caption: str, directory: Path) -> Path:
    """Write *caption* to ``directory/caption.txt`` (drawtext reads it verbatim)."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "caption.txt"
    path.write_text(caption, encoding="utf-8")
    return path


def resolve_font(font_file: str | None = DEFAULT_FONT) -> str | None:
    """Return *font_file* if it exists, else None (drawtext falls back to fontconfig)."""
    if font_file and Path(font_file).is_file():
        return font_file
    return None


def build_gif_filtergraph(
    caption_file: Path | None,
    *,
    width: int = DEFAULT_WIDTH,
    fps: int = DEFAULT_FPS,
    font_file: str | None = DEFAULT_FONT,
) -> str:
    """The single-command, two-pass-palette GIF graph from the workflow note."""
    chain = f"fps={fps},scale={width}:-1:flags=lanczos"
    if caption_file is not None:
        m = caption_metrics(width)
        opts = []
        if font_file:
            opts.append(f"fontfile={escape_filter_path(font_file)}")
        opts += [
            f"textfile={escape_filter_path(caption_file)}",
            f"fontsize={m.fontsize}",
            "fontcolor=white",
            f"borderw={m.borderw}",
            "bordercolor=black",
            "x=(w-tw)/2",
            f"y=h-th-{m.margin}",
        ]
        chain += ",drawtext=" + ":".join(opts)
    return (
        chain
        + ",split[a][b];[a]palettegen=stats_mode=diff[p];"
        "[b][p]paletteuse=dither=bayer:bayer_scale=4"
    )


def build_gif_args(
    start: float,
    end: float,
    caption_file: Path | None,
    *,
    width: int = DEFAULT_WIDTH,
    fps: int = DEFAULT_FPS,
    font_file: str | None = DEFAULT_FONT,
) -> tuple[list[str], list[str]]:
    """``(pre_input_args, args)`` for :func:`run_ffmpeg`.

    ``-ss``/``-t`` are input options so decoding stops at *end*: no frame past
    it can reach the fps filter.
    """
    if start < 0 or end <= start:
        raise ValueError(f"End ({end}) must be after start ({start}), both >= 0.")
    graph = build_gif_filtergraph(caption_file, width=width, fps=fps, font_file=font_file)
    pre = ["-ss", _fmt(start), "-t", _fmt(end - start)]
    return pre, ["-lavfi", graph, "-an", "-loop", "0"]


# ---------------------------------------------------------------------------
# Evidence builders: scene cuts, contact sheet, waveform, check strip
# ---------------------------------------------------------------------------

_PTS_RE = re.compile(r"\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:(-?\d+(?:\.\d+)?)")


def build_scene_cut_args(threshold: float = SCENE_THRESHOLD) -> list[str]:
    return ["-an", "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null"]


def parse_showinfo_cuts(stderr: str) -> list[float]:
    """Read every frame's ``pts_time`` from ``showinfo`` stderr (the shot cuts)."""
    return [float(t) for t in _PTS_RE.findall(stderr)]


def build_contact_sheet_args(
    *,
    fps: float = 2,
    start: float | None = None,
    duration: float | None = None,
    columns: int = 6,
    rows: int | None = None,
    thumb_width: int = 240,
) -> tuple[list[str], list[str]]:
    """Labelled contact sheet (each frame stamped with its time in the clip).

    Default is the note's 2 fps, 6x10 sheet. With *duration*, rows are sized
    to fit ``fps * duration`` frames (e.g. the finer 6 fps over 3 s sheet).
    """
    pre: list[str] = []
    if start is not None:
        pre += ["-ss", _fmt(start)]
    if duration is not None:
        pre += ["-t", _fmt(duration)]
    if rows is None:
        rows = 10 if duration is None else max(1, -(-round(fps * duration) // columns))
    fps_txt = f"{fps:g}"
    vf = (
        f"fps={fps_txt},scale={thumb_width}:-1,"
        "drawtext=text='%{pts\\:flt}':x=4:y=4:fontsize=16:"
        f"fontcolor=yellow:box=1:boxcolor=black,tile={columns}x{rows}"
    )
    return pre, ["-vf", vf, "-frames:v", "1"]


def build_waveform_args(
    start: float, duration: float = 6.0, size: str = "1200x200"
) -> tuple[list[str], list[str]]:
    """Waveform picture: speech is short bursts, explosions are solid blocks."""
    return (
        ["-ss", _fmt(start), "-t", _fmt(duration)],
        ["-filter_complex", f"showwavespic=s={size}", "-frames:v", "1"],
    )


def build_check_strip_args(frame_count: int, frames: int = 10) -> list[str]:
    """~*frames* evenly spaced frames from the finished GIF, tiled 5x2."""
    k = max(1, frame_count // max(1, frames))
    cols = 5
    rows = max(1, -(-frames // cols))
    return [
        "-vf", f"select='not(mod(n\\,{k}))',scale=320:-1,tile={cols}x{rows}",
        "-frames:v", "1",
    ]


# ---------------------------------------------------------------------------
# Gallery
# ---------------------------------------------------------------------------


def caption_fit_warning(caption: str | None, width: int = DEFAULT_WIDTH) -> str | None:
    """Rough check (bold sans ~0.62 em per glyph) that one caption line fits."""
    if not caption:
        return None
    m = caption_metrics(width)
    longest = max(len(line) for line in caption.splitlines() or [""])
    est = longest * m.fontsize * 0.62
    if est > width - 2 * m.borderw:
        return (
            f"Caption line of {longest} characters is about {est:.0f} px wide at "
            f"{m.fontsize} px, wider than the {width} px GIF: shorten it or "
            "break it onto two lines. Check the strip."
        )
    return None


def default_gallery_dir() -> Path:
    """``$WVB_GIF_GALLERY``, else ``~/Pictures/Reaction GIFs``."""
    env = os.environ.get(GALLERY_ENV)
    if env:
        return Path(env).expanduser()
    return Path.home() / "Pictures" / "Reaction GIFs"


def caption_slug(caption: str | None) -> str:
    text = (caption or "").casefold().replace("'", "").replace("’", "")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug[:60].strip("-") or "reaction"


# ---------------------------------------------------------------------------
# Runners
# ---------------------------------------------------------------------------


def _run(args, input_path, output_path, *, pre=None, timeout=ANALYSIS_TIMEOUT_SECONDS):
    result = run_ffmpeg(
        args, Path(input_path), Path(output_path), pre_input_args=pre, timeout=timeout
    )
    if not result.success:
        raise FFmpegCommandError(
            f"ffmpeg failed on {Path(input_path).name}:\n{result.stderr_tail}"
        )
    return result


def _require_file(path: Path, label: str) -> Path:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def detect_scene_cuts(clip: Path, threshold: float = SCENE_THRESHOLD) -> list[float]:
    """Shot-cut times (seconds in the clip) via ``select=gt(scene,T),showinfo``."""
    clip = _require_file(clip, "Clip")
    result = _run(build_scene_cut_args(threshold), clip, Path(os.devnull))
    return parse_showinfo_cuts(result.stderr)


def make_contact_sheet(
    clip: Path,
    output: Path,
    *,
    fps: float = 2,
    start: float | None = None,
    duration: float | None = None,
) -> Path:
    clip = _require_file(clip, "Clip")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pre, args = build_contact_sheet_args(fps=fps, start=start, duration=duration)
    _run(args, clip, output, pre=pre)
    return output


def make_waveform(clip: Path, start: float, output: Path, *, duration: float = 6.0) -> Path:
    clip = _require_file(clip, "Clip")
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    pre, args = build_waveform_args(start, duration)
    _run(args, clip, output, pre=pre)
    return output


def _gif_stats(gif: Path) -> dict:
    """Frame count, duration, width/height from the GIF itself (Pillow)."""
    from PIL import Image, ImageSequence

    with Image.open(gif) as im:
        width, height = im.size
        n = 0
        ms = 0
        for frame in ImageSequence.Iterator(im):
            n += 1
            ms += frame.info.get("duration", 0) or 0
    duration = ms / 1000.0
    return {
        "frames": n,
        "duration": round(duration, 3),
        "fps": round(n / duration, 2) if duration else 0.0,
        "width": width,
        "height": height,
    }


def make_check_strip(gif: Path, output: Path, *, frame_count: int, frames: int = 10) -> Path:
    gif = _require_file(gif, "GIF")
    output = Path(output)
    _run(build_check_strip_args(frame_count, frames), gif, output)
    return output


def render_gif(
    clip: Path,
    start: float | str,
    end: float | str,
    caption: str | None,
    *,
    output: Path | None = None,
    gallery_dir: Path | None = None,
    width: int = DEFAULT_WIDTH,
    fps: int = DEFAULT_FPS,
    font_file: str | None = DEFAULT_FONT,
) -> dict:
    """Render a captioned GIF from ``clip[start:end]`` and its check strip.

    *start*/*end* are seconds (or ``MM:SS``) within *clip*. Without *output*,
    the GIF goes to the gallery (``gallery_dir`` or :func:`default_gallery_dir`)
    as ``<caption-slug>.gif``. The check strip is written beside the GIF as
    ``<stem>.check.png``. Returns path, size, duration, fps, width, height,
    frames and check_strip.
    """
    clip = _require_file(clip, "Clip")
    start_s, end_s = parse_time(start), parse_time(end)
    if output is None:
        gallery = Path(gallery_dir) if gallery_dir else default_gallery_dir()
        output = gallery / f"{caption_slug(caption)}.gif"
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    work = output.parent / f".{output.stem}.work"
    try:
        cap_file = write_caption_file(caption, work) if caption else None
        pre, args = build_gif_args(
            start_s, end_s, cap_file, width=width, fps=fps, font_file=resolve_font(font_file)
        )
        _run(args, clip, output, pre=pre, timeout=DEFAULT_TIMEOUT_SECONDS)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    stats = _gif_stats(output)
    strip = make_check_strip(
        output, output.with_name(f"{output.stem}.check.png"), frame_count=stats["frames"]
    )
    size = output.stat().st_size
    return {
        "path": str(output),
        "size_bytes": size,
        "size_mb": round(size / 1_000_000, 2),
        **stats,
        "nominal_fps": fps,
        "start": start_s,
        "end": end_s,
        "caption": caption,
        "check_strip": str(strip),
        "warnings": [w for w in [caption_fit_warning(caption, width)] if w],
    }


# ---------------------------------------------------------------------------
# yt-dlp glue (find / scene)
# ---------------------------------------------------------------------------


def find_line(
    source: str,
    query: str,
    *,
    work_dir: Path | None = None,
    context: int = 4,
    picture_offset: float = PICTURE_OFFSET_SECONDS,
) -> dict:
    """Search a video's subtitles for *query*.

    *source* is a local ``.srt`` path or a URL; for a URL the English subs
    (manual or auto) are fetched with yt-dlp (no video download) into
    *work_dir*.
    """
    local = Path(source).expanduser()
    if local.suffix.lower() == ".srt" and local.is_file():
        srt_files = [local]
    else:
        from workshop_video_brain.edit_mcp.adapters.youtube import ytdlp_cli

        srt_files = ytdlp_cli.download_subs(
            source, Path(work_dir) if work_dir else default_work_dir("subs")
        )
    results = []
    for srt in srt_files:
        cues = parse_srt(srt.read_text(encoding="utf-8", errors="replace"))
        for m in search_srt(cues, query, context=context, picture_offset=picture_offset):
            m["srt"] = str(srt)
            results.append(m)
    return {
        "query": query,
        "source": source,
        "subtitle_files": [str(p) for p in srt_files],
        "match_count": len(results),
        "matches": results,
    }


def default_work_dir(kind: str) -> Path:
    """Scratch folder for subs/scenes: ``<gallery>/_work/<kind>``."""
    return default_gallery_dir() / "_work" / kind


def fetch_scene(
    source: str,
    start: float | str | None = None,
    end: float | str | None = None,
    *,
    out_dir: Path | None = None,
    contact_sheet: bool = True,
    fine_sheet_at: float | str | None = None,
    waveform_at: float | str | None = None,
) -> dict:
    """Get the scene clip and its evidence.

    *source* is a URL (only ``start..end`` is downloaded, with yt-dlp, to
    ``out_dir/clip.mp4``) or a local clip (re-examined, nothing downloaded).
    Returns shot-cut times, the matching end-before-cut times, a 2 fps
    contact sheet, and optionally a fine 6 fps / 3 s sheet from
    *fine_sheet_at* and a 6 s waveform from *waveform_at* (clip seconds).
    """
    local = Path(source).expanduser()
    if local.is_file():
        clip = local
    else:
        if start is None or end is None:
            raise ValueError("A URL source needs a start and end (MM:SS).")
        from workshop_video_brain.edit_mcp.adapters.youtube import ytdlp_cli

        start_s, end_s = parse_time(start), parse_time(end)
        if end_s <= start_s:
            raise ValueError(f"End ({end}) must be after start ({start}).")
        out_dir = Path(out_dir) if out_dir else default_work_dir(
            f"scene-{int(start_s)}-{int(end_s)}"
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        clip = ytdlp_cli.download_section(source, start_s, end_s, out_dir / "clip.mp4")
    out = describe_clip(clip, contact_sheet=contact_sheet)
    if fine_sheet_at is not None:
        at = parse_time(fine_sheet_at)
        out["fine_sheet"] = str(make_contact_sheet(
            clip, clip.with_name(f"{clip.stem}.fine-{at:g}.png"), fps=6, start=at, duration=3.0
        ))
    if waveform_at is not None:
        at = parse_time(waveform_at)
        out["waveform"] = str(make_waveform(clip, at, clip.with_name(f"{clip.stem}.wave-{at:g}.png")))
    return out


def describe_clip(clip: Path, *, contact_sheet: bool = True) -> dict:
    """Cuts (+ the end-before-cut times) and a contact sheet for a local clip."""
    clip = _require_file(clip, "Clip")
    cuts = detect_scene_cuts(clip)
    out = {
        "clip": str(clip),
        "scene_cuts": cuts,
        "end_before_cuts": [end_before_cut(c) for c in cuts],
    }
    if contact_sheet:
        out["contact_sheet"] = str(make_contact_sheet(clip, clip.with_name(f"{clip.stem}.sheet.png")))
    return out
