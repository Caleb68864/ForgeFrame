"""Unit tests for the color_grade chain builder (effect_color_grade bundle)."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.color_grade import (
    build_color_grade_chain,
)


def _services(chain):
    return [svc for svc, _ in chain]


# --- neutral / empty --------------------------------------------------------

def test_all_neutral_raises():
    with pytest.raises(ValueError, match="no color grade parameters"):
        build_color_grade_chain()


# --- individual stages emit only when non-neutral ---------------------------

def test_temperature_only():
    chain = build_color_grade_chain(temperature=4500)
    assert _services(chain) == ["avfilter.colortemperature"]
    assert chain[0][1]["av.temperature"] == "4500.0000"
    assert chain[0][1]["av.mix"] == "1.0"


def test_exposure_and_black():
    chain = build_color_grade_chain(exposure=0.5, black_level=-0.1)
    assert _services(chain) == ["avfilter.exposure"]
    assert chain[0][1]["av.exposure"] == "0.5000"
    assert chain[0][1]["av.black"] == "-0.1000"


def test_eq_emitted_for_contrast():
    chain = build_color_grade_chain(contrast=1.2)
    assert _services(chain) == ["avfilter.eq"]
    p = chain[0][1]
    assert p["av.contrast"] == "1.2000"
    assert p["av.brightness"] == "0.0000"
    assert p["av.saturation"] == "1.0000"


def test_eq_emitted_for_saturation():
    chain = build_color_grade_chain(saturation=1.3)
    assert _services(chain) == ["avfilter.eq"]


def test_lift_gamma_gain():
    chain = build_color_grade_chain(lift=10, gamma=-5, gain=3)
    assert _services(chain) == ["lumaliftgaingamma"]
    p = chain[0][1]
    assert p["lift"] == "10.0000"
    assert p["gamma"] == "-5.0000"
    assert p["gain"] == "3.0000"


def test_tint_off_at_zero():
    # tint params set but amount 0 -> no tint stage; needs another stage present
    chain = build_color_grade_chain(contrast=1.1, tint_amount=0.0)
    assert "frei0r.tint0r" not in _services(chain)


def test_tint_emitted():
    chain = build_color_grade_chain(
        tint_amount=0.3, tint_shadows="0x102030ff", tint_highlights="0x00ff00ff"
    )
    assert _services(chain) == ["frei0r.tint0r"]
    p = chain[0][1]
    assert p["Map black to"] == "0x102030ff"
    assert p["Map white to"] == "0x00ff00ff"
    assert p["Tint amount"] == "0.3000"


def test_lut_emitted():
    chain = build_color_grade_chain(lut_path="/abs/look.cube")
    assert _services(chain) == ["avfilter.lut3d"]
    assert chain[0][1]["av.file"] == "/abs/look.cube"


# --- ordering ---------------------------------------------------------------

def test_full_chain_order():
    chain = build_color_grade_chain(
        temperature=5000,
        exposure=0.3,
        contrast=1.1,
        lift=5,
        tint_amount=0.2,
        lut_path="/abs/look.cube",
    )
    assert _services(chain) == [
        "avfilter.colortemperature",
        "avfilter.exposure",
        "avfilter.eq",
        "lumaliftgaingamma",
        "frei0r.tint0r",
        "avfilter.lut3d",
    ]


# --- validation -------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        {"temperature": 500},      # below 1000
        {"temperature": 50000},    # above 40000
        {"exposure": 5},           # above 3
        {"black_level": -2},       # below -1
        {"contrast": 9},           # above 3
        {"brightness": 2},         # above 1
        {"saturation": 9},         # above 5
        {"lift": 900},             # above 500
        {"gain": -900},            # below -500
        {"tint_amount": 2000},     # above 1000
    ],
)
def test_out_of_range_raises(kwargs):
    with pytest.raises(ValueError):
        build_color_grade_chain(**kwargs)


def test_non_numeric_raises():
    with pytest.raises(ValueError, match="numeric"):
        build_color_grade_chain(contrast="a lot")  # type: ignore[arg-type]


def test_bool_rejected():
    with pytest.raises(ValueError, match="numeric"):
        build_color_grade_chain(saturation=True)  # type: ignore[arg-type]


def test_tint_empty_color_rejected():
    with pytest.raises(ValueError, match="tint_shadows"):
        build_color_grade_chain(tint_amount=0.3, tint_shadows="")
