"""Multicam assembly + switch-cutting orchestration logic (Phases A2 + B).

Pure parsing + planning for the two multicam MCP tools; **all** I/O (audio sync,
ffprobe, snapshot, patch, serialise) lives in ``server/bundles/multicam.py``.
Spec: ``docs/research/2026-07-03-tutorial-effect-analysis/multicam.md`` §3.

Phase A2 -- ``multicam_assemble``
    Given N recordings of one event, recover each angle's start offset against a
    reference (via the ``media_sync_by_audio`` / ``audio_sync`` pipeline) and stack
    each angle on its own video track at the recovered offset.  The stacked
    placement runs through the **canonical** ``clip_place`` engine (``PlaceClip``
    intents), not a private model-level insert -- see the §4 placement-fix note.
    :func:`compute_alignment` turns per-angle offsets into per-track leading-gap
    frame counts.

Phase B -- ``multicam_switch``
    Given a stacked/synced project and a list of ``(at_seconds, angle)`` switch
    points, build an angle-switching program feed.

    **Switch approach chosen: top program-track overwrite placement via
    clip_place** (the spec's Phase-B option "top-track overwrite placement of the
    active angle via clip_place"), *not* per-segment track-visibility
    choreography.

    Why: in MLT/Kdenlive a track's visibility (``hide``) is a whole-track
    attribute -- there is no per-segment "show this track only for [t0, t1)"
    primitive, so the "visibility choreography" reading of the spec would need a
    web of per-segment compositing transitions that is fragile and does not
    render deterministically.  A dedicated top *program* track, onto which each
    cut segment's active angle is ``clip_place``-overwritten (frame-aligned to the
    angle's own footage), composites cleanly over the stack and renders provably:
    the program track simply *is* the switched output.  This is the same resulting
    edit the GUI multicam view produces, authored by data instead of clicks
    (spec §1 / Phase C).  Tradeoff: the program track duplicates the chosen
    angle's ``<entry>`` references (a few extra clips) rather than re-using the
    stacked tracks in place -- cheap, and it keeps every switch a real, renderable
    clip boundary.  :func:`build_switch_segments` + :func:`locate_source` are the
    pure planners; the bundle emits one ``PlaceClip`` overwrite per segment.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from workshop_video_brain.edit_mcp.pipelines import clip_place as _cp


# ---------------------------------------------------------------------------
# argument parsing (tools pass JSON / delimited strings or native lists)
# ---------------------------------------------------------------------------

def parse_source_list(sources) -> list[str]:
    """Normalise the ``sources`` argument to a list of path strings.

    Accepts a native list/tuple, a JSON array string, or a comma / newline
    separated string.  Blank entries are dropped.  Raises ``ValueError`` when the
    result is empty.
    """
    items: list[str]
    if isinstance(sources, (list, tuple)):
        items = [str(s) for s in sources]
    else:
        text = str(sources or "").strip()
        items = []
        if text:
            parsed = None
            if text[0] in "[(":
                try:
                    parsed = json.loads(text)
                except ValueError:
                    parsed = None
            if isinstance(parsed, (list, tuple)):
                items = [str(s) for s in parsed]
            else:
                items = [part for chunk in text.splitlines() for part in chunk.split(",")]
    cleaned = [s.strip() for s in items if s and s.strip()]
    if not cleaned:
        raise ValueError("sources is empty; provide the angle recordings to assemble")
    return cleaned


def parse_int_list(value) -> list[int]:
    """Parse a list of ints from a native list, a JSON array, or a delimited string."""
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [int(v) for v in value]
    text = str(value).strip()
    if not text:
        return []
    parsed = None
    if text[0] in "[(":
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
    if isinstance(parsed, (list, tuple)):
        return [int(v) for v in parsed]
    return [int(part) for chunk in text.splitlines() for part in chunk.split(",") if part.strip()]


@dataclass(frozen=True)
class Cut:
    """A single scripted switch point: from ``at_seconds`` show ``angle``."""

    at_seconds: float
    angle: int


def parse_cuts(cuts) -> list[Cut]:
    """Parse the ``cuts`` argument into an ordered list of :class:`Cut`.

    Accepts a native list of dicts or a JSON array string; each item must carry a
    time (``at_seconds`` / ``at`` / ``t``) and an angle index (``angle`` /
    ``track``).  Raises ``ValueError`` on an empty / malformed argument.
    """
    if isinstance(cuts, (list, tuple)):
        raw = list(cuts)
    else:
        text = str(cuts or "").strip()
        if not text:
            raise ValueError("cuts is empty; provide [{at_seconds, angle}, ...]")
        try:
            raw = json.loads(text)
        except ValueError as exc:
            raise ValueError(f"cuts is not valid JSON: {exc}") from exc
    if not isinstance(raw, (list, tuple)) or not raw:
        raise ValueError("cuts must be a non-empty list of {at_seconds, angle}")

    out: list[Cut] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ValueError(f"cut #{i} must be an object, got {type(item).__name__}")
        at = item.get("at_seconds", item.get("at", item.get("t")))
        angle = item.get("angle", item.get("track"))
        if at is None or angle is None:
            raise ValueError(f"cut #{i} needs 'at_seconds' and 'angle'")
        try:
            at_f = float(at)
            angle_i = int(angle)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"cut #{i} has a non-numeric field: {exc}") from exc
        if at_f < 0:
            raise ValueError(f"cut #{i} at_seconds must be >= 0 (got {at_f})")
        if angle_i < 0:
            raise ValueError(f"cut #{i} angle must be >= 0 (got {angle_i})")
        out.append(Cut(at_seconds=at_f, angle=angle_i))
    return out


# ---------------------------------------------------------------------------
# Phase A2: offset -> leading-gap alignment
# ---------------------------------------------------------------------------

def compute_alignment(offsets: list[float], fps: float) -> list[int]:
    """Turn per-angle sync offsets (seconds) into per-track leading-gap frames.

    ``offsets[i]`` is angle *i*'s event time relative to the reference (the
    reference's own offset is 0): a positive value means the shared event appears
    that many seconds *later* into angle *i* (it has extra lead-in), so that angle
    must start *earlier* on the timeline -- i.e. carry a *smaller* leading gap.

    All angles are shifted by a common lead ``G = max(0, max offset)`` so every
    resulting gap is non-negative while the shared event still lands on the same
    timeline frame across all tracks: ``gap_i = round((G - offset_i) * fps)``.
    """
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    if not offsets:
        return []
    lead = max(0.0, max(offsets))
    return [_cp.seconds_to_frames(lead - off, fps) for off in offsets]


# ---------------------------------------------------------------------------
# Phase B: switch-cut segment planning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Segment:
    """A contiguous program segment ``[start_frame, end_frame)`` showing ``angle``."""

    start_frame: int
    end_frame: int
    angle: int

    @property
    def length(self) -> int:
        return self.end_frame - self.start_frame


def build_switch_segments(cuts: list[Cut], timeline_end: int, fps: float) -> list[Segment]:
    """Expand ordered cut points into contiguous ``[start, end)`` program segments.

    Each cut opens a segment that runs until the next cut (or ``timeline_end`` for
    the last one).  Cuts are sorted by time; a cut at/after ``timeline_end`` and
    zero-length segments are dropped.  Raises ``ValueError`` if no usable segment
    remains.
    """
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    if timeline_end <= 0:
        raise ValueError("timeline is empty; nothing to switch")

    ordered = sorted(cuts, key=lambda c: c.at_seconds)
    frames = [_cp.seconds_to_frames(c.at_seconds, fps) for c in ordered]

    segments: list[Segment] = []
    for i, cut in enumerate(ordered):
        f0 = frames[i]
        f1 = frames[i + 1] if i + 1 < len(ordered) else timeline_end
        f1 = min(f1, timeline_end)
        if f1 > f0:
            segments.append(Segment(start_frame=f0, end_frame=f1, angle=cut.angle))
    if not segments:
        raise ValueError("cuts produced no non-empty program segments")
    return segments


@dataclass(frozen=True)
class SourceRef:
    """Where an angle's footage sits at a queried timeline frame."""

    producer_id: str
    in_point: int       # source in-point aligned to the queried timeline frame
    available_end: int  # exclusive timeline frame at which this clip ends


def locate_source(entries, at_frame: int) -> SourceRef | None:
    """Locate the real clip covering timeline ``at_frame`` on a track's entries.

    Returns a :class:`SourceRef` giving the producer, the source in-point that
    corresponds to ``at_frame`` (so the program feed shows the same frame the
    angle would), and the exclusive timeline frame at which the covering clip
    ends.  Returns ``None`` when no real (non-blank) clip covers ``at_frame``.
    """
    s = 0
    for entry in entries:
        length = _cp.entry_length(entry)
        e = s + length
        if entry.producer_id and s <= at_frame < e:
            return SourceRef(
                producer_id=entry.producer_id,
                in_point=entry.in_point + (at_frame - s),
                available_end=e,
            )
        s = e
    return None
