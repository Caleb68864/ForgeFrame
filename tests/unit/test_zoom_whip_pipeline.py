"""Unit tests for the zoom / whip-pan transition planner (pure logic)."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines import zoom_whip as zw
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string


def _plan(**overrides):
    kwargs = dict(
        fps=30.0,
        width=1920,
        height=1080,
        out_clip_frames=60,
        in_clip_frames=60,
        direction="left",
        duration_frames=12,
        zoom_amount=1.4,
        blur=6.0,
        easing="cubic",
    )
    kwargs.update(overrides)
    return zw.build_zoom_whip_plan(**kwargs)


# --------------------------------------------------------------------------
# Keyframe string generation across fps values
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "fps, dur, expected_out_start_ts, expected_in_end_ts",
    [
        (30.0, 12, "00:00:01.600", "00:00:00.400"),   # out_start=48f, in_end=12f
        (60.0, 12, "00:00:00.800", "00:00:00.200"),   # 48f@60=0.8s, 12f@60=0.2s
        (24.0, 6, "00:00:02.250", "00:00:00.250"),    # out_start=54f@24, in_end=6f@24
    ],
)
def test_keyframe_timestamps_scale_with_fps(fps, dur, expected_out_start_ts, expected_in_end_ts):
    plan = _plan(fps=fps, duration_frames=dur)
    assert plan["out"]["transform_rect"].startswith(expected_out_start_ts)
    assert expected_in_end_ts in plan["in"]["transform_rect"]


def test_out_ramp_uses_full_clip_tail():
    # 60-frame clip, 12-frame transition -> punch starts at frame 48, ends at 59.
    plan = _plan(out_clip_frames=60, duration_frames=12)
    assert plan["out"]["start_frame"] == 48
    assert plan["out"]["end_frame"] == 59


def test_in_ramp_starts_at_clip_head():
    plan = _plan(in_clip_frames=60, duration_frames=12)
    assert plan["in"]["start_frame"] == 0
    assert plan["in"]["end_frame"] == 12


def test_rect_strings_roundtrip_two_keyframes():
    plan = _plan()
    for role in ("out", "in"):
        parsed = parse_keyframe_string("rect", plan[role]["transform_rect"], fps=30.0)
        assert len(parsed) == 2
        parsed_b = parse_keyframe_string("scalar", plan[role]["blur_radius"], fps=30.0)
        assert len(parsed_b) == 2


# --------------------------------------------------------------------------
# Easing variants -> MLT operator chars
# --------------------------------------------------------------------------

def test_cubic_easing_uses_directional_operators():
    plan = _plan(easing="cubic")
    # cubic_in operator = 'g' (out clip accelerates into the cut).
    assert "g=" in plan["out"]["transform_rect"]
    assert "g=" in plan["out"]["blur_radius"]
    # cubic_out operator = 'h' (in clip decelerates out of the cut).
    assert "h=" in plan["in"]["transform_rect"]
    assert "h=" in plan["in"]["blur_radius"]


def test_expo_easing_uses_expo_operators():
    plan = _plan(easing="expo")
    # expo_in operator = 'p', expo_out = 'q'.
    assert "p=" in plan["out"]["transform_rect"]
    assert "q=" in plan["in"]["transform_rect"]
    assert "g=" not in plan["out"]["transform_rect"]


def test_linear_easing_has_no_ease_operators():
    plan = _plan(easing="linear")
    # linear operator is empty; no family char before '='.
    assert "g=" not in plan["out"]["transform_rect"]
    assert "h=" not in plan["in"]["transform_rect"]


def test_unknown_easing_raises():
    with pytest.raises(ValueError):
        _plan(easing="wobble")


# --------------------------------------------------------------------------
# Direction variants -> pan sign + blur angle
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "direction, expected_angle",
    [("left", 0.0), ("right", 0.0), ("up", 90.0), ("down", 90.0)],
)
def test_blur_angle_by_direction(direction, expected_angle):
    plan = _plan(direction=direction)
    assert plan["blur_angle"] == expected_angle
    assert plan["out"]["blur_angle"] == expected_angle
    assert plan["in"]["blur_angle"] == expected_angle


def test_left_and_right_pan_are_mirrored():
    left = parse_keyframe_string("rect", _plan(direction="left")["out"]["transform_rect"], fps=30.0)
    right = parse_keyframe_string("rect", _plan(direction="right")["out"]["transform_rect"], fps=30.0)
    # The punched (final) keyframe x-offset flips sign between left and right.
    left_x = left[-1].value[0]
    right_x = right[-1].value[0]
    centre = (1920 - 1920 * 1.4) / 2.0
    assert left_x < centre < right_x


def test_outgoing_and_incoming_pan_from_opposite_sides():
    plan = _plan(direction="left")
    out_final = parse_keyframe_string("rect", plan["out"]["transform_rect"], fps=30.0)[-1].value
    in_first = parse_keyframe_string("rect", plan["in"]["transform_rect"], fps=30.0)[0].value
    centre = (1920 - 1920 * 1.4) / 2.0
    # Outgoing flies left (x below centre); incoming enters from the right (x above).
    assert out_final[0] < centre
    assert in_first[0] > centre


def test_up_direction_pans_vertically_not_horizontally():
    plan = _plan(direction="up")
    out_final = parse_keyframe_string("rect", plan["out"]["transform_rect"], fps=30.0)[-1].value
    x_centre = (1920 - 1920 * 1.4) / 2.0
    y_centre = (1080 - 1080 * 1.4) / 2.0
    assert out_final[0] == pytest.approx(x_centre)   # no horizontal pan
    assert out_final[1] < y_centre                   # panned up


# --------------------------------------------------------------------------
# Zoom + validation
# --------------------------------------------------------------------------

def test_zoom_amount_sets_scaled_dimensions():
    plan = _plan(zoom_amount=1.5)
    out_final = parse_keyframe_string("rect", plan["out"]["transform_rect"], fps=30.0)[-1].value
    assert out_final[2] == pytest.approx(1920 * 1.5)   # width
    assert out_final[3] == pytest.approx(1080 * 1.5)   # height


def test_blur_peaks_at_cut():
    plan = _plan(blur=8.0)
    out_blur = parse_keyframe_string("scalar", plan["out"]["blur_radius"], fps=30.0)
    in_blur = parse_keyframe_string("scalar", plan["in"]["blur_radius"], fps=30.0)
    assert out_blur[0].value == 0.0 and out_blur[-1].value == 8.0   # ramp up to cut
    assert in_blur[0].value == 8.0 and in_blur[-1].value == 0.0     # ramp down from cut


@pytest.mark.parametrize("bad", [
    {"direction": "sideways"},
    {"duration_frames": 0},
    {"zoom_amount": 1.0},
    {"blur": -1.0},
    {"pan_fraction": 1.5},
])
def test_validation_errors(bad):
    with pytest.raises(ValueError):
        _plan(**bad)
