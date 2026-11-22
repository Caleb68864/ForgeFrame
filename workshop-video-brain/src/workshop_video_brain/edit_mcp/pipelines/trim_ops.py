"""Pure planning for the classic NLE trims: slip, slide, replace, ripple insert.

No I/O: every function takes a playlist's entries (real clips and blanks) and
returns a new list, raising ``ValueError`` with a user-facing reason when the
trim is impossible. The patcher intents apply the plans to the video entry and
its linked audio entry; the shells in ``server/bundles/clip_trims.py`` convert
seconds and probe media.

Slip, slide and replace never change a playlist's total length.
"""
from __future__ import annotations

from workshop_video_brain.core.models.kdenlive import PlaylistEntry
from workshop_video_brain.edit_mcp.pipelines.clip_place import (
    clip_start_frame,
    entry_length,
    playlist_length,
)


def _copy(entries: list[PlaylistEntry]) -> list[PlaylistEntry]:
    return [e.model_copy(deep=True) for e in entries]


def _full_index(entries: list[PlaylistEntry], clip_index: int) -> int:
    real = -1
    for i, entry in enumerate(entries):
        if entry.producer_id:
            real += 1
            if real == clip_index:
                return i
    raise ValueError(f"clip_index {clip_index} out of range (track has {real + 1} clips)")


def _blank(length: int) -> PlaylistEntry:
    return PlaylistEntry(producer_id="", in_point=0, out_point=length - 1)


def _same_length(before: list[PlaylistEntry], after: list[PlaylistEntry]) -> list[PlaylistEntry]:
    assert playlist_length(before) == playlist_length(after), "trim changed the track length"
    return after


def plan_slip(
    entries: list[PlaylistEntry],
    clip_index: int,
    delta: int,
    source_frames: int | None = None,
) -> list[PlaylistEntry]:
    """Show a different part of the source: in and out move by *delta*; place and length stay."""
    out = _copy(entries)
    clip = out[_full_index(out, clip_index)]
    new_in, new_out = clip.in_point + delta, clip.out_point + delta
    if new_in < 0:
        raise ValueError(
            f"Slip of {delta} frames would start before the source (in point {new_in}); "
            f"the most you can slip back is {clip.in_point} frames."
        )
    if source_frames is not None and new_out > source_frames - 1:
        raise ValueError(
            f"Slip of {delta} frames would run past the end of the source "
            f"(out point {new_out}, source has {source_frames} frames); the most you can "
            f"slip forward is {source_frames - 1 - clip.out_point} frames."
        )
    clip.in_point, clip.out_point = new_in, new_out
    return _same_length(entries, out)


def plan_slide(
    entries: list[PlaylistEntry],
    clip_index: int,
    delta: int,
    prev_source_frames: int | None = None,
    next_source_frames: int | None = None,
) -> list[PlaylistEntry]:
    """Move a clip along the track by *delta*; its neighbours absorb the move.

    delta > 0: the entry before grows (a clip's out point, or a blank's length)
    and the entry after shrinks. delta < 0 mirrors it. A missing entry on the
    growing side becomes a blank; a missing one on the shrinking side is an
    error. A blank shrunk to nothing is removed (clip indices count clips only,
    so they do not change).
    """
    if delta == 0:
        return _copy(entries)
    out = _copy(entries)
    i = _full_index(out, clip_index)
    prev = out[i - 1] if i > 0 else None
    nxt = out[i + 1] if i + 1 < len(out) else None
    d = abs(delta)

    def grow(entry: PlaylistEntry | None, at_end: bool, source_frames: int | None, side: str):
        if entry is None:
            return _blank(d)
        if not entry.producer_id:
            entry.out_point += d
            return entry
        if at_end:  # previous clip grows at its tail
            if source_frames is not None and entry.out_point + d > source_frames - 1:
                raise ValueError(f"The {side} clip has only {source_frames - 1 - entry.out_point} "
                                 f"spare source frames after its out point; the slide needs {d}.")
            entry.out_point += d
        else:  # next clip grows at its head
            if entry.in_point - d < 0:
                raise ValueError(f"The {side} clip has only {entry.in_point} spare source frames "
                                 f"before its in point; the slide needs {d}.")
            entry.in_point -= d
        return entry

    def shrink(entry: PlaylistEntry | None, at_end: bool, side: str):
        if entry is None:
            raise ValueError(f"There is nothing {side} the clip to absorb the slide "
                             f"(it is the {'first' if side == 'before' else 'last'} entry on the track).")
        length = entry_length(entry)
        if not entry.producer_id:
            if length < d:
                raise ValueError(f"The gap {side} the clip is {length} frames; the slide needs {d}.")
            if length == d:
                return None
            entry.out_point -= d
            return entry
        if length - d < 1:
            raise ValueError(f"The clip {side} would be shortened to {length - d} frames "
                             f"(it is {length}); slide by at most {length - 1}.")
        if at_end:
            entry.out_point -= d
        else:
            entry.in_point += d
        return entry

    if delta > 0:
        new_prev = grow(prev, True, prev_source_frames, "previous")
        new_next = shrink(nxt, False, "after")
    else:
        new_prev = shrink(prev, True, "before")
        new_next = grow(nxt, False, next_source_frames, "next")

    head = out[: i - 1] if prev is not None else []
    tail = out[i + 2:] if nxt is not None else []
    middle = [e for e in (new_prev, out[i], new_next) if e is not None]
    return _same_length(entries, [*head, *middle, *tail])


def plan_replace(
    entries: list[PlaylistEntry],
    clip_index: int,
    new_producer_id: str,
    new_in: int = 0,
    source_frames: int | None = None,
) -> list[PlaylistEntry]:
    """Point a clip at other media from *new_in*, keeping its place and length."""
    if new_in < 0:
        raise ValueError(f"The new source in point must be >= 0 (got {new_in}).")
    out = _copy(entries)
    clip = out[_full_index(out, clip_index)]
    length = entry_length(clip)
    if source_frames is not None and new_in + length > source_frames:
        raise ValueError(f"The new media has {source_frames} frames; the clip needs {length} "
                         f"from frame {new_in}.")
    clip.producer_id, clip.in_point, clip.out_point = new_producer_id, new_in, new_in + length - 1
    return _same_length(entries, out)


def blank_out(entries: list[PlaylistEntry], clip_index: int) -> list[PlaylistEntry]:
    """Replace a clip with a blank of the same length."""
    out = _copy(entries)
    i = _full_index(out, clip_index)
    out[i] = _blank(entry_length(out[i]))
    return _same_length(entries, out)


def insert_frame_for(entries: list[PlaylistEntry], before_clip_index: int) -> int:
    """Timeline frame where an insert before *before_clip_index* lands.

    ``before_clip_index == number of clips`` means the end of the track.
    """
    real = sum(1 for e in entries if e.producer_id)
    if before_clip_index == real:
        return playlist_length(entries)
    if before_clip_index < 0 or before_clip_index > real:
        raise ValueError(f"before_clip_index {before_clip_index} out of range (track has {real} clips)")
    return clip_start_frame(entries, before_clip_index)


def split_index_at(entries: list[PlaylistEntry], frame: int) -> int | None:
    """Real-clip index of the clip that straddles *frame* (starts before, ends after), or None."""
    real, start = -1, 0
    for entry in entries:
        length = entry_length(entry)
        if entry.producer_id:
            real += 1
            if start < frame < start + length:
                return real
        start += length
    return None
