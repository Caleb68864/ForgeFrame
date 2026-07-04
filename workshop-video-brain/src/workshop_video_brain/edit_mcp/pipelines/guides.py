"""Pure helpers for project guides and YouTube chapter export.

These functions have no filesystem or MCP side effects.  They operate on
``KdenliveProject`` model instances and plain dict/list chapter data so they
can be unit-tested in isolation.  The MCP tools that snapshot, parse and
serialise projects live in ``edit_mcp/server/bundles/guides.py``.

Guides are added through the existing timeline intent + patcher machinery
(``AddGuide`` -> ``patch_project``); no patcher/serializer code is modified.

Format note (see docs/research/.../guides-chapters.md): our serializer writes
legacy top-level ``<guide>`` elements, but Kdenlive 24.x/25.x reads guides from
the ``kdenlive:sequenceproperties.guides`` (or legacy
``kdenlive:docproperties.guides``) JSON property.  ``guides_docproperties_json``
produces that JSON so the placement-fix agent (who owns serializer changes) can
emit it -- until then guides written by these tools will NOT display in a modern
Kdenlive GUI, though they round-trip through our own parser/serializer.
"""
from __future__ import annotations

import json

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddGuide
from workshop_video_brain.edit_mcp.pipelines import _common

DEFAULT_FPS = 25.0


# ---------------------------------------------------------------------------
# Time / frame math
# ---------------------------------------------------------------------------

def project_fps(project: KdenliveProject) -> float:
    """Return the project's fps, falling back to ``DEFAULT_FPS`` when unset."""
    fps = project.profile.fps
    return fps if fps else DEFAULT_FPS


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Convert *seconds* to an integer frame index (rounded to nearest frame).

    Thin fps-fallback front-end over the canonical
    :func:`_common.seconds_to_frames`: this wrapper substitutes ``DEFAULT_FPS``
    for a non-positive *fps* (the canonical helper *raises* on bad fps), then
    delegates the half-up frame math to it.
    """
    if fps <= 0:
        fps = DEFAULT_FPS
    return _common.seconds_to_frames(float(seconds), fps)


def frames_to_seconds(frames: int, fps: float) -> float:
    """Convert an integer frame index to seconds."""
    if fps <= 0:
        fps = DEFAULT_FPS
    return float(frames) / fps


def format_timestamp(seconds: float) -> str:
    """Format seconds as a YouTube chapter timestamp.

    Minutes are zero-padded (``00:00``); hours are only shown when non-zero
    (``1:05:30``).  Fractional seconds are floored, matching how YouTube and
    Kdenlive's own guide export truncate to whole seconds.
    """
    total = int(seconds)
    if total < 0:
        total = 0
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


# ---------------------------------------------------------------------------
# Guide operations (return new projects; never mutate input)
# ---------------------------------------------------------------------------

def add_guide(
    project: KdenliveProject,
    at_seconds: float,
    label: str,
    category: str | None = None,
) -> KdenliveProject:
    """Return a new project with a guide added at *at_seconds*.

    Uses the existing ``AddGuide`` intent applied through ``patch_project``.
    """
    # Local import avoids an import cycle (adapters import model layer).
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import (
        patch_project,
    )

    fps = project_fps(project)
    intent = AddGuide(
        position_frames=seconds_to_frames(at_seconds, fps),
        label=label,
        category=category,
    )
    return patch_project(project, [intent])


def list_guides(project: KdenliveProject) -> list[dict]:
    """Return guides as sorted dicts with frame + seconds + timecode."""
    fps = project_fps(project)
    rows: list[dict] = []
    for guide in sorted(project.guides, key=lambda g: g.position):
        seconds = frames_to_seconds(guide.position, fps)
        rows.append(
            {
                "position_frames": guide.position,
                "at_seconds": round(seconds, 3),
                "timecode": format_timestamp(seconds),
                "label": guide.label,
                "category": guide.category,
            }
        )
    return rows


def _is_numeric(value) -> bool:
    if isinstance(value, (int, float)):
        return True
    try:
        float(str(value).strip())
        return True
    except (TypeError, ValueError):
        return False


def remove_guide(
    project: KdenliveProject,
    at_seconds_or_label,
) -> tuple[KdenliveProject, list[dict]]:
    """Remove guides matching *at_seconds_or_label*.

    A numeric value (or numeric string) matches by frame position (converted
    from seconds at the project fps).  Any other string matches by label
    (case-insensitive, trimmed).  Returns ``(new_project, removed)`` where
    *removed* is the list of removed guide dicts.
    """
    fps = project_fps(project)
    new_project = project.model_copy(deep=True)

    numeric = _is_numeric(at_seconds_or_label)
    target_frame = (
        seconds_to_frames(float(str(at_seconds_or_label)), fps)
        if numeric
        else None
    )
    target_label = None if numeric else str(at_seconds_or_label).strip().lower()

    kept = []
    removed = []
    for guide in new_project.guides:
        if numeric:
            match = guide.position == target_frame
        else:
            match = (guide.label or "").strip().lower() == target_label
        if match:
            seconds = frames_to_seconds(guide.position, fps)
            removed.append(
                {
                    "position_frames": guide.position,
                    "at_seconds": round(seconds, 3),
                    "timecode": format_timestamp(seconds),
                    "label": guide.label,
                    "category": guide.category,
                }
            )
        else:
            kept.append(guide)

    new_project.guides = kept
    return new_project, removed


def _category_index(category: str | None) -> int:
    """Best-effort map of our string category to Kdenlive's integer type."""
    if category is None:
        return 0
    text = str(category).strip()
    if text.isdigit():
        return int(text)
    return 0


def guides_docproperties_json(project: KdenliveProject) -> str:
    """Serialise guides as Kdenlive's ``docproperties.guides`` JSON string.

    Keys mirror Kdenlive's ``MarkerListModel``: ``pos`` (frames), ``comment``
    (label), ``type`` (category index).  This is the format modern Kdenlive
    actually reads; our serializer does not yet emit it (documented limitation).
    """
    items = [
        {
            "pos": guide.position,
            "comment": guide.label,
            "type": _category_index(guide.category),
        }
        for guide in sorted(project.guides, key=lambda g: g.position)
    ]
    return json.dumps(items)


# ---------------------------------------------------------------------------
# Chapter collection + YouTube formatting
# ---------------------------------------------------------------------------

def collect_project_guide_chapters(project: KdenliveProject) -> list[dict]:
    """Return ``{time, title}`` chapter dicts from a project's guides."""
    fps = project_fps(project)
    return [
        {"time": frames_to_seconds(g.position, fps), "title": g.label or "Chapter"}
        for g in project.guides
    ]


def merge_min_gap(chapters: list[dict], min_gap_seconds: float) -> list[dict]:
    """Drop chapters closer than *min_gap_seconds* to the previous kept one.

    Input is sorted by time first.  The first (earliest) chapter is always
    kept; each subsequent chapter is kept only if it is at least
    *min_gap_seconds* after the last kept chapter (YouTube's 10s minimum
    chapter-length rule).
    """
    ordered = sorted(chapters, key=lambda c: c["time"])
    kept: list[dict] = []
    for chapter in ordered:
        if not kept:
            kept.append(chapter)
        elif chapter["time"] - kept[-1]["time"] >= min_gap_seconds:
            kept.append(chapter)
    return kept


def prepare_chapters(
    chapters: list[dict],
    min_gap_seconds: float = 10.0,
) -> list[dict]:
    """Sort, ensure a 0:00 chapter exists, then apply the min-gap merge."""
    ordered = sorted(chapters, key=lambda c: c["time"])
    has_zero = any(abs(c["time"]) < 0.001 for c in ordered)
    if not has_zero:
        ordered = [{"time": 0.0, "title": "Intro"}] + ordered
    return merge_min_gap(ordered, min_gap_seconds)


def format_chapter_lines(chapters: list[dict]) -> str:
    """Render prepared chapters as ``MM:SS Label`` lines (YouTube format)."""
    return "\n".join(
        f"{format_timestamp(c['time'])} {c['title']}" for c in chapters
    )


def youtube_chapter_warnings(
    chapters: list[dict],
    min_gap_seconds: float = 10.0,
) -> list[str]:
    """Return YouTube-rule violations for *chapters* (already time-sorted)."""
    warnings: list[str] = []
    ordered = sorted(chapters, key=lambda c: c["time"])
    if not ordered or abs(ordered[0]["time"]) >= 0.001:
        warnings.append("First chapter must start at 00:00.")
    if len(ordered) < 3:
        warnings.append("YouTube requires at least three chapters.")
    for prev, nxt in zip(ordered, ordered[1:]):
        if nxt["time"] - prev["time"] < min_gap_seconds:
            warnings.append(
                f"Chapters must be at least {min_gap_seconds:g}s apart."
            )
            break
    return warnings
