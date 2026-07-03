"""Zoom / whip-pan transition -- pure keyframe planning.

Derived from the "Zoom / Whip-Pan Transition" Kdenlive tutorial by Nuxttux
Creative Studio (https://www.youtube.com/watch?v=ex7GoLFOnio). Encodes the
standard technique: the outgoing clip punches in (transform scale ramp) and
whip-pans off toward ``direction`` while a directional blur ramps up to the
cut; the incoming clip mirrors the move -- entering punched + panned from the
opposite side and settling back to full frame while the directional blur ramps
back down.

Pure-logic module. No XML I/O, no MCP, no filesystem. Keyframe strings are
built via ``keyframes.build_keyframe_string`` so the MLT operator table stays
authoritative (docs/reference/mlt/keyframe-operators.md).

Honest-subset caveats (docs/plans/2026-07-03-kdenlive-mcp-improvements.md, S1.1):
- The Transform effect is emitted as ``mlt_service="affine"`` with a ``rect``
  property, matching the existing keyframe fixture/machinery. The exact MLT
  service/property mapping for Kdenlive "Transform" (affine vs qtblend) is an
  assumption, not verified against melt render output.
- Filters carry ``track``/``clip_index`` attributes (root-level placement) so
  the same-project patcher can round-trip them; whether MLT associates such
  root filters with the clip is the open S1.1 question.
"""
from __future__ import annotations

from typing import Any

from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    VALID_EASE_FAMILIES,
    Keyframe,
    build_keyframe_string,
)

# --------------------------------------------------------------------------
# Effect identity constants (single source of truth for the bundle tool).
# --------------------------------------------------------------------------

TRANSFORM_SERVICE = "affine"
TRANSFORM_KDENLIVE_ID = "transform"
TRANSFORM_RECT_PROP = "rect"

DBLUR_SERVICE = "avfilter.dblur"
DBLUR_KDENLIVE_ID = "avfilter_dblur"
DBLUR_ANGLE_PROP = "av.angle"
DBLUR_RADIUS_PROP = "av.radius"

DIRECTIONS: frozenset[str] = frozenset({"left", "right", "up", "down"})
# Easing names accepted as-is (non-directional); families compose _in/_out.
_NON_DIRECTIONAL: frozenset[str] = frozenset(
    {"linear", "smooth", "hold", "discrete", "step"}
)

_OPPOSITE: dict[str, str] = {
    "left": "right",
    "right": "left",
    "up": "down",
    "down": "up",
}


def _blur_angle(direction: str) -> float:
    """Directional-blur angle: horizontal for left/right, vertical for up/down."""
    return 0.0 if direction in ("left", "right") else 90.0


def _pan_offset(direction: str, pan_x: float, pan_y: float) -> tuple[float, float]:
    """Signed (dx, dy) pan for a whip toward ``direction``."""
    if direction == "left":
        return (-pan_x, 0.0)
    if direction == "right":
        return (pan_x, 0.0)
    if direction == "up":
        return (0.0, -pan_y)
    if direction == "down":
        return (0.0, pan_y)
    raise ValueError(f"unknown direction {direction!r}; use one of {sorted(DIRECTIONS)}")


def _ease_name(easing: str, ease_dir: str) -> str:
    """Compose a keyframe easing name.

    Families (``cubic``, ``expo`` ...) compose with ``ease_dir`` (``in``/``out``)
    to accelerate into the cut / decelerate out of it. Non-directional names
    (``linear``, ``smooth`` ...) pass through unchanged.
    """
    if easing in VALID_EASE_FAMILIES:
        return f"{easing}_{ease_dir}"
    if easing in _NON_DIRECTIONAL:
        return easing
    raise ValueError(
        f"unknown easing {easing!r}; use an ease family "
        f"{sorted(VALID_EASE_FAMILIES)} or one of {sorted(_NON_DIRECTIONAL)}"
    )


def _punched_rect(
    width: float, height: float, zoom: float, dx: float, dy: float
) -> list[float]:
    """Rect ``[x, y, w, h, opacity]`` for a centred zoom of ``zoom`` plus pan."""
    w = width * zoom
    h = height * zoom
    x = (width - w) / 2.0 + dx
    y = (height - h) / 2.0 + dy
    return [round(x, 3), round(y, 3), round(w, 3), round(h, 3), 1]


def _full_rect(width: float, height: float) -> list[float]:
    return [0, 0, round(float(width), 3), round(float(height), 3), 1]


def build_zoom_whip_plan(
    *,
    fps: float,
    width: int,
    height: int,
    out_clip_frames: int,
    in_clip_frames: int,
    direction: str = "left",
    duration_frames: int = 12,
    zoom_amount: float = 1.4,
    blur: float = 6.0,
    easing: str = "cubic",
    pan_fraction: float = 0.75,
) -> dict[str, Any]:
    """Compute all keyframe strings for a zoom/whip-pan transition.

    Parameters
    ----------
    fps:
        Project frame rate (drives frame -> timestamp normalization).
    width, height:
        Project profile dimensions in pixels.
    out_clip_frames, in_clip_frames:
        Frame length of the outgoing / incoming clip. The punch occupies the
        last ``duration_frames`` of the outgoing clip and the first
        ``duration_frames`` of the incoming clip.
    direction:
        Whip direction: the outgoing clip flies off toward ``direction``; the
        incoming clip enters from the opposite side.
    duration_frames:
        Length of each half of the transition, in frames.
    zoom_amount:
        Peak scale multiplier at the cut (1.4 = 140%).
    blur:
        Peak directional-blur radius at the cut.
    easing:
        Ease family (``cubic``) or a non-directional name (``linear``).
    pan_fraction:
        Fraction of the available head-room used for the whip pan (0..1).
        1.0 pans exactly to the frame edge; <1.0 keeps a margin.

    Returns
    -------
    dict with ``out`` / ``in`` sub-dicts, each carrying ``transform_rect``,
    ``blur_radius`` (MLT keyframe strings) and ``blur_angle``, plus the frame
    markers used.
    """
    if direction not in DIRECTIONS:
        raise ValueError(
            f"direction must be one of {sorted(DIRECTIONS)}; got {direction!r}"
        )
    if duration_frames < 1:
        raise ValueError(f"duration_frames must be >= 1; got {duration_frames}")
    if zoom_amount <= 1.0:
        raise ValueError(f"zoom_amount must be > 1.0; got {zoom_amount}")
    if blur < 0:
        raise ValueError(f"blur must be >= 0; got {blur}")
    if not 0.0 <= pan_fraction <= 1.0:
        raise ValueError(f"pan_fraction must be in [0, 1]; got {pan_fraction}")
    if out_clip_frames < 1 or in_clip_frames < 1:
        raise ValueError("clip frame lengths must be >= 1")
    # Validate easing early (raises for unknown names).
    _ease_name(easing, "in")

    # Available head-room after the zoom, per axis, then scaled by pan_fraction.
    pan_x = pan_fraction * (width * zoom_amount - width) / 2.0
    pan_y = pan_fraction * (height * zoom_amount - height) / 2.0

    full = _full_rect(width, height)
    angle = _blur_angle(direction)

    ease_in = _ease_name(easing, "in")
    ease_out = _ease_name(easing, "out")

    # --- Outgoing clip: full -> punched/panned toward `direction`, blur 0 -> peak.
    out_start = max(0, out_clip_frames - duration_frames)
    out_end = out_clip_frames - 1
    if out_end <= out_start:
        out_end = out_start + 1
    out_dx, out_dy = _pan_offset(direction, pan_x, pan_y)
    out_punched = _punched_rect(width, height, zoom_amount, out_dx, out_dy)

    out_rect = build_keyframe_string(
        "rect",
        [
            Keyframe(frame=out_start, value=full, easing=ease_in),
            Keyframe(frame=out_end, value=out_punched, easing="linear"),
        ],
        fps,
        easing if easing in VALID_EASE_FAMILIES else "cubic",
    )
    out_blur = build_keyframe_string(
        "scalar",
        [
            Keyframe(frame=out_start, value=0.0, easing=ease_in),
            Keyframe(frame=out_end, value=blur, easing="linear"),
        ],
        fps,
        easing if easing in VALID_EASE_FAMILIES else "cubic",
    )

    # --- Incoming clip: punched/panned from opposite side -> full, blur peak -> 0.
    in_start = 0
    in_end = min(duration_frames, in_clip_frames - 1)
    if in_end <= in_start:
        in_end = in_start + 1
    in_dx, in_dy = _pan_offset(_OPPOSITE[direction], pan_x, pan_y)
    in_punched = _punched_rect(width, height, zoom_amount, in_dx, in_dy)

    in_rect = build_keyframe_string(
        "rect",
        [
            Keyframe(frame=in_start, value=in_punched, easing=ease_out),
            Keyframe(frame=in_end, value=full, easing="linear"),
        ],
        fps,
        easing if easing in VALID_EASE_FAMILIES else "cubic",
    )
    in_blur = build_keyframe_string(
        "scalar",
        [
            Keyframe(frame=in_start, value=blur, easing=ease_out),
            Keyframe(frame=in_end, value=0.0, easing="linear"),
        ],
        fps,
        easing if easing in VALID_EASE_FAMILIES else "cubic",
    )

    return {
        "fps": fps,
        "direction": direction,
        "duration_frames": duration_frames,
        "zoom_amount": zoom_amount,
        "blur": blur,
        "easing": easing,
        "blur_angle": angle,
        "out": {
            "start_frame": out_start,
            "end_frame": out_end,
            "transform_rect": out_rect,
            "blur_radius": out_blur,
            "blur_angle": angle,
        },
        "in": {
            "start_frame": in_start,
            "end_frame": in_end,
            "transform_rect": in_rect,
            "blur_radius": in_blur,
            "blur_angle": angle,
        },
    }
