"""Pure helpers for speed ramping / time remapping (``speed_ramp``).

No I/O lives here: this module only does deterministic number crunching --
keyframe parsing, easing interpolation, and segment planning -- turning a
speed-ramp / time-remap description into a list of **constant-speed segments**
that the patcher realises as ``timewarp:`` producer swaps. All side effects
(parsing/serialising the project, snapshotting) live in the bundle module
``edit_mcp/server/bundles/speed_ramp.py``.

Why segments (not a native ``timeremap`` link)?
    Kdenlive's UI "Time Remap" maps output-time -> source-time with keyframes.
    MLT can express that with a ``timeremap`` *link*, but a link must live inside
    a ``<chain>`` and the project serializer here emits plain ``<producer>``
    elements, so the native route is not writable without serializer changes.
    The reliable, melt-proven route is to slice the clip at ramp boundaries and
    play each slice through a constant-speed ``timewarp:`` producer (the same
    machinery ``clip_speed`` uses -- verified: 2x halves the rendered duration).
    A smooth ease is approximated by subdividing each keyframe interval into many
    short constant-speed sub-segments. See
    ``docs/research/2026-07-03-tutorial-effect-analysis/speed-ramping.md``.

Two keyframe formats are accepted (JSON string or already-decoded list):

* **speed** -- ``[{"at_seconds": t, "speed": v}, ...]`` -- at source-time ``t``
  (offset within the clip, 0 = clip start) the playback speed is ``v``
  (``2.0`` = 2x faster / slow-motion is ``0.5``). Speed eases between keyframes.
* **timemap** -- ``[{"output_seconds": o, "source_seconds": s}, ...]`` -- at
  output-time ``o`` show source-time ``s``. Each consecutive pair is a constant
  speed ``= (s2 - s1) / (o2 - o1)``. Easing does not apply (the map is explicit).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

# MLT's timewarp producer accepts speeds in [0.01, 20] (see ``melt -query
# producer=timewarp``). We only ramp forward playback; reverse (negative speed)
# is ``effect_rewind``'s domain.
MIN_SPEED = 0.01
MAX_SPEED = 20.0

DEFAULT_EASING = "cubic"
DEFAULT_SUBDIVISIONS = 8


@dataclass(frozen=True)
class Segment:
    """A constant-speed slice of the clip, in source-frame offsets.

    ``src_in`` / ``src_out`` are **offsets within the clip** (0 = the clip's
    in-point), as integer source frames, half-open ``[src_in, src_out)``.
    ``speed`` is the playback multiplier for the slice.
    """

    src_in: int
    src_out: int
    speed: float

    @property
    def source_frames(self) -> int:
        return self.src_out - self.src_in


# ---------------------------------------------------------------------------
# easing
# ---------------------------------------------------------------------------

def _clamp01(t: float) -> float:
    return 0.0 if t < 0 else 1.0 if t > 1 else t


def ease(t: float, mode: str = DEFAULT_EASING) -> float:
    """Ease a normalised fraction ``t`` in [0, 1] -> eased fraction in [0, 1].

    Supported modes: ``linear``, ``cubic`` (smoothstep, ease-in-out),
    ``ease_in`` (quadratic), ``ease_out`` (quadratic). Unknown modes fall back
    to ``linear``.
    """
    t = _clamp01(t)
    if mode == "linear":
        return t
    if mode == "cubic":
        # smoothstep: 3t^2 - 2t^3 -- symmetric ease-in-out.
        return t * t * (3.0 - 2.0 * t)
    if mode == "ease_in":
        return t * t
    if mode == "ease_out":
        return t * (2.0 - t)
    return t


def interp_speed(v0: float, v1: float, frac: float, easing: str) -> float:
    """Interpolate speed from ``v0`` to ``v1`` at eased fraction ``frac``."""
    e = ease(frac, easing)
    return v0 + (v1 - v0) * e


# ---------------------------------------------------------------------------
# keyframe parsing / validation
# ---------------------------------------------------------------------------

def parse_keyframes(keyframes) -> list[dict]:
    """Decode ``keyframes`` (JSON string or list) into a list of dicts."""
    if isinstance(keyframes, str):
        try:
            keyframes = json.loads(keyframes)
        except json.JSONDecodeError as exc:
            raise ValueError(f"keyframes is not valid JSON: {exc}") from exc
    if not isinstance(keyframes, (list, tuple)):
        raise ValueError("keyframes must be a JSON array of objects")
    out: list[dict] = []
    for i, kf in enumerate(keyframes):
        if not isinstance(kf, dict):
            raise ValueError(f"keyframe {i} must be an object, got {type(kf).__name__}")
        out.append(dict(kf))
    if not out:
        raise ValueError("keyframes must contain at least one entry")
    return out


def keyframe_format(keyframes: list[dict]) -> str:
    """Classify a decoded keyframe list as ``"speed"`` or ``"timemap"``."""
    first = keyframes[0]
    if "output_seconds" in first or "source_seconds" in first:
        return "timemap"
    if "at_seconds" in first or "speed" in first:
        return "speed"
    raise ValueError(
        "unrecognised keyframe schema: expected keys {at_seconds, speed} or "
        "{output_seconds, source_seconds}"
    )


def _validate_speed(v: float, where: str) -> float:
    v = float(v)
    if not math.isfinite(v):
        raise ValueError(f"{where}: speed must be a finite number")
    if v < MIN_SPEED or v > MAX_SPEED:
        raise ValueError(
            f"{where}: speed {v:g} out of range [{MIN_SPEED}, {MAX_SPEED}]"
        )
    return v


# ---------------------------------------------------------------------------
# segment planning
# ---------------------------------------------------------------------------

def _merge_runs(segments: list[Segment]) -> list[Segment]:
    """Merge adjacent segments that share the same speed (fewer producers)."""
    merged: list[Segment] = []
    for seg in segments:
        if seg.src_out <= seg.src_in:
            continue
        if merged and abs(merged[-1].speed - seg.speed) < 1e-9 and merged[-1].src_out == seg.src_in:
            prev = merged[-1]
            merged[-1] = Segment(prev.src_in, seg.src_out, prev.speed)
        else:
            merged.append(seg)
    return merged


def _plan_speed_format(
    keyframes: list[dict],
    clip_frames: int,
    fps: float,
    easing: str,
    subdivisions: int,
) -> list[Segment]:
    # Normalise to (frame_offset, speed) sorted by time, clamped to the clip.
    pts: list[tuple[int, float]] = []
    for i, kf in enumerate(keyframes):
        at = float(kf.get("at_seconds", 0.0))
        if at < 0:
            raise ValueError(f"keyframe {i}: at_seconds must be >= 0")
        frame = int(round(at * fps))
        frame = max(0, min(frame, clip_frames))
        speed = _validate_speed(kf.get("speed", 1.0), f"keyframe {i}")
        pts.append((frame, speed))
    pts.sort(key=lambda p: p[0])

    # Edge coverage: hold the first/last speed out to the clip bounds.
    if pts[0][0] > 0:
        pts.insert(0, (0, pts[0][1]))
    if pts[-1][0] < clip_frames:
        pts.append((clip_frames, pts[-1][1]))

    segments: list[Segment] = []
    k = max(1, int(subdivisions))
    for (f0, v0), (f1, v1) in zip(pts, pts[1:]):
        if f1 <= f0:
            continue
        if abs(v1 - v0) < 1e-9:
            segments.append(Segment(f0, f1, v0))
            continue
        # Subdivide the interval; each sub-segment samples the eased curve at its
        # midpoint so the average speed tracks the ramp.
        span = f1 - f0
        steps = min(k, span)  # never more sub-segments than frames
        for j in range(steps):
            a = f0 + (span * j) // steps
            b = f0 + (span * (j + 1)) // steps
            if b <= a:
                continue
            mid = (j + 0.5) / steps
            v = _validate_speed(interp_speed(v0, v1, mid, easing), f"segment {j}")
            segments.append(Segment(a, b, v))
    return _merge_runs(segments)


def _plan_timemap_format(
    keyframes: list[dict],
    clip_frames: int,
    fps: float,
) -> list[Segment]:
    pts: list[tuple[float, float]] = []
    for i, kf in enumerate(keyframes):
        if "output_seconds" not in kf or "source_seconds" not in kf:
            raise ValueError(
                f"keyframe {i}: timemap entries need output_seconds and source_seconds"
            )
        o = float(kf["output_seconds"])
        s = float(kf["source_seconds"])
        if o < 0 or s < 0:
            raise ValueError(f"keyframe {i}: output/source seconds must be >= 0")
        pts.append((o, s))
    pts.sort(key=lambda p: p[0])
    if len(pts) < 2:
        raise ValueError("timemap format needs at least two keyframes")

    segments: list[Segment] = []
    for (o0, s0), (o1, s1) in zip(pts, pts[1:]):
        d_out = o1 - o0
        d_src = s1 - s0
        if d_out <= 0:
            raise ValueError("timemap output_seconds must strictly increase")
        if d_src <= 0:
            raise ValueError("timemap source_seconds must strictly increase (forward only)")
        speed = _validate_speed(d_src / d_out, "timemap segment")
        a = int(round(s0 * fps))
        b = int(round(s1 * fps))
        a = max(0, min(a, clip_frames))
        b = max(0, min(b, clip_frames))
        if b > a:
            segments.append(Segment(a, b, speed))
    return _merge_runs(segments)


def plan_segments(
    keyframes,
    clip_frames: int,
    fps: float,
    easing: str = DEFAULT_EASING,
    subdivisions: int = DEFAULT_SUBDIVISIONS,
) -> list[Segment]:
    """Plan the constant-speed segments for a ramp over a ``clip_frames`` clip.

    Returns segments in source-frame offsets covering ``[0, clip_frames)`` (for
    the speed format) or the mapped source span (timemap format). Raises
    ``ValueError`` on invalid input.
    """
    if clip_frames <= 0:
        raise ValueError(f"clip_frames must be > 0 (got {clip_frames})")
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    kfs = parse_keyframes(keyframes)
    fmt = keyframe_format(kfs)
    if fmt == "timemap":
        segs = _plan_timemap_format(kfs, clip_frames, fps)
    else:
        segs = _plan_speed_format(kfs, clip_frames, fps, easing, subdivisions)
    if not segs:
        raise ValueError("keyframes produced no non-empty segments")
    return segs


# ---------------------------------------------------------------------------
# frame math (shared with the patcher so expected == rendered)
# ---------------------------------------------------------------------------

def timewarp_entry(entry_in: int, src_in: int, src_out: int, speed: float) -> tuple[int, int]:
    """Map a source-frame slice to a ``timewarp`` producer's ``(in, out)``.

    A ``timewarp:{speed}`` producer plays source frame ``f`` at producer frame
    ``round(f / speed)``. For a source slice ``[entry_in+src_in, entry_in+src_out)``
    the entry spans producer frames ``[round(a/speed), round(b/speed) - 1]``.
    """
    a = entry_in + src_in
    b = entry_in + src_out
    tw_in = int(round(a / speed))
    tw_out = int(round(b / speed)) - 1
    if tw_out < tw_in:
        tw_out = tw_in
    return tw_in, tw_out


def total_output_frames(entry_in: int, segments: list[Segment]) -> int:
    """Total timeline frames the planned segments occupy after the swap."""
    total = 0
    for seg in segments:
        tw_in, tw_out = timewarp_entry(entry_in, seg.src_in, seg.src_out, seg.speed)
        total += tw_out - tw_in + 1
    return total


def source_output_frames(segments: list[Segment]) -> tuple[int, int]:
    """Return (total source frames covered, entry-in=0 output frames)."""
    src = sum(seg.source_frames for seg in segments)
    return src, total_output_frames(0, segments)
