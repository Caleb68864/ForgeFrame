"""Pan/zoom (Ken Burns) rect geometry -- pure functions.

Computes source-region rects for a keyframed ``affine``/``transform`` filter
from a project profile, clamps them to frame bounds, and emits an MLT rect
keyframe animation string via the shared keyframe pipeline
(``pipelines/keyframes.py`` -> ``build_keyframe_string``).

Convention: a rect ``(x, y, w, h)`` names the *source region* (in frame
pixels) that the transform scales to fill the output frame. A smaller region
zooms in; translating the region pans. All rects live inside
``[0, 0, W, H]`` -- see plan §5 (``subject_zoom``): "pad the subject rect ...
clamp to frame bounds". This module is the *static cousin* of
``subject_zoom``: no tracking/smoothing, just two hand-/preset-chosen rects
eased over time.

Pure-logic module: no XML I/O, no MCP, no filesystem.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    Keyframe,
    build_keyframe_string,
)

Rect = tuple[float, float, float, float]

# Visible-region fraction for the pan / ken-burns presets (leaves head-room to
# travel across the frame) and the zoomed-in region for the zoom presets.
_PAN_SCALE = 0.7
_ZOOM_SCALE = 0.6

PRESETS: tuple[str, ...] = (
    "zoom_in",
    "zoom_out",
    "pan_left_to_right",
    "pan_right_to_left",
    "pan_top_to_bottom",
    "pan_bottom_to_top",
    "kenburns_tl_br",
    "kenburns_br_tl",
    "kenburns_tr_bl",
    "kenburns_bl_tr",
)


def _as_four(rect: object) -> Rect:
    """Coerce a 4- or 5-element rect (x y w h [opacity]) to an ``(x,y,w,h)``.

    A 5th opacity element is accepted and dropped -- Ken Burns transforms the
    whole clip, so opacity is left to the keyframe pipeline (defaults to 1).
    """
    if not isinstance(rect, (list, tuple)) or len(rect) not in (4, 5):
        raise ValueError(
            f"rect must be a list/tuple of 4 or 5 numbers; got {rect!r}"
        )
    try:
        vals = tuple(float(v) for v in rect[:4])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"rect values must be numeric; got {rect!r}") from exc
    return vals  # type: ignore[return-value]


def clamp_rect(rect: object, width: int, height: int) -> Rect:
    """Clamp a rect so it lies fully within ``[0, 0, width, height]``.

    Width/height are floored to 1px and capped at the frame size; the origin
    is then constrained so ``x + w <= width`` and ``y + h <= height``.
    """
    if width <= 0 or height <= 0:
        raise ValueError(
            f"frame size must be positive; got width={width}, height={height}"
        )
    x, y, w, h = _as_four(rect)
    w = min(max(w, 1.0), float(width))
    h = min(max(h, 1.0), float(height))
    x = min(max(x, 0.0), float(width) - w)
    y = min(max(y, 0.0), float(height) - h)
    return (x, y, w, h)


def preset_rects(preset: str, width: int, height: int) -> tuple[Rect, Rect]:
    """Return the clamped ``(start_rect, end_rect)`` for a named preset.

    Geometry is derived entirely from the project profile ``(width, height)``
    so a preset scales correctly across 1080p / 4K / vertical.
    """
    if preset not in PRESETS:
        raise ValueError(
            f"unknown preset {preset!r}; valid presets: {PRESETS}"
        )
    w_f, h_f = float(width), float(height)

    full: Rect = (0.0, 0.0, w_f, h_f)

    # Centered zoomed-in region for zoom presets.
    zw, zh = w_f * _ZOOM_SCALE, h_f * _ZOOM_SCALE
    center: Rect = ((w_f - zw) / 2.0, (h_f - zh) / 2.0, zw, zh)

    # Travelling region for pan / ken-burns presets.
    pw, ph = w_f * _PAN_SCALE, h_f * _PAN_SCALE
    x_cen = (w_f - pw) / 2.0
    y_cen = (h_f - ph) / 2.0
    left: Rect = (0.0, y_cen, pw, ph)
    right: Rect = (w_f - pw, y_cen, pw, ph)
    top: Rect = (x_cen, 0.0, pw, ph)
    bottom: Rect = (x_cen, h_f - ph, pw, ph)
    tl: Rect = (0.0, 0.0, pw, ph)
    br: Rect = (w_f - pw, h_f - ph, pw, ph)
    tr: Rect = (w_f - pw, 0.0, pw, ph)
    bl: Rect = (0.0, h_f - ph, pw, ph)

    table: dict[str, tuple[Rect, Rect]] = {
        "zoom_in": (full, center),
        "zoom_out": (center, full),
        "pan_left_to_right": (left, right),
        "pan_right_to_left": (right, left),
        "pan_top_to_bottom": (top, bottom),
        "pan_bottom_to_top": (bottom, top),
        "kenburns_tl_br": (tl, br),
        "kenburns_br_tl": (br, tl),
        "kenburns_tr_bl": (tr, bl),
        "kenburns_bl_tr": (bl, tr),
    }
    start, end = table[preset]
    return clamp_rect(start, width, height), clamp_rect(end, width, height)


def build_pan_zoom_keyframes(
    start_rect: object,
    end_rect: object,
    duration_frames: int,
    fps: float,
    easing: str = "cubic_in_out",
    hold_frames: int = 0,
    ease_family_default: str = "cubic",
) -> str:
    """Emit an MLT rect keyframe animation string for a pan/zoom move.

    The move runs ``start_rect -> end_rect`` over ``duration_frames``. When
    ``hold_frames > 0`` the start rect is held for ``hold_frames`` (a lead-in
    hold) before the eased move begins. ``easing`` names the interpolation of
    the moving segment (any name accepted by ``resolve_easing``).
    """
    if not isinstance(duration_frames, int) or isinstance(duration_frames, bool):
        raise ValueError(f"duration_frames must be int; got {duration_frames!r}")
    if duration_frames <= 0:
        raise ValueError(f"duration_frames must be > 0; got {duration_frames}")
    if not isinstance(hold_frames, int) or isinstance(hold_frames, bool):
        raise ValueError(f"hold_frames must be int; got {hold_frames!r}")
    if hold_frames < 0:
        raise ValueError(f"hold_frames must be >= 0; got {hold_frames}")

    start = list(_as_four(start_rect))
    end = list(_as_four(end_rect))

    if hold_frames > 0:
        keyframes = [
            Keyframe(0, start, "linear"),
            Keyframe(hold_frames, start, easing),
            Keyframe(hold_frames + duration_frames, end, "linear"),
        ]
    else:
        keyframes = [
            Keyframe(0, start, easing),
            Keyframe(duration_frames, end, "linear"),
        ]

    return build_keyframe_string("rect", keyframes, fps, ease_family_default)


def build_pan_zoom_transform_keyframes(
    start_region: object,
    end_region: object,
    width: int,
    height: int,
    duration_frames: int,
    fps: float,
    easing: str = "cubic_in_out",
    hold_frames: int = 0,
    ease_family_default: str = "cubic",
) -> str:
    """Emit the **render-correct** ``affine`` ``transition.rect`` keyframe string.

    ``build_pan_zoom_keyframes`` reasons in intuitive *source-region* space (the
    rect that gets scaled up to fill the frame). But a bare ``rect`` on the
    ``affine``/``transform`` filter is a **proven no-op** on this MLT build --
    ``affine`` reads ``transition.rect``, which names where the *whole* source
    frame is placed/scaled, not a crop. This helper converts each source region
    to the affine *destination* rect (via ``motion_track.region_to_transform_rect``,
    the same math the tracked ``build_zoom_keyframes`` uses) and then builds the
    keyframe animation, so the transform actually moves pixels.

    Render-proof: ``tests/integration/external/test_pan_zoom_render.py``.
    """
    from workshop_video_brain.edit_mcp.pipelines.motion_track import (
        region_to_transform_rect,
    )

    d_start = region_to_transform_rect(
        clamp_rect(start_region, width, height), width, height
    )
    d_end = region_to_transform_rect(
        clamp_rect(end_region, width, height), width, height
    )
    return build_pan_zoom_keyframes(
        d_start, d_end, duration_frames, fps,
        easing=easing, hold_frames=hold_frames,
        ease_family_default=ease_family_default,
    )
