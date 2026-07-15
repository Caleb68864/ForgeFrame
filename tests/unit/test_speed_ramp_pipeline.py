"""Unit tests for the pure speed-ramp planning helpers.

Covers keyframe parsing / format detection, easing curves, segment planning for
both keyframe schemas at multiple frame rates, and the timewarp frame math whose
integral the external render oracle asserts.
"""
from __future__ import annotations

import json

import pytest

from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr


# ---------------------------------------------------------------------------
# keyframe parsing / format detection
# ---------------------------------------------------------------------------

def test_parse_keyframes_accepts_json_string_and_list():
    data = [{"at_seconds": 0, "speed": 2.0}]
    assert sr.parse_keyframes(json.dumps(data)) == data
    assert sr.parse_keyframes(data) == data


@pytest.mark.parametrize("bad", ["not json", "{}", "[]", "[1, 2]"])
def test_parse_keyframes_rejects_bad_input(bad):
    with pytest.raises(ValueError):
        sr.parse_keyframes(bad)


def test_keyframe_format_detection():
    assert sr.keyframe_format([{"at_seconds": 0, "speed": 1.0}]) == "speed"
    assert sr.keyframe_format([{"output_seconds": 0, "source_seconds": 0}]) == "timemap"
    with pytest.raises(ValueError):
        sr.keyframe_format([{"foo": 1}])


# ---------------------------------------------------------------------------
# easing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["linear", "cubic", "ease_in", "ease_out", "unknown"])
def test_ease_endpoints_are_fixed(mode):
    assert sr.ease(0.0, mode) == pytest.approx(0.0)
    assert sr.ease(1.0, mode) == pytest.approx(1.0)


def test_ease_clamps_out_of_range():
    assert sr.ease(-1.0, "cubic") == pytest.approx(0.0)
    assert sr.ease(2.0, "cubic") == pytest.approx(1.0)


def test_cubic_is_smoothstep_midpoint():
    assert sr.ease(0.5, "cubic") == pytest.approx(0.5)
    # smoothstep is flatter than linear near the ends
    assert sr.ease(0.25, "cubic") < 0.25


def test_interp_speed_linear_midpoint():
    assert sr.interp_speed(1.0, 3.0, 0.5, "linear") == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# segment planning -- speed format
# ---------------------------------------------------------------------------

def test_single_keyframe_is_constant_speed():
    segs = sr.plan_segments(
        [{"at_seconds": 0, "speed": 2.0}], clip_frames=100, fps=25.0
    )
    assert len(segs) == 1
    assert segs[0].src_in == 0 and segs[0].src_out == 100
    assert segs[0].speed == pytest.approx(2.0)


def test_two_phase_ramp_covers_clip_and_integral():
    # fast (2x) first 2s, slow (0.5x) last 2s of a 4s / 100-frame clip.
    kfs = [
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ]
    segs = sr.plan_segments(kfs, clip_frames=100, fps=25.0, easing="linear")
    # full source coverage
    assert segs[0].src_in == 0
    assert segs[-1].src_out == 100
    src, out = sr.source_output_frames(segs)
    assert src == 100
    # 50 frames @2x -> 25, 50 frames @0.5x -> 100  => 125 output frames
    assert out == 125


@pytest.mark.parametrize("fps", [24.0, 25.0, 30.0, 60.0])
def test_output_frames_scale_with_fps(fps):
    clip_frames = int(round(4 * fps))
    # constant 2x over the whole clip halves the output frame count (+/- rounding)
    segs = sr.plan_segments(
        [{"at_seconds": 0, "speed": 2.0}], clip_frames=clip_frames, fps=fps
    )
    _, out = sr.source_output_frames(segs)
    assert abs(out - round(clip_frames / 2)) <= 1


def test_easing_subdivides_ramp_into_multiple_segments():
    kfs = [{"at_seconds": 0, "speed": 1.0}, {"at_seconds": 4, "speed": 4.0}]
    segs = sr.plan_segments(
        kfs, clip_frames=100, fps=25.0, easing="cubic", subdivisions=8
    )
    assert len(segs) > 1
    # speeds are monotonically non-decreasing along a rising ramp
    speeds = [s.speed for s in segs]
    assert speeds == sorted(speeds)
    assert speeds[0] >= 1.0 and speeds[-1] <= 4.0
    # contiguous coverage, no gaps/overlaps
    for a, b in zip(segs, segs[1:]):
        assert a.src_out == b.src_in


def test_edge_hold_before_first_and_after_last_keyframe():
    kfs = [{"at_seconds": 1, "speed": 2.0}, {"at_seconds": 2, "speed": 2.0}]
    segs = sr.plan_segments(kfs, clip_frames=100, fps=25.0)
    assert segs[0].src_in == 0  # held back to clip start
    assert segs[-1].src_out == 100  # held out to clip end


def test_speed_out_of_range_rejected():
    with pytest.raises(ValueError):
        sr.plan_segments([{"at_seconds": 0, "speed": 999}], clip_frames=100, fps=25.0)
    with pytest.raises(ValueError):
        sr.plan_segments([{"at_seconds": 0, "speed": 0}], clip_frames=100, fps=25.0)


def test_negative_time_rejected():
    with pytest.raises(ValueError):
        sr.plan_segments([{"at_seconds": -1, "speed": 2}], clip_frames=100, fps=25.0)


# ---------------------------------------------------------------------------
# segment planning -- timemap format
# ---------------------------------------------------------------------------

def test_timemap_constant_slowdown():
    # output 0..4s shows source 0..2s  => 0.5x (slow motion)
    kfs = [
        {"output_seconds": 0, "source_seconds": 0},
        {"output_seconds": 4, "source_seconds": 2},
    ]
    segs = sr.plan_segments(kfs, clip_frames=100, fps=25.0)
    assert len(segs) == 1
    assert segs[0].speed == pytest.approx(0.5)
    assert segs[0].src_in == 0 and segs[0].src_out == 50


def test_timemap_two_slopes():
    kfs = [
        {"output_seconds": 0, "source_seconds": 0},
        {"output_seconds": 1, "source_seconds": 2},  # 2x
        {"output_seconds": 3, "source_seconds": 3},  # 0.5x
    ]
    segs = sr.plan_segments(kfs, clip_frames=100, fps=25.0)
    assert segs[0].speed == pytest.approx(2.0)
    assert segs[1].speed == pytest.approx(0.5)


def test_timemap_requires_two_points_and_forward_source():
    with pytest.raises(ValueError):
        sr.plan_segments([{"output_seconds": 0, "source_seconds": 0}], clip_frames=100, fps=25.0)
    backwards = [
        {"output_seconds": 0, "source_seconds": 2},
        {"output_seconds": 1, "source_seconds": 1},
    ]
    with pytest.raises(ValueError):
        sr.plan_segments(backwards, clip_frames=100, fps=25.0)


# ---------------------------------------------------------------------------
# timewarp frame math
# ---------------------------------------------------------------------------

def test_timewarp_entry_maps_source_to_producer_frames():
    # source [0, 50) at 2x -> producer frames [0, 24]  (25 frames)
    assert sr.timewarp_entry(0, 0, 50, 2.0) == (0, 24)
    # source [50, 100) at 0.5x -> producer frames [100, 199]  (100 frames)
    assert sr.timewarp_entry(0, 50, 100, 0.5) == (100, 199)


def test_timewarp_entry_respects_entry_in_offset():
    tw_in, tw_out = sr.timewarp_entry(10, 0, 20, 2.0)
    assert tw_in == 5  # round((10+0)/2)
    assert tw_out == 14  # round((10+20)/2) - 1


def test_total_output_frames_matches_manual_sum():
    kfs = [
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ]
    segs = sr.plan_segments(kfs, clip_frames=100, fps=25.0, easing="linear")
    manual = sum(
        sr.timewarp_entry(0, s.src_in, s.src_out, s.speed)[1]
        - sr.timewarp_entry(0, s.src_in, s.src_out, s.speed)[0]
        + 1
        for s in segs
    )
    assert sr.total_output_frames(0, segs) == manual == 125
