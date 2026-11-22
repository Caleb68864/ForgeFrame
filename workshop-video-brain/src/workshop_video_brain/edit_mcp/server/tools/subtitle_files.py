"""Subtitle file tools on plain files: convert, shift, merge, split, restyle, burn in.

Pure cue transforms live in ``pipelines/subtitle_files.py``. Inputs are
srt / vtt / json; outputs srt / vtt / ass / txt. Output paths follow the
plain-file rules (``pipelines/media_files.resolve_output``).
"""
from __future__ import annotations

import json
from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.bundles._media_shell import ffmpeg_ok_or_error, source_path
from workshop_video_brain.edit_mcp.server.errors import (
    bad_json_param,
    invalid_input,
    media_unreadable,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok

_HINT = "Inputs are .srt, .vtt or .json; formats srt, vtt, ass or txt."


def _ext(fmt: str, src: Path) -> str:
    return "." + (fmt or src.suffix.lstrip(".")).lower()


def _write(cues, src: Path, *, suffix: str, fmt: str, output_path: str, output_dir: str, overwrite: bool,
           style=None, width: int = 1920, height: int = 1080, max_line_length: int = 42) -> Path:
    from workshop_video_brain.edit_mcp.pipelines.media_files import resolve_output
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import write_cues

    fmt = (fmt or (Path(output_path).suffix.lstrip(".") if output_path else src.suffix.lstrip("."))).lower()
    out = resolve_output(src, output_path, output_dir, suffix=suffix, ext="." + fmt, overwrite=overwrite)
    write_cues(cues, out, fmt, max_line_length, style=style, width=width, height=height)
    return out


def _load(src: Path):
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import load_cues
    return load_cues(src)


@mcp.tool()
@tool_guard
def subtitle_convert(source: str, format: str = "vtt", style: str = "", width: int = 1920, height: int = 1080,
                     output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Convert a subtitle file to srt, vtt, ass or txt (``style`` JSON and the play size apply to ass)."""
    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        cues = _load(src)
        out = _write(cues, src, suffix="_converted" if _ext(format, src) == src.suffix.lower() else "",
                     fmt=format, output_path=output_path, output_dir=output_dir, overwrite=overwrite,
                     style=style or None, width=width, height=height)
    except ValueError as exc:
        return invalid_input(str(exc), _HINT)
    return _ok({"output_path": str(out), "cue_count": len(cues), "format": out.suffix.lstrip(".")})


@mcp.tool()
@tool_guard
def subtitle_shift(source: str, offset_seconds: float = 0.0, scale: float = 1.0, from_seconds: float = 0.0,
                   output_path: str = "", output_dir: str = "", overwrite: bool = False) -> dict:
    """Move subtitle timings by ``offset_seconds`` and/or stretch them by ``scale`` (0.5-2;
    25/23.976 fixes a frame-rate drift), only for cues from ``from_seconds`` on. Cues pushed
    before 0 are dropped."""
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import shift_cues

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        cues, dropped = shift_cues(_load(src), offset_seconds, scale, from_seconds)
        out = _write(cues, src, suffix="_shifted", fmt="", output_path=output_path, output_dir=output_dir,
                     overwrite=overwrite)
    except ValueError as exc:
        return invalid_input(str(exc), _HINT)
    return _ok({"output_path": str(out), "cue_count": len(cues), "dropped": dropped})


@mcp.tool()
@tool_guard
def subtitle_merge(sources: str, offsets: str = "", format: str = "srt", output_path: str = "",
                   output_dir: str = "", overwrite: bool = False) -> dict:
    """Merge subtitle files into one; ``offsets`` (JSON list, seconds) shifts each file.

    After ``media_concat``, pass the cumulative durations of the earlier files
    as offsets so each file's subtitles land on its part of the joined video.
    """
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import merge_cues

    try:
        items = json.loads(sources)
    except (TypeError, json.JSONDecodeError):
        return bad_json_param("sources", '["a.srt", "b.srt"]', str(sources))
    if not isinstance(items, list) or len(items) < 2:
        return invalid_input("sources must be a JSON list of at least two files", 'Pass e.g. ["a.srt", "b.srt"].')
    try:
        shifts = json.loads(offsets) if offsets else [0.0] * len(items)
    except json.JSONDecodeError:
        return bad_json_param("offsets", "[0, 312.5]", offsets)
    if not isinstance(shifts, list) or len(shifts) != len(items):
        return invalid_input("offsets must list one number per source", "Give as many offsets as sources.")
    paths = []
    for item in items:
        path = source_path(str(item), "sources")
        if isinstance(path, dict):
            return path
        paths.append(path)
    try:
        cues, overlaps = merge_cues([(_load(p), float(o)) for p, o in zip(paths, shifts)])
        out = _write(cues, paths[0], suffix="_merged", fmt=format, output_path=output_path, output_dir=output_dir,
                     overwrite=overwrite)
    except ValueError as exc:
        return invalid_input(str(exc), _HINT)
    return _ok({"output_path": str(out), "cue_count": len(cues), "overlaps": overlaps})


@mcp.tool()
@tool_guard
def subtitle_split(source: str, at_seconds: float, rebase: bool = True, output_dir: str = "",
                   overwrite: bool = False) -> dict:
    """Split a subtitle file in two at ``at_seconds`` (``<name>_part1`` / ``_part2``); a cue across the
    point is cut in two. With ``rebase`` part 2 starts at 0 (to match a video cut at the same point)."""
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import split_cues

    src = source_path(source)
    if isinstance(src, dict):
        return src
    try:
        first, second = split_cues(_load(src), at_seconds, rebase)
        out1 = _write(first, src, suffix="_part1", fmt="", output_path="", output_dir=output_dir, overwrite=overwrite)
        out2 = _write(second, src, suffix="_part2", fmt="", output_path="", output_dir=output_dir, overwrite=overwrite)
    except ValueError as exc:
        return invalid_input(str(exc), _HINT)
    return _ok({"part1": {"output_path": str(out1), "cue_count": len(first)},
                "part2": {"output_path": str(out2), "cue_count": len(second)}})


@mcp.tool()
@tool_guard
def subtitle_restyle(source: str, max_line_length: int = 42, max_lines: int = 2, style: str = "", format: str = "",
                     width: int = 1920, height: int = 1080, output_path: str = "", output_dir: str = "",
                     overwrite: bool = False) -> dict:
    """Rewrap lines (``max_line_length`` x ``max_lines``; longer cues are split, sharing their time)
    and/or style them. A ``style`` (JSON: font, size, primary_color, position...) needs ASS output, so
    with ``format`` empty a styled result is written as ASS."""
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import rewrap_cues

    src = source_path(source)
    if isinstance(src, dict):
        return src
    fmt = format or ("ass" if style else "")
    try:
        cues = rewrap_cues(_load(src), max_line_length, max_lines)
        out = _write(cues, src, suffix="_restyled", fmt=fmt, output_path=output_path, output_dir=output_dir,
                     overwrite=overwrite, style=style or None, width=width, height=height,
                     max_line_length=max_line_length)
    except ValueError as exc:
        return invalid_input(str(exc), _HINT)
    return _ok({"output_path": str(out), "cue_count": len(cues), "format": out.suffix.lstrip(".")})


@mcp.tool()
@tool_guard
def media_burn_subtitles(source: str, subtitles: str, style: str = "", output_path: str = "", output_dir: str = "",
                         overwrite: bool = False) -> dict:
    """Burn subtitles (srt/vtt/json) into a video file; ``style`` JSON as in ``subtitle_restyle``.

    The subtitle layout is sized to the video's real resolution. Default output
    ``<name>_subtitled.mp4``.
    """
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary, resolve_output
    from workshop_video_brain.edit_mcp.pipelines.subtitle_files import burn_subtitles_file

    src = source_path(source)
    if isinstance(src, dict):
        return src
    subs = source_path(subtitles, "subtitles")
    if isinstance(subs, dict):
        return subs
    try:
        out = resolve_output(src, output_path, output_dir, suffix="_subtitled", ext=".mp4", overwrite=overwrite)
        result, count = burn_subtitles_file(src, subs, out, style=style or None)
    except ValueError as exc:
        if str(exc).startswith("source has no"):
            return media_unreadable(str(src), exc)
        return invalid_input(str(exc), _HINT)
    problem = ffmpeg_ok_or_error(result, out, "Subtitle burn-in")
    if problem:
        return problem
    return _ok({**output_summary(out), "source": str(src), "subtitles": str(subs), "cue_count": count})
