"""Named camera moves for a ``qtblend`` filter: zoom punch, orbit, handheld (pure).

Same contract as ``shake_shadow.camera_shake_keyframes``: each returns
``{"rect", "rotation" (or None), "keyframe_count", "zoom", ...}`` with
entry-local frames. The clip is overscanned so every keyframe's rect covers
``[0, 0, W, H]`` (no black edges), rotation keyframes share the rect's
timestamps, and the first keyframe is at rest (no pop on entry).
Ken Burns / push / pull / pans stay in ``pan_zoom``; jitter stays in
``shake_shadow``.
"""
from __future__ import annotations

import math
import random

from workshop_video_brain.edit_mcp.pipelines.easing import bake_keyframes
from workshop_video_brain.edit_mcp.pipelines.keyframes import Keyframe, build_keyframe_string
from workshop_video_brain.edit_mcp.pipelines.shake_shadow import shake_step_frames

MOVES = ("zoom_punch", "orbit", "handheld")

#: (px, degrees) at 1080p width 1920; scaled to the profile width.
HANDHELD_PRESETS = {"subtle": (2.0, 0.4), "medium": (6.0, 1.0), "aggressive": (14.0, 2.2)}


def _check_size(width: int, height: int) -> None:
    for name, value in (("width", width), ("height", height)):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} must be a positive int; got {value!r}")


def _rect(x: float, y: float, w: float, h: float) -> tuple:
    return (round(x, 3), round(y, 3), round(w, 3), round(h, 3), 1.0)


def _clamp_cover(x: float, w: float, size: int) -> float:
    """Keep a rect of width *w* (>= size) covering [0, size]: x in [size - w, 0]."""
    return min(0.0, max(size - w, x))


def zoom_punch(
    width: int,
    height: int,
    at_frame: int,
    fps: float,
    intensity: float = 0.15,
    attack_frames: int = 3,
    decay_frames: int = 10,
    anchor: tuple[float, float] = (0.5, 0.5),
    attack_easing: str = "ease_out_cubic",
    decay_easing: str = "ease_in_out_sine",
) -> dict:
    """A quick push to ``1 + intensity`` that peaks exactly at *at_frame*, then settles back.

    The attack starts ``attack_frames`` earlier (from frame 0 at the latest).
    Native MLT easing operators; the zoom centres on *anchor* (fractions of the
    frame) but stays clamped so the frame is always covered.
    """
    _check_size(width, height)
    if at_frame < 0:
        raise ValueError(f"at_frame must be >= 0; got {at_frame}")
    if not 0 < intensity <= 2:
        raise ValueError(f"intensity must be in (0, 2]; got {intensity}")
    if attack_frames < 1 or decay_frames < 1:
        raise ValueError("attack_frames and decay_frames must be >= 1")
    scale = 1.0 + intensity
    w, h = width * scale, height * scale
    ax, ay = anchor
    x = _clamp_cover(-(w - width) * ax, w, width)
    y = _clamp_cover(-(h - height) * ay, h, height)
    rest = _rect(0, 0, width, height)
    start = max(0, at_frame - attack_frames)
    frames = []
    if start > 0:
        frames.append(Keyframe(frame=0, value=rest, easing="linear"))
    if at_frame > 0:
        frames.append(Keyframe(frame=start, value=rest, easing=attack_easing))
    frames.append(Keyframe(frame=at_frame, value=_rect(x, y, w, h), easing=decay_easing))
    frames.append(Keyframe(frame=at_frame + decay_frames, value=rest, easing="linear"))
    return {"rect": build_keyframe_string("rect", frames, fps), "rotation": None,
            "keyframe_count": len(frames), "zoom": scale, "peak_frame": at_frame}


def orbit(
    width: int,
    height: int,
    start_frame: int,
    end_frame: int,
    fps: float,
    radius_px: float | None = None,
    revolutions: float = 1.0,
    samples_per_rev: int = 24,
) -> dict:
    """The (overscanned) frame drifts around a circle that passes through its rest position."""
    _check_size(width, height)
    if start_frame < 0 or end_frame <= start_frame:
        raise ValueError(f"need 0 <= start_frame < end_frame; got {start_frame}, {end_frame}")
    if revolutions <= 0:
        raise ValueError(f"revolutions must be > 0; got {revolutions}")
    r = float(radius_px) if radius_px is not None else 0.03 * width
    if r <= 0:
        raise ValueError(f"radius_px must be > 0; got {radius_px}")
    # The circle's centre sits r to the left of rest, so x travels 2r and y +-r.
    # +4 px: 2 px of safety per side against edge anti-aliasing.
    zoom = max((width + 4 * r + 4) / width, (height + 2 * r + 4) / height)
    w, h = width * zoom, height * zoom
    x0, y0 = -(w - width) / 2, -(h - height) / 2
    n = max(2, math.ceil(revolutions * samples_per_rev))
    span = end_frame - start_frame
    keyframes = []
    last_frame = None
    for i in range(n + 1):
        frame = start_frame + round(span * i / n)
        if frame == last_frame:
            continue
        theta = 2 * math.pi * revolutions * i / n
        x = _clamp_cover(x0 - r + r * math.cos(theta), w, width)
        y = _clamp_cover(y0 + r * math.sin(theta), h, height)
        keyframes.append(Keyframe(frame=frame, value=_rect(x, y, w, h), easing="linear"))
        last_frame = frame
    return {"rect": build_keyframe_string("rect", keyframes, fps), "rotation": None,
            "keyframe_count": len(keyframes), "zoom": zoom, "radius_px": r}


def handheld(
    width: int,
    height: int,
    start_frame: int,
    end_frame: int,
    fps: float,
    intensity: str = "medium",
    frequency_hz: float = 1.5,
    seed: int | None = None,
    rotation: bool = True,
    bake_step: int = 2,
) -> dict:
    """A slow, eased wander between seeded random offsets (and a little roll); starts and ends at rest."""
    _check_size(width, height)
    if intensity not in HANDHELD_PRESETS:
        raise ValueError(f"intensity must be one of {sorted(HANDHELD_PRESETS)}; got {intensity!r}")
    if start_frame < 0 or end_frame <= start_frame:
        raise ValueError(f"need 0 <= start_frame < end_frame; got {start_frame}, {end_frame}")
    px, deg = HANDHELD_PRESETS[intensity]
    amp = px * width / 1920.0
    max_angle = deg if rotation else 0.0
    a = math.radians(max_angle)
    # Overscan that covers the frame at the largest offset AND the largest roll
    # (qtblend rotates about the rect centre with rotate_center=1).
    zoom = max(1.08,
               (width * math.cos(a) + height * math.sin(a) + 2 * amp + 4) / width,
               (height * math.cos(a) + width * math.sin(a) + 2 * amp + 4) / height)
    w, h = width * zoom, height * zoom
    x0, y0 = -(w - width) / 2, -(h - height) / 2
    step = shake_step_frames(frequency_hz, fps)
    grid = list(range(start_frame, end_frame, step))
    if grid[-1] != end_frame:
        grid.append(end_frame)
    rng = random.Random(1729 if seed is None else seed)
    rect_kfs, rot_kfs = [], []
    for i, frame in enumerate(grid):
        at_rest = i in (0, len(grid) - 1)
        dx = 0.0 if at_rest else rng.uniform(-amp, amp)
        dy = 0.0 if at_rest else rng.uniform(-amp, amp)
        angle = 0.0 if at_rest or not rotation else rng.uniform(-max_angle, max_angle)
        rect_kfs.append(Keyframe(frame=frame, value=list(_rect(x0 + dx, y0 + dy, w, h)), easing="ease_in_out_sine"))
        rot_kfs.append(Keyframe(frame=frame, value=round(angle, 3), easing="ease_in_out_sine"))
    rect_baked = bake_keyframes(rect_kfs, step=bake_step)
    rot_baked = bake_keyframes(rot_kfs, step=bake_step)
    return {"rect": build_keyframe_string("rect", rect_baked, fps),
            "rotation": build_keyframe_string("scalar", rot_baked, fps) if rotation else None,
            "keyframe_count": len(rect_baked), "zoom": zoom, "amplitude_px": amp,
            "max_rotation_deg": max_angle}
