"""Pure logic for the light-wash ("Color Wash VFX") bundle tool.

Reproduces the lightsaber-style *light wash* look taught in Photolearningism's
"Master Color Wash VFX in Kdenlive" tutorial (video id ``X0CnXskcBpc``). The
tutorial layers a **colorize** (hue / saturation / lightness), a **transparency**
(tone-down), and a **brightness & contrast** boost, scoped to the subject with a
rotoscoping mask, to simulate coloured light spilling onto a subject and room.

This module is pure logic: no XML I/O, no MCP decorators, no filesystem. It only
computes the ``(mlt_service, property_dict)`` tuples for the filter stack; the
MCP tool (``effect_color_wash``) does the snapshot + XML insertion.

Honest-subset notes
--------------------
The bundle composes only the *whole-clip* colour-grade filters from the
tutorial. Two pieces of the tutorial are **not** reproduced here because the
underlying primitives are missing / blocked (see the analysis report
``docs/research/2026-07-03-tutorial-effect-analysis/color-wash-vfx.md``):

* **Rotoscoping-mask scoping** — the tutorial confines the wash to the subject
  (and, on a second layer, to the room) with an *animated* rotoscoping mask.
  ``masking._spline_json`` emits only frame 0, so per-frame roto is a known
  hard blocker. The wash here is applied to the whole clip; region-scoping must
  be added separately (static only) via ``mask_set`` / ``mask_apply``.
* **Multi-layer bleed** — the tutorial duplicates the clip onto under-layers so
  the transparency has an opaque layer to bleed onto. Cross-track clip
  duplication is not an available primitive, so a single clip is graded.

The stack parameters are static (like ``effect_glitch_stack``). The tutorial
keyframes lightness / brightness to pulse the wash with saber distance; a caller
can keyframe those afterwards with ``effect_keyframe_set_scalar``.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines._common import (
    check_unit_interval as _check_unit,
)


# Named wash colours -> normalized ``frei0r.colorize`` hue (0.0..1.0). MLT stores
# frei0r params normalized regardless of the frei0r display range (0..360 deg).
COLOR_HUES: dict[str, float] = {
    "red": 0.0,
    "orange": 0.08,
    "yellow": 0.15,
    "green": 0.33,
    "cyan": 0.5,
    "blue": 0.62,
    "purple": 0.78,
    "magenta": 0.9,
}


# Canonical stack order: colorize (wash tint) -> transparency (tone down)
# -> brightness (glow lift) -> contrast. Mirrors the tutorial's top-to-bottom
# effect order on the washed clip.
COLOR_WASH_SERVICES: tuple[str, ...] = (
    "frei0r.colorize",
    "frei0r.transparency",
    "frei0r.brightness",
    "frei0r.contrast0r",
)


def resolve_hue(color: object) -> float:
    """Resolve a colour name or normalized float to a hue in ``[0.0, 1.0]``.

    Accepts a named colour (see :data:`COLOR_HUES`), a float in ``[0.0, 1.0]``,
    or a numeric string. Raises ``ValueError`` otherwise.
    """
    if isinstance(color, bool):  # bool is an int subclass; reject explicitly.
        raise ValueError(f"color must be a name or float in [0.0, 1.0]; got {color!r}")
    if isinstance(color, (int, float)):
        hue = float(color)
        if not 0.0 <= hue <= 1.0:
            raise ValueError(f"numeric hue must be in [0.0, 1.0]; got {hue}")
        return hue
    if isinstance(color, str):
        key = color.strip().lower()
        if key in COLOR_HUES:
            return COLOR_HUES[key]
        try:
            hue = float(key)
        except ValueError:
            raise ValueError(
                f"unknown color {color!r}; use one of {sorted(COLOR_HUES)} "
                f"or a float in [0.0, 1.0]"
            ) from None
        if not 0.0 <= hue <= 1.0:
            raise ValueError(f"numeric hue must be in [0.0, 1.0]; got {hue}")
        return hue
    raise ValueError(f"color must be a name or float in [0.0, 1.0]; got {color!r}")


# ``_check_unit`` is imported from ``pipelines/_common`` (check_unit_interval);
# the identical copy that lived here was merged in the consistency pass.


def color_wash_params(
    color: object = "blue",
    intensity: float = 0.5,
    opacity: float = 0.6,
) -> list[tuple[str, dict[str, str]]]:
    """Return ``(mlt_service, property_dict)`` tuples for the light-wash stack.

    Parameters
    ----------
    color:
        Wash colour: a name from :data:`COLOR_HUES` or a normalized hue float.
    intensity:
        ``[0.0, 1.0]`` — scales the colorize saturation, the brightness lift,
        and the contrast boost. ``0`` is a near-neutral grade; ``1`` is a bold
        saturated glow.
    opacity:
        ``[0.0, 1.0]`` — the ``frei0r.transparency`` amount (1.0 = wash fully
        applied, lower values let the underlying image bleed through so the
        wash reads as a translucent light spill).

    Returns a list (not a dict) so insertion order matches
    :data:`COLOR_WASH_SERVICES`.
    """
    hue = resolve_hue(color)
    i = _check_unit("intensity", intensity)
    transp = _check_unit("opacity", opacity)

    saturation = 0.5 + i * 0.5          # 0.50 .. 1.00 (normalized)
    lightness = 0.5                     # neutral; keyframe later to pulse
    brightness = 0.5 + i * 0.12         # 0.50 (neutral) .. 0.62 glow lift
    contrast = 0.5 + i * 0.08           # 0.50 (neutral) .. 0.58

    return [
        (
            "frei0r.colorize",
            {
                "hue": f"{hue:.4f}",
                "saturation": f"{saturation:.4f}",
                "lightness": f"{lightness:.4f}",
            },
        ),
        ("frei0r.transparency", {"0": f"{transp:.4f}"}),
        ("frei0r.brightness", {"Brightness": f"{brightness:.4f}"}),
        ("frei0r.contrast0r", {"Contrast": f"{contrast:.4f}"}),
    ]
