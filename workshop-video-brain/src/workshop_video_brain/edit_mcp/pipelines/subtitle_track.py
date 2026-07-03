"""Pure helpers for real subtitle-track attachment, SRT→ASS conversion and
subtitle styling.

No filesystem or MCP side effects live here (except :func:`latest_srt`, a
read-only directory scan) so the styling / conversion / docproperties logic is
unit-testable in isolation.  The MCP tools that snapshot, parse, serialise and
render live in ``edit_mcp/server/bundles/subtitle_track.py``.

Subtitle-storage format verified against KDE source + a live melt 7.40 — see
``docs/research/2026-07-03-tutorial-effect-analysis/subtitle-track.md``:

* sidecar ``.ass`` next to the project (``{project}.ass``);
* an ``avfilter.subtitles`` filter on the timeline tractor (``av.filename``,
  optional ``av.force_style``); rendered headless by melt (proven);
* ``kdenlive:docproperties.subtitlesList`` / ``kdenlive:activeSubtitleIndex``
  properties for the Kdenlive GUI Subtitles panel.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import BaseModel

from workshop_video_brain.core.models.kdenlive import KdenliveProject, SubtitleTrack
from workshop_video_brain.core.models.timeline import SubtitleCue

# ASS numpad alignment (SubStation): 1-3 bottom, 4-6 middle, 7-9 top; 2 = bottom
# centre (the subtitle default).
ALIGNMENT_NAMES = {
    "bottom-left": 1,
    "bottom": 2,
    "bottom-center": 2,
    "bottom-right": 3,
    "middle-left": 4,
    "middle": 5,
    "center": 5,
    "middle-center": 5,
    "middle-right": 6,
    "top-left": 7,
    "top": 8,
    "top-center": 8,
    "top-right": 9,
}


class SubtitleStyle(BaseModel):
    """User-facing subtitle styling, mapped to an ASS ``[V4+ Styles]`` line."""

    font: str = "DejaVu Sans"
    size: int = 48
    primary_color: str = "#FFFFFF"   # text fill
    outline_color: str = "#000000"   # border
    bold: bool = False
    italic: bool = False
    outline: float = 2.0             # border thickness (px)
    shadow: float = 0.0
    alignment: int = 2               # numpad, or set via `position`
    margin_v: int = 20               # vertical margin from the aligned edge

    @classmethod
    def from_input(cls, value) -> "SubtitleStyle | None":
        """Coerce ``None`` / dict / JSON string / SubtitleStyle into a style.

        MCP tools receive styling as a dict or a JSON-encoded string; both are
        accepted so the server stays agent-friendly.
        """
        if value is None:
            return None
        if isinstance(value, SubtitleStyle):
            return value
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
            value = json.loads(value)
        if not isinstance(value, dict):
            raise ValueError(f"style must be a dict or JSON object, got {type(value)!r}")
        data = dict(value)
        pos = data.pop("position", None)
        if pos is not None and "alignment" not in data:
            data["alignment"] = _alignment_from_position(pos)
        return cls(**data)


def _alignment_from_position(position) -> int:
    if isinstance(position, (int, float)):
        return int(position)
    key = str(position).strip().lower().replace("_", "-").replace(" ", "-")
    if key not in ALIGNMENT_NAMES:
        raise ValueError(f"unknown subtitle position {position!r}")
    return ALIGNMENT_NAMES[key]


# ---------------------------------------------------------------------------
# Colour + time formatting
# ---------------------------------------------------------------------------

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6})$")


def hex_to_ass_color(hex_str: str) -> str:
    """Convert ``#RRGGBB`` (or ``RRGGBB``) to ASS ``&H00BBGGRR`` (AABBGGRR).

    ASS/libass colours are little-endian ABGR with a leading alpha byte where
    ``00`` is fully opaque.
    """
    match = _HEX_RE.match(str(hex_str).strip())
    if not match:
        raise ValueError(f"invalid hex colour: {hex_str!r} (expected #RRGGBB)")
    rr = match.group(1)[0:2]
    gg = match.group(1)[2:4]
    bb = match.group(1)[4:6]
    return f"&H00{bb}{gg}{rr}".upper()


def ass_timestamp(seconds: float) -> str:
    """Format seconds as an ASS timestamp ``H:MM:SS.cc`` (centiseconds)."""
    if seconds < 0:
        seconds = 0.0
    total_cs = int(round(seconds * 100))
    cs = total_cs % 100
    total_s = total_cs // 100
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


# ---------------------------------------------------------------------------
# ASS document generation
# ---------------------------------------------------------------------------

_ASS_STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
    "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
    "MarginR, MarginV, Encoding"
)
_ASS_EVENT_FORMAT = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
    "Effect, Text"
)


def build_ass_style_line(style: SubtitleStyle, name: str = "Default") -> str:
    """Return the ASS ``Style:`` line for *style*."""
    primary = hex_to_ass_color(style.primary_color)
    outline_c = hex_to_ass_color(style.outline_color)
    bold = -1 if style.bold else 0
    italic = -1 if style.italic else 0
    return (
        f"Style: {name},{style.font},{style.size},{primary},&H000000FF,"
        f"{outline_c},&H80000000,{bold},{italic},0,0,100,100,0,0,1,"
        f"{_num(style.outline)},{_num(style.shadow)},{int(style.alignment)},"
        f"10,10,{int(style.margin_v)},1"
    )


def _num(value: float) -> str:
    """Format a float without a trailing ``.0`` when integral (ASS-friendly)."""
    if float(value).is_integer():
        return str(int(value))
    return str(value)


def _ass_escape(text: str) -> str:
    """Escape newlines for an ASS ``Dialogue`` Text field (``\\N`` line break)."""
    return text.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\N")


def cues_to_ass(
    cues: list[SubtitleCue],
    style: SubtitleStyle | None = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Render a list of :class:`SubtitleCue` as a complete ASS document."""
    style = style or SubtitleStyle()
    lines = [
        "[Script Info]",
        "; Generated by ForgeFrame subtitles_attach",
        "ScriptType: v4.00+",
        "WrapStyle: 0",
        "ScaledBorderAndShadow: yes",
        f"PlayResX: {int(width)}",
        f"PlayResY: {int(height)}",
        "",
        "[V4+ Styles]",
        _ASS_STYLE_FORMAT,
        build_ass_style_line(style),
        "",
        "[Events]",
        _ASS_EVENT_FORMAT,
    ]
    for cue in cues:
        start = ass_timestamp(cue.start_seconds)
        end = ass_timestamp(cue.end_seconds)
        text = _ass_escape(cue.text.strip())
        lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def srt_to_ass(
    srt_content: str,
    style: SubtitleStyle | None = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """Convert an SRT string to a styled ASS document."""
    # Reuse the existing SRT parser (no code duplication).
    from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import (
        _parse_srt_content,
    )

    cues = _parse_srt_content(srt_content)
    return cues_to_ass(cues, style=style, width=width, height=height)


# ---------------------------------------------------------------------------
# Project attachment (pure) + docproperties assembly
# ---------------------------------------------------------------------------


def subtitles_list_json(project: KdenliveProject) -> str:
    """Serialise the project's subtitle tracks as Kdenlive's ``subtitlesList``.

    Matches ``SubtitleModel::subtitlesFilesToJson`` — a JSON array of
    ``{"name", "id", "file"}`` objects.  ``file`` is the sidecar's basename
    (Kdenlive resolves it relative to the project directory).
    """
    items = [
        {
            "name": sub.name,
            "id": sub.id,
            "file": Path(sub.file).name if sub.file else "",
        }
        for sub in project.subtitles
    ]
    return json.dumps(items)


def active_subtitle_index(project: KdenliveProject) -> str:
    """Return the active subtitle index property value (default ``"0"``)."""
    if not project.subtitles:
        return "0"
    return str(project.subtitles[0].id)


def attach_subtitle(
    project: KdenliveProject,
    sidecar_path: str,
    name: str = "Subtitle",
    style: str | None = None,
    replace: bool = True,
) -> KdenliveProject:
    """Return a new project with a subtitle track pointing at *sidecar_path*.

    *style* is an optional libass ``av.force_style`` override; normally styling
    is baked into the ``.ass`` sidecar and this stays ``None``.  When *replace*
    is true (default) any existing tracks are cleared so re-running the tool is
    idempotent rather than stacking duplicate tracks.
    """
    new_project = project.model_copy(deep=True)
    existing = [] if replace else list(new_project.subtitles)
    track_id = 0 if replace else len(existing)
    existing.append(
        SubtitleTrack(id=track_id, name=name, file=str(sidecar_path), style=style)
    )
    new_project.subtitles = existing
    return new_project


# ---------------------------------------------------------------------------
# reports/ SRT discovery
# ---------------------------------------------------------------------------


def latest_srt(reports_dir: Path) -> Path | None:
    """Return the most-recently-modified ``*.srt`` under *reports_dir* or None."""
    reports_dir = Path(reports_dir)
    if not reports_dir.is_dir():
        return None
    srts = sorted(
        reports_dir.glob("*.srt"), key=lambda p: p.stat().st_mtime, reverse=True
    )
    return srts[0] if srts else None


def force_style_string(style: SubtitleStyle) -> str:
    """Build an ffmpeg/libass ``force_style`` override string for burn-in.

    Colours are ASS ABGR; commas separate directives (callers embedding this in
    an ffmpeg filtergraph must single-quote the value).
    """
    parts = [
        f"Fontname={style.font}",
        f"Fontsize={style.size}",
        f"PrimaryColour={hex_to_ass_color(style.primary_color)}",
        f"OutlineColour={hex_to_ass_color(style.outline_color)}",
        f"Bold={1 if style.bold else 0}",
        f"Italic={1 if style.italic else 0}",
        f"Outline={_num(style.outline)}",
        f"Shadow={_num(style.shadow)}",
        f"Alignment={int(style.alignment)}",
        f"MarginV={int(style.margin_v)}",
    ]
    return ",".join(parts)
