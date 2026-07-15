"""Pure-logic helpers for the ``effect_scifi_greenscreen`` bundle tool.

This module composes the three-effect green-screen keying recipe taught in the
Photolearningism Kdenlive VFX tutorial *"Sci-Fi Effects | Mastering Chroma
Keying in KDEnlive"* (video ``uqge5McjO7E``). The tutorial keys a hand shot
against a green screen with a deliberately ordered stack of three stock
Kdenlive effects:

1. **Key Spill Mop Up** (``frei0r.keyspillm0pup``) -- placed *first* so it
   corrects the green light that bounces onto the subject **before** the key
   removes the background. ``[05:24]`` / ``[07:42]`` ("I am putting the correct
   effect first to translate key from my hand then it passes into the next
   effect which is actually that key effect").
2. **Chroma Key: Advanced** (``avfilter.hsvkey``) -- the actual key that removes
   the green backdrop. ``[02:20]``. Built by reusing
   :func:`masking.build_chroma_key_advanced_xml` (the same pipeline function the
   ``effect_chroma_key_advanced`` tool uses).
3. **Despill** (``avfilter.despill``) -- placed *last* to restore the brightness
   and detail stripped off the subject during keying. ``[08:28]`` ("the last
   thing that I did ... is this d-spill effect ... bring back those details of
   my hand that make it look real").

It is pure logic only: no XML I/O, no MCP decorators, no filesystem. The MCP
tool ``effect_scifi_greenscreen`` (in ``server/tools.py``) consumes
:func:`keyspill_mopup_params`, :func:`despill_params`, and
:func:`scifi_greenscreen_services`, and writes the filters via the shared
``_build_filter_xml`` / ``masking.build_chroma_key_advanced_xml`` /
``patcher.insert_effect_xml`` machinery, exactly like ``effect_hologram``
consumes ``hologram_stack_params``.

Deliberately **not** modelled (honest to the transcript + current primitives;
see docs/research/2026-07-03-tutorial-effect-analysis/scifi-chroma-key.md):

* Background-plate replacement / compositing -- the tutorial reveals the track
  below purely by keying out the green ("I'm going to take away the background
  here because that's just there so you can see it working"); it never places or
  grades a replacement plate. Layer a plate on a lower track + ``composite_set``
  separately if desired.
* Plate grading, glow, and atmosphere -- not present in *this* video.
* Animated / keyframed keying -- the tutorial notes the key *can* be keyframed
  but demonstrates a single static key ("for now I'm just doing the one key").
* The Position-and-Zoom crop -- clip-specific framing, not part of the recipe.
"""
from __future__ import annotations

from .masking import color_to_mlt_hex

# Tutorial defaults.
SCIFI_KEY_COLOR_DEFAULT = "#00FF00"
# Catalog default Target Color for Key Spill Mop Up (a warm skin hue) -- the
# tutorial "borrowed a hue from my hand to correct" the spill.
SCIFI_SPILL_TARGET_DEFAULT = "#C87F65"

# Service identifiers, in tutorial stack order.
KEYSPILL_SERVICE = "frei0r.keyspillm0pup"
KEYSPILL_KID = "frei0r_keyspillm0pup"
KEY_SERVICE = "avfilter.hsvkey"
KEY_KID = "avfilter_hsvkey"
DESPILL_SERVICE = "avfilter.despill"
DESPILL_KID = "avfilter_despill"


def _require_number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric; got {value!r}")
    return float(value)


def _require_non_negative(value: float, name: str) -> float:
    v = _require_number(value, name)
    if v < 0.0:
        raise ValueError(f"{name} must be >= 0; got {v}")
    return v


def screen_type_from_color(color: str) -> str:
    """Return ``"green"`` or ``"blue"`` for a chroma key color.

    Both ``frei0r.keyspillm0pup`` and ``avfilter.despill`` operate on a
    green- or blue-screen. The screen type is inferred from the dominant
    channel of ``color``; the tutorial screens against green.
    """
    mlt_hex = color_to_mlt_hex(color)  # validates + normalizes to 0xRRGGBBAA
    r = int(mlt_hex[2:4], 16)
    g = int(mlt_hex[4:6], 16)
    b = int(mlt_hex[6:8], 16)
    if b > g and b > r:
        return "blue"
    return "green"


def keyspill_mopup_params(
    key_color: str = SCIFI_KEY_COLOR_DEFAULT,
    target_color: str = SCIFI_SPILL_TARGET_DEFAULT,
    tolerance: float = 0.24,
    slope: float = 0.4,
    two_pass: bool = True,
) -> dict[str, str]:
    """Return ``frei0r.keyspillm0pup`` tuneable properties.

    Defaults follow the catalog / tutorial: **Color distance** mask type (the
    tutorial's "color distance again is the best mask type"), De-Key operations,
    and an optional second De-Key pass ("you can do two passes at this which I
    found to be really useful").
    """
    tol = _require_non_negative(tolerance, "spill_tolerance")
    slp = _require_non_negative(slope, "spill_slope")
    props: dict[str, str] = {
        "Key color": color_to_mlt_hex(key_color),
        "Target color": color_to_mlt_hex(target_color),
        "Mask type": "0",  # 0 = Color distance
        "Tolerance": f"{tol:.4f}",
        "Slope": f"{slp:.4f}",
        "Operation 1": "1",  # 1 = De-Key
        "Amount 1": "0.5000",
    }
    if two_pass:
        props["Operation 2"] = "1"  # second De-Key pass
        props["Amount 2"] = "0.5000"
    else:
        props["Operation 2"] = "0"  # None
        props["Amount 2"] = "0.0000"
    return props


def despill_params(
    key_color: str = SCIFI_KEY_COLOR_DEFAULT,
    amount: float = 0.05,
    expand: float = 0.0,
    brightness: float = 0.0,
) -> dict[str, str]:
    """Return ``avfilter.despill`` tuneable properties.

    ``amount`` -> ``av.mix`` (Spillmap Mix, 0..1), ``expand`` -> ``av.expand``
    (0..1), ``brightness`` -> ``av.brightness`` (-10..10, restores luma the key
    stripped off). Screen type is inferred from ``key_color``.
    """
    mix = _require_non_negative(amount, "despill_amount")
    if mix > 1.0:
        raise ValueError(f"despill_amount must be in [0.0, 1.0]; got {mix}")
    exp = _require_non_negative(expand, "despill_expand")
    if exp > 1.0:
        raise ValueError(f"despill_expand must be in [0.0, 1.0]; got {exp}")
    bright = _require_number(brightness, "despill_brightness")
    if bright < -10.0 or bright > 10.0:
        raise ValueError(f"despill_brightness must be in [-10.0, 10.0]; got {bright}")
    return {
        "av.type": screen_type_from_color(key_color),
        "av.mix": f"{mix:.4f}",
        "av.expand": f"{exp:.4f}",
        "av.brightness": f"{bright:.4f}",
    }


def scifi_greenscreen_services(
    spill_correction: bool = True,
    despill: bool = True,
) -> list[str]:
    """Return the ordered MLT service list for the keying recipe.

    The advanced chroma key (``avfilter.hsvkey``) is always present; the
    Key-Spill-Mop-Up pre-correction and the Despill restore are toggleable. The
    order is fixed and load-bearing: spill correction -> key -> despill.
    """
    services: list[str] = []
    if spill_correction:
        services.append(KEYSPILL_SERVICE)
    services.append(KEY_SERVICE)
    if despill:
        services.append(DESPILL_SERVICE)
    return services
