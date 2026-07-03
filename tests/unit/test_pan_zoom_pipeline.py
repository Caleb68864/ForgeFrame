"""Unit tests for the pan/zoom (Ken Burns) pure-function pipeline.

Covers preset geometry across 1080p / 4K / vertical profiles, frame-bound
clamping, easing operator emission, NTSC fps timestamp rounding, and the
lead-in hold. No XML / MCP / filesystem here -- see
``tests/integration/test_pan_zoom_mcp_tool.py`` for the tool.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines import pan_zoom as pz
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string


# ---------------------------------------------------------------------------
# Preset geometry
# ---------------------------------------------------------------------------

def test_zoom_in_start_is_full_frame_end_is_centered_1080p():
    start, end = pz.preset_rects("zoom_in", 1920, 1080)
    assert start == (0.0, 0.0, 1920.0, 1080.0)
    # _ZOOM_SCALE (0.6) centered region.
    assert end == (384.0, 216.0, 1152.0, 648.0)


def test_zoom_out_is_reverse_of_zoom_in():
    zi_s, zi_e = pz.preset_rects("zoom_in", 1920, 1080)
    zo_s, zo_e = pz.preset_rects("zoom_out", 1920, 1080)
    assert (zo_s, zo_e) == (zi_e, zi_s)


def test_zoom_in_scales_with_4k_profile():
    start, end = pz.preset_rects("zoom_in", 3840, 2160)
    assert start == (0.0, 0.0, 3840.0, 2160.0)
    # 0.6 * dims, centered.
    assert end == (768.0, 432.0, 2304.0, 1296.0)


def test_zoom_in_scales_with_vertical_profile():
    start, end = pz.preset_rects("zoom_in", 1080, 1920)
    assert start == (0.0, 0.0, 1080.0, 1920.0)
    assert end == (216.0, 384.0, 648.0, 1152.0)


def test_pan_left_to_right_travels_along_x_only_1080p():
    start, end = pz.preset_rects("pan_left_to_right", 1920, 1080)
    # _PAN_SCALE (0.7): region 1344 x 756, y centered at 162.
    assert start == (0.0, 162.0, 1344.0, 756.0)
    assert end == (576.0, 162.0, 1344.0, 756.0)
    assert start[1] == end[1]  # no vertical travel
    assert start[2:] == end[2:]  # constant size => pure pan


def test_pan_presets_stay_within_frame_bounds():
    for preset in pz.PRESETS:
        for w, h in ((1920, 1080), (3840, 2160), (1080, 1920)):
            s, e = pz.preset_rects(preset, w, h)
            for rect in (s, e):
                x, y, rw, rh = rect
                assert 0.0 <= x and 0.0 <= y
                assert x + rw <= w + 1e-6
                assert y + rh <= h + 1e-6


def test_kenburns_tl_br_moves_from_top_left_to_bottom_right():
    start, end = pz.preset_rects("kenburns_tl_br", 1920, 1080)
    assert start == (0.0, 0.0, 1344.0, 756.0)
    assert end == (576.0, 324.0, 1344.0, 756.0)


def test_unknown_preset_raises():
    with pytest.raises(ValueError, match="unknown preset"):
        pz.preset_rects("spin_around", 1920, 1080)


# ---------------------------------------------------------------------------
# Clamping
# ---------------------------------------------------------------------------

def test_clamp_pulls_oversized_negative_rect_to_full_frame():
    assert pz.clamp_rect((-100, -50, 5000, 5000), 1920, 1080) == (
        0.0, 0.0, 1920.0, 1080.0,
    )


def test_clamp_shifts_origin_so_rect_fits():
    assert pz.clamp_rect((1900, 0, 200, 100), 1920, 1080) == (
        1720.0, 0.0, 200.0, 100.0,
    )


def test_clamp_floors_zero_size_to_one_pixel():
    x, y, w, h = pz.clamp_rect((10, 10, 0, 0), 1920, 1080)
    assert w == 1.0 and h == 1.0


def test_clamp_accepts_five_element_rect_and_drops_opacity():
    assert pz.clamp_rect((0, 0, 100, 100, 0.5), 1920, 1080) == (
        0.0, 0.0, 100.0, 100.0,
    )


def test_clamp_rejects_bad_rect_length():
    with pytest.raises(ValueError, match="4 or 5"):
        pz.clamp_rect((0, 0, 100), 1920, 1080)


def test_clamp_rejects_nonpositive_frame():
    with pytest.raises(ValueError, match="positive"):
        pz.clamp_rect((0, 0, 10, 10), 0, 1080)


# ---------------------------------------------------------------------------
# Keyframe string output
# ---------------------------------------------------------------------------

def test_build_emits_two_keyframes_with_easing_operator():
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (384, 216, 1152, 648), 60, 30.0,
        easing="cubic_in_out",
    )
    # cubic_in_out => operator 'i' on the start keyframe.
    assert out == (
        "00:00:00.000i=0 0 1920 1080 1;00:00:02.000=384 216 1152 648 1"
    )


def test_build_linear_easing_has_no_operator_prefix():
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (100, 100, 800, 600), 30, 30.0, easing="linear",
    )
    assert out.startswith("00:00:00.000=")  # no operator char before '='


def test_build_roundtrips_through_parser():
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (384, 216, 1152, 648), 60, 30.0,
    )
    parsed = parse_keyframe_string("rect", out, fps=30.0)
    assert [k.frame for k in parsed] == [0, 60]
    assert parsed[0].value[:4] == [0.0, 0.0, 1920.0, 1080.0]
    assert parsed[1].value[:4] == [384.0, 216.0, 1152.0, 648.0]


def test_hold_frames_emits_three_keyframes_holding_start():
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (384, 216, 1152, 648), 60, 30.0,
        easing="cubic_in_out", hold_frames=15,
    )
    parsed = parse_keyframe_string("rect", out, fps=30.0)
    assert [k.frame for k in parsed] == [0, 15, 75]
    # Start rect held across the first two keyframes.
    assert parsed[0].value[:4] == parsed[1].value[:4] == [0.0, 0.0, 1920.0, 1080.0]
    assert parsed[2].value[:4] == [384.0, 216.0, 1152.0, 648.0]


def test_ntsc_fps_rounds_timestamp_deterministically():
    # 29.97 fps == 30000/1001. Frame 60 -> 60*1001/30000 = 2.002s exactly.
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (384, 216, 1152, 648), 60, 30000 / 1001,
    )
    assert "00:00:02.002=" in out


def test_ntsc_23976_fps_rounding():
    # 23.976 fps == 24000/1001. Frame 48 -> 48*1001/24000 = 2.002s.
    out = pz.build_pan_zoom_keyframes(
        (0, 0, 1920, 1080), (384, 216, 1152, 648), 48, 24000 / 1001,
    )
    assert "00:00:02.002=" in out


def test_build_rejects_nonpositive_duration():
    with pytest.raises(ValueError, match="duration_frames"):
        pz.build_pan_zoom_keyframes(
            (0, 0, 1920, 1080), (1, 1, 10, 10), 0, 30.0,
        )


def test_build_rejects_negative_hold():
    with pytest.raises(ValueError, match="hold_frames"):
        pz.build_pan_zoom_keyframes(
            (0, 0, 1920, 1080), (1, 1, 10, 10), 30, 30.0, hold_frames=-1,
        )


def test_build_rejects_unknown_easing():
    with pytest.raises(ValueError, match="easing"):
        pz.build_pan_zoom_keyframes(
            (0, 0, 1920, 1080), (1, 1, 10, 10), 30, 30.0, easing="bogus",
        )
