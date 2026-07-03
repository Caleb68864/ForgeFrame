"""Pure-logic helpers for the ``effect_hologram`` bundle tool.

This module composes the "realistic hologram" look from the Photolearningism
Kdenlive VFX tutorial (video ``P0eI7YLN3FU``) as an ordered stack of MLT
``<filter>`` services with tutorial-derived default parameters.

It is pure logic only: no XML I/O, no MCP decorators, no filesystem. The MCP
tool ``effect_hologram`` (in ``server/tools.py``) consumes
``hologram_stack_params`` and writes the filters via the shared
``_build_filter_xml`` / ``patcher.insert_effect_xml`` machinery, exactly like
``effect_glitch_stack`` consumes ``glitch_stack_params``.

Tutorial → service mapping
--------------------------

The tutorial builds its hologram from a green-screen key + rotoscope, motion
tracking, and a "cake" embellishment stack (``[09:12]`` onward). The subject
isolation (roto / chroma / key-spill) and motion-tracker → transform steps are
**not** reproducible with current primitives (no ``opencv.tracker``, only a
frame-0 rotoscoping spline) and are documented as omissions in the tool
docstring. This module reproduces the achievable "look" layer:

* ``frei0r.colorize`` -- the tutorial's **Colorize** ("I like it blue").
* ``frei0r.scanline0r`` -- interlaced scan lines (classic hologram texture;
  scanline0r has no tuneable params, so it is included/omitted as a unit).
* ``boxblur`` -- the tutorial's one-axis **Box Blur** ("interrupted
  transmission effect"), driven horizontally by ``scanline_intensity``.
* ``frei0r.glow`` -- hologram bloom / **Glow**.
* ``frei0r.glitch0r`` -- hologram **flicker** (animated Glitch Frequency over
  the ``[start_frame, end_frame]`` window when a window is supplied).
* ``frei0r.transparency`` -- the tutorial's **Transparency** (translucency).
"""
from __future__ import annotations

import colorsys

from .keyframes import Keyframe, build_keyframe_string

# Tutorial default: hologram cyan / blue.
HOLOGRAM_TINT_DEFAULT = "#33ccff"

# Ordered canonical hologram stack. Filters are emitted in this order; some are
# conditionally omitted (see ``hologram_stack_params``).
HOLOGRAM_SERVICES: tuple[str, ...] = (
    "frei0r.colorize",     # tint
    "frei0r.scanline0r",   # scan lines
    "boxblur",             # directional "interrupted transmission" blur
    "frei0r.glow",         # bloom
    "frei0r.glitch0r",     # flicker
    "frei0r.transparency",  # translucency
)


def _clamp01(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric in [0.0, 1.0]; got {value!r}")
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{name} must be in [0.0, 1.0]; got {value}")
    return float(value)


def hex_to_hsl(hex_color: str) -> tuple[float, float, float]:
    """Return ``(hue_degrees, saturation_0_1, lightness_0_1)`` for a hex color.

    Accepts ``#RRGGBB`` / ``#RGB`` / ``0xRRGGBB`` (leading ``#`` or ``0x``
    optional). Raises ``ValueError`` on malformed input.
    """
    if not isinstance(hex_color, str):
        raise ValueError(f"tint_color must be a hex string; got {hex_color!r}")
    s = hex_color.strip()
    if s.startswith("#"):
        s = s[1:]
    elif s.lower().startswith("0x"):
        s = s[2:]
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        raise ValueError(f"tint_color must be a 3- or 6-digit hex color; got {hex_color!r}")
    try:
        r = int(s[0:2], 16) / 255.0
        g = int(s[2:4], 16) / 255.0
        b = int(s[4:6], 16) / 255.0
    except ValueError as exc:
        raise ValueError(f"tint_color not valid hex: {hex_color!r}") from exc
    h, ll, sat = colorsys.rgb_to_hls(r, g, b)
    return (h * 360.0, sat, ll)


def _flicker_keyframes(
    freq_peak: float,
    start_frame: int,
    end_frame: int,
    fps: float,
) -> str:
    """Build an MLT scalar keyframe string pulsing Glitch Frequency.

    Produces a five-point flicker (peak / 0 / peak / 0 / peak) across the
    ``[start_frame, end_frame]`` window. ``end_frame`` must be > ``start_frame``.
    """
    span = end_frame - start_frame
    quarter = max(1, span // 4)
    frames = [
        start_frame,
        start_frame + quarter,
        start_frame + 2 * quarter,
        start_frame + 3 * quarter,
        end_frame,
    ]
    values = [freq_peak, 0.0, freq_peak, 0.0, freq_peak]
    kfs = [
        Keyframe(frame=f, value=v, easing="linear")
        for f, v in zip(frames, values)
    ]
    return build_keyframe_string("scalar", kfs, fps)


def hologram_stack_params(
    tint_color: str = HOLOGRAM_TINT_DEFAULT,
    scanline_intensity: float = 0.5,
    glow: float = 0.35,
    transparency: float = 0.25,
    flicker: float = 0.3,
    start_frame: int = 0,
    end_frame: int = -1,
    fps: float = 25.0,
) -> list[tuple[str, dict[str, str]]]:
    """Return an ordered ``[(mlt_service, {prop: value}), ...]`` hologram stack.

    Parameters
    ----------
    tint_color:
        Hologram tint as a hex color (default cyan ``#33ccff``). Drives the
        ``frei0r.colorize`` hue/saturation.
    scanline_intensity, glow, transparency, flicker:
        Each in ``[0.0, 1.0]``. ``scanline_intensity`` gates the scan-line
        filter and scales the directional box blur; ``glow`` gates/scales the
        bloom; ``flicker`` gates/scales the glitch flicker. ``transparency`` is
        the fraction of visibility removed (0 = opaque, 1 = fully transparent);
        the ``frei0r.transparency`` filter is always emitted.
    start_frame, end_frame:
        Frame window for the animated flicker. If ``end_frame <= start_frame``
        (e.g. the ``-1`` sentinel), flicker is applied as a static value.
    fps:
        Project frame rate, used to encode the flicker keyframe timestamps.

    Property values are strings (static or MLT keyframe animation strings),
    ready to hand to ``_build_filter_xml``.
    """
    scanline_intensity = _clamp01(scanline_intensity, "scanline_intensity")
    glow = _clamp01(glow, "glow")
    transparency = _clamp01(transparency, "transparency")
    flicker = _clamp01(flicker, "flicker")
    if not isinstance(start_frame, int) or isinstance(start_frame, bool):
        raise ValueError(f"start_frame must be int; got {start_frame!r}")
    if not isinstance(end_frame, int) or isinstance(end_frame, bool):
        raise ValueError(f"end_frame must be int; got {end_frame!r}")
    if start_frame < 0:
        raise ValueError(f"start_frame must be >= 0; got {start_frame}")

    hue, sat, _light = hex_to_hsl(tint_color)

    stack: list[tuple[str, dict[str, str]]] = []

    # 1. Colorize -- the tutorial's "I like it blue" tint.
    stack.append((
        "frei0r.colorize",
        {
            "hue": f"{hue:.2f}",
            "saturation": f"{max(0.5, sat):.4f}",
            "lightness": "0.5",
        },
    ))

    # 2. Scan lines (no tuneable params -- included as a unit when enabled).
    if scanline_intensity > 0.0:
        stack.append(("frei0r.scanline0r", {}))

    # 3. Directional box blur -- the "interrupted transmission" one-axis blur.
    #    Horizontal multiplicator + blur factor scale with scanline_intensity.
    if scanline_intensity > 0.0:
        hori = 1.0 + scanline_intensity * 8.0
        blur = 2.0 + scanline_intensity * 6.0
        stack.append((
            "boxblur",
            {"hori": f"{hori:.4f}", "vert": "1", "blur": f"{blur:.4f}"},
        ))

    # 4. Glow / bloom.
    if glow > 0.0:
        stack.append((
            "frei0r.glow",
            {"Blur": f"{glow * 200.0:.4f}"},
        ))

    # 5. Flicker -- animated Glitch Frequency across the window when supplied.
    if flicker > 0.0:
        freq_peak = flicker * 30.0
        if end_frame > start_frame:
            freq_value = _flicker_keyframes(freq_peak, start_frame, end_frame, fps)
        else:
            freq_value = f"{freq_peak:.4f}"
        stack.append((
            "frei0r.glitch0r",
            {
                "0": freq_value,
                "2": f"{flicker * 0.5:.4f}",
                "3": f"{flicker * 1.5:.4f}",
            },
        ))

    # 6. Transparency -- the tutorial's translucency. frei0r.transparency '0'
    #    is 1.0 = opaque, 0.0 = fully transparent.
    stack.append((
        "frei0r.transparency",
        {"0": f"{1.0 - transparency:.4f}"},
    ))

    return stack
