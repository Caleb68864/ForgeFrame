"""Unit tests for the ``color_wash`` pipeline (pure logic).

Covers ``resolve_hue`` and ``color_wash_params`` used by the
``effect_color_wash`` bundle MCP tool.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.color_wash import (
    COLOR_HUES,
    COLOR_WASH_SERVICES,
    color_wash_params,
    resolve_hue,
)


# ---------------------------------------------------------------------------
# resolve_hue
# ---------------------------------------------------------------------------


def test_resolve_hue_named_colors():
    assert resolve_hue("blue") == COLOR_HUES["blue"]
    assert resolve_hue("RED") == 0.0
    assert resolve_hue("  Green ") == COLOR_HUES["green"]


def test_resolve_hue_float_and_numeric_string():
    assert resolve_hue(0.25) == 0.25
    assert resolve_hue("0.75") == 0.75
    assert resolve_hue(0) == 0.0
    assert resolve_hue(1) == 1.0


def test_resolve_hue_rejects_out_of_range():
    with pytest.raises(ValueError):
        resolve_hue(1.5)
    with pytest.raises(ValueError):
        resolve_hue(-0.1)
    with pytest.raises(ValueError):
        resolve_hue("2.0")


def test_resolve_hue_rejects_unknown_name_and_bool():
    with pytest.raises(ValueError):
        resolve_hue("chartreuse")
    with pytest.raises(ValueError):
        resolve_hue(True)


# ---------------------------------------------------------------------------
# color_wash_params
# ---------------------------------------------------------------------------


def test_params_service_order_matches_constant():
    stack = color_wash_params()
    services = [svc for svc, _ in stack]
    assert tuple(services) == COLOR_WASH_SERVICES
    assert len(stack) == 4


def test_params_defaults_are_blue_and_neutralish():
    stack = dict(color_wash_params())
    colorize = stack["frei0r.colorize"]
    assert colorize["hue"] == f"{COLOR_HUES['blue']:.4f}"
    # intensity 0.5 -> saturation 0.75, brightness 0.56, contrast 0.54
    assert colorize["saturation"] == "0.7500"
    assert colorize["lightness"] == "0.5000"
    assert stack["frei0r.transparency"]["0"] == "0.6000"
    assert stack["frei0r.brightness"]["Brightness"] == "0.5600"
    assert stack["frei0r.contrast0r"]["Contrast"] == "0.5400"


def test_params_intensity_scaling_monotonic():
    low = dict(color_wash_params(intensity=0.0))
    high = dict(color_wash_params(intensity=1.0))
    assert low["frei0r.colorize"]["saturation"] == "0.5000"
    assert high["frei0r.colorize"]["saturation"] == "1.0000"
    assert float(high["frei0r.brightness"]["Brightness"]) > float(
        low["frei0r.brightness"]["Brightness"]
    )
    assert float(high["frei0r.contrast0r"]["Contrast"]) > float(
        low["frei0r.contrast0r"]["Contrast"]
    )


def test_params_opacity_flows_to_transparency():
    stack = dict(color_wash_params(opacity=0.3))
    assert stack["frei0r.transparency"]["0"] == "0.3000"


def test_params_custom_hue_float():
    stack = dict(color_wash_params(color=0.9))
    assert stack["frei0r.colorize"]["hue"] == "0.9000"


def test_params_validate_ranges():
    with pytest.raises(ValueError):
        color_wash_params(intensity=1.5)
    with pytest.raises(ValueError):
        color_wash_params(opacity=-0.2)
    with pytest.raises(ValueError):
        color_wash_params(intensity=True)
