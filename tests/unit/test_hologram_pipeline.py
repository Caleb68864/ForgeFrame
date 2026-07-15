"""Unit tests for the hologram pipeline pure functions.

Covers ``workshop_video_brain.edit_mcp.pipelines.hologram`` -- the pure logic
behind the ``effect_hologram`` bundle tool.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.hologram import (
    HOLOGRAM_TINT_DEFAULT,
    hex_to_hsl,
    hologram_stack_params,
)


# ---------------------------------------------------------------------------
# hex_to_hsl
# ---------------------------------------------------------------------------


def test_hex_to_hsl_cyan_default():
    hue, sat, light = hex_to_hsl(HOLOGRAM_TINT_DEFAULT)
    # #33ccff is a cyan/blue -- hue in the ~190-200 range, high saturation.
    assert 180.0 <= hue <= 210.0
    assert sat > 0.8
    assert 0.0 <= light <= 1.0


@pytest.mark.parametrize("value", ["#fff", "0x33ccff", "33ccff", "#33CCFF"])
def test_hex_to_hsl_accepts_forms(value):
    hue, sat, light = hex_to_hsl(value)
    assert 0.0 <= hue <= 360.0


@pytest.mark.parametrize("bad", ["", "#12", "nothex", "#gggggg", 123])
def test_hex_to_hsl_rejects_bad(bad):
    with pytest.raises(ValueError):
        hex_to_hsl(bad)


# ---------------------------------------------------------------------------
# hologram_stack_params: structure & ordering
# ---------------------------------------------------------------------------


def test_default_stack_full_order():
    stack = hologram_stack_params()
    services = [s for s, _ in stack]
    assert services == [
        "frei0r.colorize",
        "frei0r.scanline0r",
        "boxblur",
        "frei0r.glow",
        "frei0r.glitch0r",
        "frei0r.transparency",
    ]


def test_colorize_hue_derived_from_tint():
    stack = hologram_stack_params(tint_color="#ff0000")  # red -> hue ~0
    colorize = dict(stack)["frei0r.colorize"]
    assert abs(float(colorize["hue"])) < 1.0


def test_transparency_always_present_and_inverted():
    # transparency=0.25 means 25% removed -> filter value 0.75 (opaque-ish).
    stack = dict(hologram_stack_params(transparency=0.25))
    assert stack["frei0r.transparency"]["0"] == "0.7500"
    # transparency=0 -> fully opaque (1.0000)
    stack0 = dict(hologram_stack_params(transparency=0.0))
    assert stack0["frei0r.transparency"]["0"] == "1.0000"


# ---------------------------------------------------------------------------
# Conditional inclusion
# ---------------------------------------------------------------------------


def test_scanline_zero_omits_scanline_and_boxblur():
    services = [s for s, _ in hologram_stack_params(scanline_intensity=0.0)]
    assert "frei0r.scanline0r" not in services
    assert "boxblur" not in services


def test_glow_zero_omits_glow():
    services = [s for s, _ in hologram_stack_params(glow=0.0)]
    assert "frei0r.glow" not in services


def test_flicker_zero_omits_glitch():
    services = [s for s, _ in hologram_stack_params(flicker=0.0)]
    assert "frei0r.glitch0r" not in services


def test_all_off_leaves_colorize_and_transparency():
    services = [
        s for s, _ in hologram_stack_params(
            scanline_intensity=0.0, glow=0.0, flicker=0.0
        )
    ]
    assert services == ["frei0r.colorize", "frei0r.transparency"]


# ---------------------------------------------------------------------------
# Parameter scaling
# ---------------------------------------------------------------------------


def test_scanline_intensity_scales_boxblur():
    low = dict(hologram_stack_params(scanline_intensity=0.1))["boxblur"]
    high = dict(hologram_stack_params(scanline_intensity=1.0))["boxblur"]
    assert float(high["hori"]) > float(low["hori"])
    # box blur is one-axis: vertical multiplicator stays neutral.
    assert high["vert"] == "1"


def test_glow_scales_blur():
    low = dict(hologram_stack_params(glow=0.1))["frei0r.glow"]
    high = dict(hologram_stack_params(glow=0.9))["frei0r.glow"]
    assert float(high["Blur"]) > float(low["Blur"])


# ---------------------------------------------------------------------------
# Flicker: static vs animated window
# ---------------------------------------------------------------------------


def test_flicker_static_when_no_window():
    glitch = dict(hologram_stack_params(flicker=0.5, end_frame=-1))["frei0r.glitch0r"]
    # No keyframe separators -> static scalar.
    assert ";" not in glitch["0"]
    assert "=" not in glitch["0"]


def test_flicker_animated_over_window():
    glitch = dict(
        hologram_stack_params(flicker=0.5, start_frame=0, end_frame=100, fps=25.0)
    )["frei0r.glitch0r"]
    # Animated MLT keyframe string -> contains timestamp segments.
    assert ";" in glitch["0"]
    assert "=" in glitch["0"]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"scanline_intensity": 1.5},
        {"scanline_intensity": -0.1},
        {"glow": 2.0},
        {"transparency": -1.0},
        {"flicker": 1.1},
        {"start_frame": -5},
    ],
)
def test_out_of_range_raises(kwargs):
    with pytest.raises(ValueError):
        hologram_stack_params(**kwargs)


def test_bool_intensity_rejected():
    with pytest.raises(ValueError):
        hologram_stack_params(glow=True)
