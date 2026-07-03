"""Pure planning for absolute-time clip placement (``clip_place``).

No I/O lives here: this module only does deterministic frame arithmetic on a
list of :class:`PlaylistEntry` objects, turning a "place clip C at timeline
frame T on this track" request into the exact new run of entries (real clips +
blanks) the track should hold.  All side effects (parse / patch / serialise,
producer registration, ffprobe duration, snapshotting) live in the patcher
intent handlers and the bundle module ``server/bundles/clip_place.py``.

This is the *canonical* engine the Wave-3a private model-level inserts
(``pipelines/overlay_looks.insert_overlay_clip`` and the vo_loop / image_overlay
modules) should eventually migrate onto: a playlist-targeted, frame-exact,
overwrite-or-insert placement -- the thing ``clip_insert`` (append-to-first-video
-track, playlist-index only) cannot express.

Two placement modes
--------------------
* **overwrite** -- the clip replaces whatever occupies ``[T, T+L)`` on the track.
  Straddling entries/blanks are trimmed at the region boundaries and entries
  fully inside the region are dropped.  Content beyond the region is untouched
  (no ripple).  If ``T`` is past the end of the track, a blank pad of ``T -
  content_len`` frames is inserted so the clip lands at the right time.
* **insert** -- the track is split at ``T`` and everything from ``T`` onward
  ripples right by the clip length ``L``; the clip is inserted at ``T``.  A
  Kdenlive playlist is inherently sequential, so the ripple is automatic (the
  tail entries keep their in/out and simply move later).  Cross-track sync is
  the caller's concern unless ``ripple_all_tracks`` is used at the patcher level.

Frame accuracy at fractional fps
--------------------------------
``seconds_to_frames`` rounds ``seconds * fps`` half-up via ``floor(x + 0.5)``
(deterministic, unlike Python's bankers' ``round``).  At 23.976 fps t=1.0s ->
frame 24, t=2.0s -> frame 48; at 29.97 fps t=1.0s -> frame 30, t=2.0s -> frame
60 -- i.e. what a human editor expects, not the truncation ``int(t*fps)`` the
legacy ``clip_insert`` used.  The engine itself works purely in integer frames,
so once seconds are converted every split/pad/length is exact.

Index remapping
---------------
Clip effects are stored (by the serializer) nested in the clip ``<entry>`` and
tracked in ``opaque_elements`` keyed by ``(track_index, real_clip_index)``.
Placement changes real-clip indices on the target track, so each plan returns an
``index_map`` (old real index -> new real index, or ``None`` when the clip was
fully overwritten).  The patcher uses it to shift/drop those filter
associations.  When a single clip is *split* by a placement boundary, its
effects stay with the **left** remainder (the surviving fragment that keeps the
clip's identity); the right fragment is treated as new, un-effected media -- the
same simplification the existing ``SplitClip`` handler makes (it does not remap
filters at all).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from workshop_video_brain.core.models.kdenlive import PlaylistEntry


# ---------------------------------------------------------------------------
# frame conversion
# ---------------------------------------------------------------------------

def seconds_to_frames(seconds: float, fps: float) -> int:
    """Convert a timeline offset in seconds to an integer frame index.

    Rounds half-up (``floor(seconds * fps + 0.5)``) so placement is frame-exact
    and deterministic at fractional NTSC rates (23.976 / 29.97 / 59.94).  Raises
    ``ValueError`` on a negative time or non-positive fps.
    """
    if seconds < 0:
        raise ValueError(f"seconds must be >= 0 (got {seconds})")
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    return int(math.floor(seconds * fps + 0.5))


def entry_length(entry: PlaylistEntry) -> int:
    """Timeline length in frames of a playlist entry (real clip or blank)."""
    return max(0, entry.out_point - entry.in_point + 1)


def playlist_length(entries: list[PlaylistEntry]) -> int:
    """Total timeline length of a playlist's entries, in frames."""
    return sum(entry_length(e) for e in entries)


# ---------------------------------------------------------------------------
# the clip to place + the plan result
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlacedClip:
    """A concrete clip to place: a producer id and its source in/out frames."""

    producer_id: str
    in_point: int
    out_point: int

    @property
    def length(self) -> int:
        return self.out_point - self.in_point + 1


@dataclass
class PlacementResult:
    """Outcome of a placement plan.

    ``entries`` is the new full run for the track (real clips + blanks).
    ``index_map`` maps each old real-clip index to its new real-clip index, or
    ``None`` if that clip no longer exists (overwritten).  ``placed_index`` is
    the new real-clip index of the placed clip.
    """

    entries: list[PlaylistEntry]
    index_map: dict[int, int | None] = field(default_factory=dict)
    placed_index: int = -1


# ---------------------------------------------------------------------------
# internal helpers
# ---------------------------------------------------------------------------

def _blank(length: int) -> PlaylistEntry:
    """A blank (gap) entry of ``length`` frames."""
    return PlaylistEntry(producer_id="", in_point=0, out_point=length - 1)


def _sub_entry(entry: PlaylistEntry, span_start: int, a: int, b: int) -> PlaylistEntry:
    """Return the entry covering timeline sub-range ``[a, b)`` of ``entry``.

    ``span_start`` is the timeline frame where ``entry`` begins.  For a real
    clip the source in-point is shifted by the offset into the clip; for a blank
    only the length changes.
    """
    length = b - a
    if entry.producer_id:
        new_in = entry.in_point + (a - span_start)
        return PlaylistEntry(
            producer_id=entry.producer_id,
            in_point=new_in,
            out_point=new_in + length - 1,
        )
    return _blank(length)


def _finalize(
    left: list[tuple[PlaylistEntry, int | None]],
    middle: list[PlaylistEntry],
    right: list[tuple[PlaylistEntry, int | None]],
    old_real_count: int,
) -> PlacementResult:
    """Assemble ``left + middle + right`` into a PlacementResult.

    ``middle`` is the freshly-placed content (the clip, possibly preceded by a
    pad blank); its real clips are not mapped from any old index.  ``index_map``
    is completed with ``None`` for every old real index that did not survive.
    """
    combined: list[tuple[PlaylistEntry, int | None]] = list(left)
    combined.extend((e, None) for e in middle)
    combined.extend(right)

    entries: list[PlaylistEntry] = []
    index_map: dict[int, int | None] = {}
    placed_index = -1
    new_real = -1
    placed_ids = {id(e) for e in middle if e.producer_id}
    for entry, origin in combined:
        entries.append(entry)
        if entry.producer_id:
            new_real += 1
            if id(entry) in placed_ids and placed_index < 0:
                placed_index = new_real
            if origin is not None:
                index_map[origin] = new_real
    for old in range(old_real_count):
        index_map.setdefault(old, None)
    return PlacementResult(entries=entries, index_map=index_map, placed_index=placed_index)


def _real_count(entries: list[PlaylistEntry]) -> int:
    return sum(1 for e in entries if e.producer_id)


# ---------------------------------------------------------------------------
# planning: overwrite
# ---------------------------------------------------------------------------

def plan_overwrite(
    entries: list[PlaylistEntry],
    at_frame: int,
    clip: PlacedClip,
) -> PlacementResult:
    """Plan an overwrite placement of ``clip`` at timeline frame ``at_frame``.

    Replaces whatever occupies ``[at_frame, at_frame + clip.length)`` on the
    track, trimming straddling entries/blanks and dropping fully-covered ones.
    Content outside the region keeps its position (no ripple).  If ``at_frame``
    is past the end of the track a blank pad is inserted first.
    """
    if at_frame < 0:
        raise ValueError(f"at_frame must be >= 0 (got {at_frame})")
    if clip.length <= 0:
        raise ValueError(f"clip length must be > 0 (got {clip.length})")

    region_start = at_frame
    region_end = at_frame + clip.length
    old_real_count = _real_count(entries)

    left: list[tuple[PlaylistEntry, int | None]] = []
    right: list[tuple[PlaylistEntry, int | None]] = []
    real_idx = -1
    s = 0
    for entry in entries:
        length = entry_length(entry)
        e = s + length
        ridx: int | None = None
        if entry.producer_id:
            real_idx += 1
            ridx = real_idx
        if e <= region_start:
            left.append((entry, ridx))
        elif s >= region_end:
            right.append((entry, ridx))
        else:
            # entry overlaps the placement region -- keep the remainders.
            has_left_rem = s < region_start
            if has_left_rem:
                left.append((_sub_entry(entry, s, s, region_start), ridx))
            if e > region_end:
                # tail fragment: origin goes to the left remainder if there was
                # one, else this tail keeps the clip identity.
                right.append((_sub_entry(entry, s, region_end, e), None if has_left_rem else ridx))
        s = e

    total = s
    middle: list[PlaylistEntry] = []
    if region_start > total:
        middle.append(_blank(region_start - total))
    middle.append(
        PlaylistEntry(
            producer_id=clip.producer_id,
            in_point=clip.in_point,
            out_point=clip.out_point,
        )
    )
    return _finalize(left, middle, right, old_real_count)


# ---------------------------------------------------------------------------
# planning: insert (ripple this track)
# ---------------------------------------------------------------------------

def plan_insert(
    entries: list[PlaylistEntry],
    at_frame: int,
    clip: PlacedClip,
) -> PlacementResult:
    """Plan an insert placement of ``clip`` at timeline frame ``at_frame``.

    Splits the track at ``at_frame`` and ripples everything from there on right
    by ``clip.length``; the clip is inserted at ``at_frame``.  Cross-track sync
    is the caller's concern (use the patcher's ``ripple_all_tracks`` to shift the
    other tracks + guides too).
    """
    if at_frame < 0:
        raise ValueError(f"at_frame must be >= 0 (got {at_frame})")
    if clip.length <= 0:
        raise ValueError(f"clip length must be > 0 (got {clip.length})")

    old_real_count = _real_count(entries)
    left: list[tuple[PlaylistEntry, int | None]] = []
    right: list[tuple[PlaylistEntry, int | None]] = []
    real_idx = -1
    s = 0
    for entry in entries:
        length = entry_length(entry)
        e = s + length
        ridx: int | None = None
        if entry.producer_id:
            real_idx += 1
            ridx = real_idx
        if e <= at_frame:
            left.append((entry, ridx))
        elif s >= at_frame:
            right.append((entry, ridx))
        else:
            # straddles the split: left remainder keeps origin, right is fresh.
            left.append((_sub_entry(entry, s, s, at_frame), ridx))
            right.append((_sub_entry(entry, s, at_frame, e), None))
        s = e

    total = s
    middle: list[PlaylistEntry] = []
    if at_frame > total:
        middle.append(_blank(at_frame - total))
    middle.append(
        PlaylistEntry(
            producer_id=clip.producer_id,
            in_point=clip.in_point,
            out_point=clip.out_point,
        )
    )
    return _finalize(left, middle, right, old_real_count)


def plan_insert_blank(
    entries: list[PlaylistEntry],
    at_frame: int,
    length: int,
) -> list[PlaylistEntry]:
    """Insert a ``length``-frame blank gap at ``at_frame`` (ripples the track).

    Used to keep *other* tracks in sync when an insert placement ripples one
    track (``ripple_all_tracks``).  A track shorter than ``at_frame`` is left
    unchanged (nothing to ripple there).
    """
    if length <= 0:
        raise ValueError(f"length must be > 0 (got {length})")
    total = playlist_length(entries)
    if at_frame >= total:
        # Nothing on this track at or after the insertion point -- no ripple.
        return list(entries)
    result: list[PlaylistEntry] = []
    inserted = False
    s = 0
    for entry in entries:
        elen = entry_length(entry)
        e = s + elen
        if not inserted and e <= at_frame:
            result.append(entry)
        elif not inserted and s >= at_frame:
            result.append(_blank(length))
            result.append(entry)
            inserted = True
        elif not inserted:
            # straddle: split and drop the blank in between
            result.append(_sub_entry(entry, s, s, at_frame))
            result.append(_blank(length))
            result.append(_sub_entry(entry, s, at_frame, e))
            inserted = True
        else:
            result.append(entry)
        s = e
    return result


# ---------------------------------------------------------------------------
# reference-clip helpers (match-length insert + cross-track move)
# ---------------------------------------------------------------------------

def clip_at_index(entries: list[PlaylistEntry], clip_index: int) -> PlaylistEntry:
    """Return the real (non-blank) clip at ``clip_index``, or raise IndexError."""
    real = [e for e in entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real):
        raise IndexError(
            f"clip_index {clip_index} out of range (track has {len(real)} clips)"
        )
    return real[clip_index]


def clip_start_frame(entries: list[PlaylistEntry], clip_index: int) -> int:
    """Timeline start frame of the real clip at ``clip_index``."""
    real_idx = -1
    s = 0
    for entry in entries:
        if entry.producer_id:
            real_idx += 1
            if real_idx == clip_index:
                return s
        s += entry_length(entry)
    raise IndexError(f"clip_index {clip_index} out of range")


def reference_length(entries: list[PlaylistEntry], clip_index: int) -> int:
    """Timeline length (frames) of the real clip at ``clip_index``."""
    return entry_length(clip_at_index(entries, clip_index))
