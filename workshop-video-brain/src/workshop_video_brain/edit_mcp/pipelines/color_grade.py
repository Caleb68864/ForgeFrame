"""Correction + grade chain builder for the ``effect_color_grade`` bundle tool.

Models the workflow from the Nuxttux "Color Correction & Grading" Kdenlive
tutorial (video ``JTWRb8IEUl0``) as a single ordered filter chain built entirely
from MLT/avfilter services that already ship in the effect catalog.

The tutorial itself demonstrates three downloadable *custom effect stacks*
(``LM basic CC``, ``LM creative cg``, ``LM secondary hsl``). Those templates are
not primitives we can honestly reproduce one-for-one, so this module distils the
underlying, catalog-backed Kdenlive effects the presenter names into a compact,
parameterised chain:

Correction (``LM basic CC`` equivalent)
    1. white balance / temperature  -> ``avfilter.colortemperature``
    2. exposure / dark point         -> ``avfilter.exposure``
    3. video equalizer (contrast /   -> ``avfilter.eq``
       brightness / saturation)

Grade (``LM creative cg`` equivalent)
    4. lift / gamma / gain wheels    -> ``lumaliftgaingamma``
    5. creative tint (optional)      -> ``frei0r.tint0r``
    6. creative LUT (optional)       -> ``avfilter.lut3d``

This module is pure logic: no XML I/O, no MCP decorators, no filesystem access.
Every stage is optional -- a stage is only emitted when its parameters differ
from the neutral (identity) defaults, so a chain never contains no-op filters.

Substitutions / omissions (documented for honesty)
--------------------------------------------------
* The tutorial's ``color balance`` (shadows/mids/highlights RGB) and ``curves``
  steps are NOT emitted: ``avfilter.colorbalance`` needs nine RGB scalars and
  ``avfilter.curves`` needs spline point strings -- neither maps to a small,
  honest scalar surface. Creative colour is instead offered via lift/gamma/gain
  plus the optional tint, matching what the presenter actually reaches for.
* The presenter's ``LM secondary hsl`` (masked secondary colour selection) is a
  separate masking workflow, out of scope for a correction+grade bundle.
* ``lumaliftgaingamma`` (a.k.a. lift/gamma/gain) IS present in the catalog under
  that exact ``mlt_service`` id -- despite the SYNTHESIS note claiming it was
  missing -- so no substitution is required for the tonal-wheel stage.
"""
from __future__ import annotations

from typing import Any

# Neutral (identity) reference values -- a stage whose params all equal these is
# skipped so the emitted chain never carries a no-op filter.
NEUTRAL_TEMPERATURE = 6500.0
NEUTRAL_EXPOSURE = 0.0
NEUTRAL_BLACK = 0.0
NEUTRAL_CONTRAST = 1.0
NEUTRAL_BRIGHTNESS = 0.0
NEUTRAL_SATURATION = 1.0
NEUTRAL_LGG = 0.0  # lift / gamma / gain wheels are all 0 at neutral

# Canonical correction->grade order. Mirrors the presenter's top-to-bottom stack.
COLOR_GRADE_ORDER: tuple[str, ...] = (
    "avfilter.colortemperature",
    "avfilter.exposure",
    "avfilter.eq",
    "lumaliftgaingamma",
    "frei0r.tint0r",
    "avfilter.lut3d",
)


def _fmt(value: float) -> str:
    """Format a numeric MLT property value compactly (no trailing zeros noise)."""
    return f"{float(value):.4f}"


def _num(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric; got {value!r}")
    return float(value)


def _check_range(name: str, value: float, lo: float, hi: float) -> None:
    if value < lo or value > hi:
        raise ValueError(f"{name} must be in [{lo}, {hi}]; got {value}")


def build_color_grade_chain(
    *,
    temperature: float = NEUTRAL_TEMPERATURE,
    exposure: float = NEUTRAL_EXPOSURE,
    black_level: float = NEUTRAL_BLACK,
    contrast: float = NEUTRAL_CONTRAST,
    brightness: float = NEUTRAL_BRIGHTNESS,
    saturation: float = NEUTRAL_SATURATION,
    lift: float = NEUTRAL_LGG,
    gamma: float = NEUTRAL_LGG,
    gain: float = NEUTRAL_LGG,
    tint_amount: float = 0.0,
    tint_shadows: str = "0x000000ff",
    tint_highlights: str = "0x00ff00ff",
    lut_path: str = "",
) -> list[tuple[str, dict[str, str]]]:
    """Return an ordered ``[(mlt_service, property_dict), ...]`` grade chain.

    Every stage is optional. A stage is emitted only when at least one of its
    parameters departs from the neutral/identity value, so the returned list
    contains no no-op filters. Parameters are validated against the catalog
    ranges for their target service.

    Raises
    ------
    ValueError
        On a non-numeric or out-of-range parameter, or when every stage is
        neutral (nothing to apply).
    """
    temperature = _num("temperature", temperature)
    exposure = _num("exposure", exposure)
    black_level = _num("black_level", black_level)
    contrast = _num("contrast", contrast)
    brightness = _num("brightness", brightness)
    saturation = _num("saturation", saturation)
    lift = _num("lift", lift)
    gamma = _num("gamma", gamma)
    gain = _num("gain", gain)
    tint_amount = _num("tint_amount", tint_amount)

    _check_range("temperature", temperature, 1000.0, 40000.0)
    _check_range("exposure", exposure, -3.0, 3.0)
    _check_range("black_level", black_level, -1.0, 1.0)
    _check_range("contrast", contrast, -3.0, 3.0)
    _check_range("brightness", brightness, -1.0, 1.0)
    _check_range("saturation", saturation, 0.0, 5.0)
    _check_range("lift", lift, -500.0, 500.0)
    _check_range("gamma", gamma, -1000.0, 1000.0)
    _check_range("gain", gain, -500.0, 500.0)
    _check_range("tint_amount", tint_amount, 0.0, 1000.0)

    chain: list[tuple[str, dict[str, str]]] = []

    # 1. White balance / temperature (correction)
    if temperature != NEUTRAL_TEMPERATURE:
        chain.append((
            "avfilter.colortemperature",
            {"av.temperature": _fmt(temperature), "av.mix": "1.0"},
        ))

    # 2. Exposure / dark point (correction)
    if exposure != NEUTRAL_EXPOSURE or black_level != NEUTRAL_BLACK:
        chain.append((
            "avfilter.exposure",
            {"av.exposure": _fmt(exposure), "av.black": _fmt(black_level)},
        ))

    # 3. Video equalizer: contrast / brightness / saturation (correction)
    if (
        contrast != NEUTRAL_CONTRAST
        or brightness != NEUTRAL_BRIGHTNESS
        or saturation != NEUTRAL_SATURATION
    ):
        chain.append((
            "avfilter.eq",
            {
                "av.contrast": _fmt(contrast),
                "av.brightness": _fmt(brightness),
                "av.saturation": _fmt(saturation),
            },
        ))

    # 4. Lift / gamma / gain tonal wheels (grade)
    if lift != NEUTRAL_LGG or gamma != NEUTRAL_LGG or gain != NEUTRAL_LGG:
        chain.append((
            "lumaliftgaingamma",
            {"lift": _fmt(lift), "gamma": _fmt(gamma), "gain": _fmt(gain)},
        ))

    # 5. Creative tint (grade, optional -- off at amount 0)
    if tint_amount > 0.0:
        if not isinstance(tint_shadows, str) or not tint_shadows:
            raise ValueError("tint_shadows must be a non-empty color string")
        if not isinstance(tint_highlights, str) or not tint_highlights:
            raise ValueError("tint_highlights must be a non-empty color string")
        chain.append((
            "frei0r.tint0r",
            {
                "Map black to": tint_shadows,
                "Map white to": tint_highlights,
                "Tint amount": _fmt(tint_amount),
            },
        ))

    # 6. Creative LUT (grade, optional)
    if lut_path:
        if not isinstance(lut_path, str):
            raise ValueError("lut_path must be a string path")
        chain.append(("avfilter.lut3d", {"av.file": lut_path}))

    if not chain:
        raise ValueError(
            "no color grade parameters set -- adjust at least one of "
            "temperature/exposure/black_level/contrast/brightness/saturation/"
            "lift/gamma/gain/tint_amount/lut_path"
        )

    return chain
