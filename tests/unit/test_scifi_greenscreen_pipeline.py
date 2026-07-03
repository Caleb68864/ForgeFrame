"""Unit tests for the sci-fi green-screen pipeline pure functions.

Covers ``workshop_video_brain.edit_mcp.pipelines.scifi_greenscreen`` -- the pure
logic behind the ``effect_scifi_greenscreen`` bundle tool (the Photolearningism
*"Sci-Fi Effects | Mastering Chroma Keying in KDEnlive"* recipe, video
``uqge5McjO7E``).
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.scifi_greenscreen import (
    DESPILL_SERVICE,
    KEY_SERVICE,
    KEYSPILL_SERVICE,
    SCIFI_KEY_COLOR_DEFAULT,
    despill_params,
    keyspill_mopup_params,
    scifi_greenscreen_services,
    screen_type_from_color,
)


# ---------------------------------------------------------------------------
# screen_type_from_color
# ---------------------------------------------------------------------------


def test_screen_type_green_default():
    assert screen_type_from_color(SCIFI_KEY_COLOR_DEFAULT) == "green"


@pytest.mark.parametrize(
    "color,expected",
    [
        ("#00FF00", "green"),
        ("#0000FF", "blue"),
        ("#10D010", "green"),
        ("#1010D0", "blue"),
        ("#00FF00FF", "green"),
    ],
)
def test_screen_type_detection(color, expected):
    assert screen_type_from_color(color) == expected


def test_screen_type_rejects_bad_color():
    with pytest.raises(ValueError):
        screen_type_from_color("not-a-color")


# ---------------------------------------------------------------------------
# scifi_greenscreen_services -- ordering & toggles
# ---------------------------------------------------------------------------


def test_default_services_full_order():
    services = scifi_greenscreen_services()
    assert services == [KEYSPILL_SERVICE, KEY_SERVICE, DESPILL_SERVICE]


def test_key_always_in_the_middle_or_present():
    # Spill correction is always the pre-filter; despill is always last.
    assert scifi_greenscreen_services()[1] == KEY_SERVICE


def test_no_spill_correction_omits_keyspill():
    services = scifi_greenscreen_services(spill_correction=False)
    assert services == [KEY_SERVICE, DESPILL_SERVICE]
    assert KEYSPILL_SERVICE not in services


def test_no_despill_omits_despill():
    services = scifi_greenscreen_services(despill=False)
    assert services == [KEYSPILL_SERVICE, KEY_SERVICE]
    assert DESPILL_SERVICE not in services


def test_key_only():
    assert scifi_greenscreen_services(
        spill_correction=False, despill=False
    ) == [KEY_SERVICE]


# ---------------------------------------------------------------------------
# keyspill_mopup_params
# ---------------------------------------------------------------------------


def test_keyspill_defaults_color_distance_and_two_pass():
    props = keyspill_mopup_params()
    # Mask type 0 = Color distance (the tutorial's chosen mask type).
    assert props["Mask type"] == "0"
    # Key + target colors are frei0r 0xRRGGBBAA hex.
    assert props["Key color"].startswith("0x") and len(props["Key color"]) == 10
    assert props["Target color"].startswith("0x")
    # Two-pass => both operations are De-Key (1).
    assert props["Operation 1"] == "1"
    assert props["Operation 2"] == "1"


def test_keyspill_single_pass_disables_second_op():
    props = keyspill_mopup_params(two_pass=False)
    assert props["Operation 2"] == "0"
    assert props["Amount 2"] == "0.0000"


def test_keyspill_key_color_matches_input():
    props = keyspill_mopup_params(key_color="#00FF00")
    assert props["Key color"] == "0x00ff00ff"


@pytest.mark.parametrize("kwargs", [{"tolerance": -0.1}, {"slope": -1.0}])
def test_keyspill_rejects_negative(kwargs):
    with pytest.raises(ValueError):
        keyspill_mopup_params(**kwargs)


def test_keyspill_rejects_bad_color():
    with pytest.raises(ValueError):
        keyspill_mopup_params(key_color="#zzz")


# ---------------------------------------------------------------------------
# despill_params
# ---------------------------------------------------------------------------


def test_despill_defaults():
    props = despill_params()
    assert props["av.type"] == "green"
    assert props["av.mix"] == "0.0500"
    assert props["av.brightness"] == "0.0000"


def test_despill_blue_screen_type_from_color():
    props = despill_params(key_color="#0000FF")
    assert props["av.type"] == "blue"


def test_despill_brightness_restore():
    props = despill_params(brightness=2.5)
    assert props["av.brightness"] == "2.5000"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"amount": -0.1},
        {"amount": 1.5},
        {"expand": 2.0},
        {"brightness": 50.0},
        {"brightness": -50.0},
    ],
)
def test_despill_out_of_range_raises(kwargs):
    with pytest.raises(ValueError):
        despill_params(**kwargs)


def test_despill_bool_amount_rejected():
    with pytest.raises(ValueError):
        despill_params(amount=True)
