"""Edit to the beat: choose beats, map them to timeline frames, plan cuts and pulses (pure).

Builds on ``music_beat_grid``'s ``reports/beat_grid.json`` (beats in seconds of
music-file time). There is no downbeat detection, so a "bar" is every
``bar_every``-th beat from ``phase``.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.keyframes import Keyframe

#: Base stride per intensity: cutting on every beat looks robotic.
INTENSITY_STRIDE = {"subtle": 4, "medium": 2, "aggressive": 1}


def select_beats(
    beats: list[float],
    intensity: str = "medium",
    every_n: int = 0,
    phase: int = 0,
    bar_every: int = 4,
    start_s: float | None = None,
    end_s: float | None = None,
    min_gap_s: float = 0.0,
) -> list[float]:
    """Beats to edit on: every stride-th beat, bar beats always kept, windowed, spaced."""
    if every_n < 0:
        raise ValueError(f"every_n must be >= 0; got {every_n}")
    if every_n == 0:
        if intensity not in INTENSITY_STRIDE:
            raise ValueError(f"intensity must be one of {', '.join(INTENSITY_STRIDE)}; got {intensity!r}")
        stride = INTENSITY_STRIDE[intensity]
    else:
        stride = every_n
    if bar_every < 1:
        raise ValueError(f"bar_every must be >= 1; got {bar_every}")
    kept: list[float] = []
    for i, beat in enumerate(sorted(beats)):
        if start_s is not None and beat < start_s:
            continue
        if end_s is not None and beat > end_s:
            continue
        on_bar = (i - phase) % bar_every == 0
        if not on_bar and (i - phase) % stride != 0:
            continue
        if kept and beat - kept[-1] < min_gap_s:
            continue
        kept.append(beat)
    return kept


def beats_to_timeline_frames(
    beats: list[float],
    fps: float,
    music_start_frame: int = 0,
    music_in_frame: int = 0,
    music_out_frame: int | None = None,
    offset_seconds: float | None = None,
) -> tuple[list[int], int]:
    """Timeline frames of *beats*, and how many fell outside the music's used range.

    Through a music entry: ``start + round(beat * fps) - in``, keeping beats in
    ``[in, out]`` of the source. With *offset_seconds* (music starts at that
    timeline time, from its own beginning): ``round((offset + beat) * fps)``.
    """
    frames, skipped = [], 0
    for beat in beats:
        if offset_seconds is not None:
            frames.append(int(round((offset_seconds + beat) * fps)))
            continue
        source = int(round(beat * fps))
        if source < music_in_frame or (music_out_frame is not None and source > music_out_frame):
            skipped += 1
            continue
        frames.append(music_start_frame + source - music_in_frame)
    return sorted(set(frames)), skipped


def plan_beat_cut(clip_records: list[dict], beat_frames: list[int], min_clip_frames: int = 6) -> list[dict]:
    """New lengths so each cut after the first clip lands on the next selected beat.

    ``clip_records``: consecutive clips ``{start, length, in, source_frames}``
    (``source_frames`` None when unknown; optional ``gap_before`` = blank frames
    before the clip, kept as they are). The first clip keeps its start;
    each boundary moves to the next beat at least ``min_clip_frames`` after
    the clip's (new) start. A clip whose source cannot reach its beat uses
    what it has and is flagged ``off_beat``. With no beat left, clips keep
    their length. Clips are never dropped or reordered.
    """
    plan = []
    if not clip_records:
        return plan
    cursor = clip_records[0]["start"]
    beats = sorted(b for b in beat_frames)
    for k, record in enumerate(clip_records):
        if k:
            cursor += record.get("gap_before", 0)  # blanks between clips keep their length
        target = next((b for b in beats if b >= cursor + min_clip_frames), None)
        if target is None:
            length, off_beat, on = record["length"], False, None
        else:
            length = target - cursor
            max_len = (record["source_frames"] - record["in"]) if record.get("source_frames") else None
            off_beat = max_len is not None and length > max_len
            if off_beat:
                length = max_len
            on = None if off_beat else target
        plan.append({"start": cursor, "old_length": record["length"], "new_length": length,
                     "cut_frame": on, "off_beat": off_beat})
        cursor += length
    return plan


def clip_hits(track_records: list[dict], beat_frames: list[int]) -> tuple[dict[int, list[int]], int]:
    """``{clip_index: [entry-local frames]}`` for beats over clips, and the count over blanks.

    Beats after the track's last clip are neither hits nor blanks.
    """
    hits: dict[int, list[int]] = {}
    missed = 0
    track_end = max((r["start"] + r["length"] for r in track_records), default=0)
    for frame in beat_frames:
        if frame >= track_end:
            continue
        record = next((r for r in track_records if r["start"] <= frame <= r["start"] + r["length"] - 1), None)
        if record is None:
            missed += 1
            continue
        hits.setdefault(record["clip_index"], []).append(frame - record["start"])
    return hits, missed


def merge_pulses(local_frames: list[int], clip_length: int, rest, peak, attack: int, decay: int,
                 attack_easing: str = "linear", decay_easing: str = "linear") -> list[Keyframe]:
    """One keyframe track for several pulses that peak at *local_frames*.

    Each pulse: rest at ``f - attack``, peak at ``f``, rest at ``f + decay``. The
    next pulse's attack truncates the previous decay (no keyframe goes back in
    time); everything stays inside ``[0, clip_length - 1]``.
    """
    last = clip_length - 1
    out: dict[int, Keyframe] = {0: Keyframe(0, rest, "linear")}
    frames = sorted(f for f in set(local_frames) if 0 <= f <= last)
    for k, f in enumerate(frames):
        nxt = frames[k + 1] if k + 1 < len(frames) else None
        start = max(0, f - attack)
        if start < f and (start not in out or out[start].value == rest):
            out[start] = Keyframe(start, rest, attack_easing)
        out[f] = Keyframe(f, peak, decay_easing)
        end = min(last, f + decay)
        if nxt is not None and end >= nxt - attack:
            continue  # the next attack starts before this decay ends
        if end > f:
            out[end] = Keyframe(end, rest, "linear")
    return [out[f] for f in sorted(out)]


def flash_keyframes(local_frames: list[int], clip_length: int, strength: float = 1.0,
                    attack_frames: int = 1, decay_frames: int = 3) -> list[Keyframe]:
    """``brightness`` ``level`` keyframes: 1.0 at rest, ``1 + strength`` at each beat."""
    if strength <= 0:
        raise ValueError(f"strength must be > 0; got {strength}")
    return merge_pulses(local_frames, clip_length, 1.0, round(1.0 + strength, 4),
                        attack_frames, decay_frames)
