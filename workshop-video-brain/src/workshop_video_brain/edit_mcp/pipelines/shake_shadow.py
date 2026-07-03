"""Pure-logic helpers for the ``effect_camera_shake`` / ``effect_drop_shadow``
bundle tools (Nuxttux *"Smooth Transitions, Camera Shake, Drop Shadow"*
tutorial, video ``V0_yp-ziqvI``).

The tutorial demonstrates two downloadable Kdenlive **presets** ("camera Shake
medium, r for rotation" and a "drop shadow") without exposing their internals.
This module reconstructs the achievable mechanics from existing primitives:

* **Camera shake** -- a deterministic, seeded pseudo-random keyframed
  ``qtblend`` (Transform) jitter. The clip is slightly overscanned (zoomed) so
  the jittered position never reveals black frame edges, and a dense
  position/rotation keyframe animation is emitted via the shared keyframe
  pipeline. A fixed seed makes every run byte-for-byte reproducible.

* **Drop shadow** -- the dedicated MLT ``dropshadow`` service ("Create a shadow
  effect from the alpha channel"), the clean, single-filter path for PiP / title
  layers. No duplicate-darken-offset-blur recipe is required.

Pure logic only: no XML I/O, no MCP decorators, no filesystem. The MCP tools in
``server/bundles/shake_shadow.py`` consume these functions and write filters via
the shared ``_build_filter_xml`` / ``patcher.insert_effect_xml`` machinery.
"""
from __future__ import annotations

import random

from .keyframes import Keyframe, build_keyframe_string

# MLT services (both present in the effect catalog).
SHAKE_SERVICE = "qtblend"      # modern Kdenlive Transform: rect + rotation.
DROP_SHADOW_SERVICE = "dropshadow"

# Tuning constants (tutorial preset "medium" ~= intensity 0.5).
ZOOM_PER_INTENSITY = 0.12   # overscan headroom grows with intensity.
AMP_FRACTION = 0.9          # jitter uses <=90% of the overscan margin.
MAX_ROTATION_DEG = 2.5      # peak roll (degrees) at full intensity.

# Deterministic fallback seed so results are reproducible even when the caller
# passes ``seed=None``.
DEFAULT_SEED = 0


def _clamp01(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric in [0.0, 1.0]; got {value!r}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be in [0.0, 1.0]; got {value}")
    return float(value)


def _clamp_offset(offset: float, margin: float) -> float:
    """Clamp a jitter offset into ``[-margin, margin]`` so edges stay covered."""
    if offset < -margin:
        return -margin
    if offset > margin:
        return margin
    return offset


def _require_positive_int(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{name} must be an int; got {value!r}")
    if value <= 0:
        raise ValueError(f"{name} must be > 0; got {value}")
    return value


def shake_step_frames(frequency_hz: float, fps: float) -> int:
    """Frames between successive shake keyframes for a given shake frequency."""
    if isinstance(frequency_hz, bool) or not isinstance(frequency_hz, (int, float)):
        raise ValueError(f"frequency_hz must be numeric; got {frequency_hz!r}")
    if frequency_hz <= 0:
        raise ValueError(f"frequency_hz must be > 0; got {frequency_hz}")
    if fps <= 0:
        raise ValueError(f"fps must be > 0; got {fps}")
    return max(1, round(float(fps) / float(frequency_hz)))


def _shake_frames(start_frame: int, end_frame: int, step: int) -> list[int]:
    """Inclusive frame grid ``[start .. end]`` stepping by ``step``.

    The final frame is always included even if it does not fall on the grid.
    """
    frames = list(range(start_frame, end_frame, step))
    if frames[-1] != end_frame:
        frames.append(end_frame)
    return frames


def camera_shake_keyframes(
    width: int,
    height: int,
    start_frame: int,
    end_frame: int,
    intensity: float = 0.5,
    frequency_hz: float = 8.0,
    fps: float = 25.0,
    seed: int | None = None,
    rotation: bool = False,
) -> dict:
    """Build deterministic camera-shake keyframe strings for a ``qtblend`` filter.

    Returns a dict with:

    * ``rect``      -- MLT rect keyframe string ``x y w h opacity`` (overscanned
      + jittered position).
    * ``rotation``  -- MLT scalar keyframe string (degrees), or ``None`` when
      ``rotation`` is False.
    * ``keyframe_count`` / ``step_frames`` / ``zoom`` / ``amplitude_px``
      (``(ax, ay)``) -- introspection metadata.

    The jitter is produced by a ``random.Random`` seeded with ``seed`` (or
    ``DEFAULT_SEED`` when ``seed is None``), so identical inputs yield identical
    output. The clip is overscanned by ``ZOOM_PER_INTENSITY * intensity`` and
    every offset is clamped into the overscan margin so black frame edges are
    never revealed. The first keyframe is anchored at rest (no offset / 0
    rotation) to avoid a pop on entry.
    """
    if isinstance(width, bool) or not isinstance(width, int) or width <= 0:
        raise ValueError(f"width must be a positive int; got {width!r}")
    if isinstance(height, bool) or not isinstance(height, int) or height <= 0:
        raise ValueError(f"height must be a positive int; got {height!r}")
    if isinstance(start_frame, bool) or not isinstance(start_frame, int):
        raise ValueError(f"start_frame must be int; got {start_frame!r}")
    if isinstance(end_frame, bool) or not isinstance(end_frame, int):
        raise ValueError(f"end_frame must be int; got {end_frame!r}")
    if start_frame < 0:
        raise ValueError(f"start_frame must be >= 0; got {start_frame}")
    if end_frame <= start_frame:
        raise ValueError(
            f"end_frame ({end_frame}) must be > start_frame ({start_frame})"
        )
    intensity = _clamp01(intensity, "intensity")
    if fps <= 0:
        raise ValueError(f"fps must be > 0; got {fps}")

    step = shake_step_frames(frequency_hz, fps)

    # Overscan: enlarge the frame so shifted content still covers the viewport.
    zoom = 1.0 + ZOOM_PER_INTENSITY * intensity
    scaled_w = round(width * zoom)
    scaled_h = round(height * zoom)
    margin_x = (scaled_w - width) / 2.0
    margin_y = (scaled_h - height) / 2.0
    base_x = -margin_x  # centered enlarged rect.
    base_y = -margin_y
    amp_x = AMP_FRACTION * margin_x
    amp_y = AMP_FRACTION * margin_y
    max_angle = MAX_ROTATION_DEG * intensity

    rng = random.Random(DEFAULT_SEED if seed is None else seed)
    frames = _shake_frames(start_frame, end_frame, step)

    rect_kfs: list[Keyframe] = []
    rot_kfs: list[Keyframe] = []
    for i, f in enumerate(frames):
        if i == 0:
            dx = dy = 0.0
            angle = 0.0
        else:
            dx = _clamp_offset(rng.uniform(-amp_x, amp_x), margin_x)
            dy = _clamp_offset(rng.uniform(-amp_y, amp_y), margin_y)
            angle = (
                _clamp_offset(rng.uniform(-max_angle, max_angle), max_angle)
                if rotation
                else 0.0
            )
        x = round(base_x + dx, 3)
        y = round(base_y + dy, 3)
        rect_kfs.append(
            Keyframe(frame=f, value=(x, y, scaled_w, scaled_h, 1.0), easing="linear")
        )
        if rotation:
            rot_kfs.append(
                Keyframe(frame=f, value=round(angle, 3), easing="linear")
            )

    rect_str = build_keyframe_string("rect", rect_kfs, fps)
    rot_str = build_keyframe_string("scalar", rot_kfs, fps) if rotation else None

    return {
        "rect": rect_str,
        "rotation": rot_str,
        "keyframe_count": len(frames),
        "step_frames": step,
        "zoom": zoom,
        "amplitude_px": (amp_x, amp_y),
    }


def drop_shadow_params(
    blur_radius: int = 6,
    offset_x: int = 8,
    offset_y: int = 8,
    color: str = "#b4000000",
) -> dict[str, str]:
    """Return ``dropshadow`` filter properties for a PiP / title layer.

    The MLT ``dropshadow`` service derives the shadow from the layer's alpha
    channel, so it is the clean single-filter path (no duplicate-darken-offset
    recipe needed).

    Parameters
    ----------
    blur_radius:
        Shadow blur radius in pixels (``>= 0``).
    offset_x, offset_y:
        Shadow displacement in pixels (positive = right / down).
    color:
        Shadow color as Kdenlive ``#AARRGGBB`` hex (alpha first). Default is
        70%-opacity black (``#b4000000``).
    """
    if isinstance(blur_radius, bool) or not isinstance(blur_radius, int):
        raise ValueError(f"blur_radius must be an int; got {blur_radius!r}")
    if blur_radius < 0:
        raise ValueError(f"blur_radius must be >= 0; got {blur_radius}")
    for name, val in (("offset_x", offset_x), ("offset_y", offset_y)):
        if isinstance(val, bool) or not isinstance(val, int):
            raise ValueError(f"{name} must be an int; got {val!r}")
    if not isinstance(color, str) or not color.strip():
        raise ValueError(f"color must be a non-empty hex string; got {color!r}")

    return {
        "radius": str(blur_radius),
        "x": str(offset_x),
        "y": str(offset_y),
        "color": color.strip(),
    }
