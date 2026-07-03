"""Unit tests for the pure geometry of ``pipelines/motion_track.py``.

Covers the plan §5 pure-function list: padding to a target composition,
frame-bounds clamping, moving-average smoothing, boundary ease-in/out, MLT
``results`` parsing, and keyframe assembly at 23.976 / 25 / 30 fps.
"""
from __future__ import annotations

import math

import pytest

from workshop_video_brain.edit_mcp.pipelines import motion_track as mt
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string


# ---------------------------------------------------------------------------
# pad_rect_to_fill
# ---------------------------------------------------------------------------

class TestPadRectToFill:
    def test_subject_fills_requested_fraction(self):
        # 40px square subject, fill 0.5, 4:3 landscape frame -> the *height* is
        # the constraining axis, so subject_h / region_h == fill exactly and the
        # width fills at most `fill`.
        x, y, w, h = mt.pad_rect_to_fill((100, 100, 40, 40), 320, 240, 0.5)
        assert math.isclose(40 / h, 0.5, rel_tol=1e-6)  # tight axis == fill
        assert 40 / w <= 0.5 + 1e-6                      # other axis <= fill
        # Region keeps frame aspect ratio (no distortion on scale-up).
        assert math.isclose(w / h, 320 / 240, rel_tol=1e-6)

    def test_region_centred_on_subject(self):
        x, y, w, h = mt.pad_rect_to_fill((100, 60, 40, 40), 320, 240, 0.6)
        assert math.isclose(x + w / 2, 120, rel_tol=1e-6)
        assert math.isclose(y + h / 2, 80, rel_tol=1e-6)

    def test_smaller_fill_gives_larger_region(self):
        _, _, w_small, _ = mt.pad_rect_to_fill((100, 100, 40, 40), 320, 240, 0.3)
        _, _, w_big, _ = mt.pad_rect_to_fill((100, 100, 40, 40), 320, 240, 0.8)
        assert w_small > w_big  # lower fill == more zoomed out == bigger region

    @pytest.mark.parametrize("fill", [0.0, -0.1, 1.5])
    def test_invalid_fill_rejected(self, fill):
        with pytest.raises(ValueError):
            mt.pad_rect_to_fill((0, 0, 40, 40), 320, 240, fill)

    def test_zero_subject_rejected(self):
        with pytest.raises(ValueError):
            mt.pad_rect_to_fill((0, 0, 0, 40), 320, 240, 0.6)


# ---------------------------------------------------------------------------
# clamp_rect_to_bounds
# ---------------------------------------------------------------------------

class TestClampRectToBounds:
    def test_inside_unchanged(self):
        r = (10.0, 20.0, 100.0, 80.0)
        assert mt.clamp_rect_to_bounds(r, 320, 240) == r

    def test_origin_pushed_inside(self):
        # Region hangs off the right/bottom edge -> origin pulled back in.
        x, y, w, h = mt.clamp_rect_to_bounds((300, 200, 100, 80), 320, 240)
        assert x + w <= 320 + 1e-6
        assert y + h <= 240 + 1e-6
        assert x >= 0 and y >= 0

    def test_negative_origin_clamped(self):
        x, y, w, h = mt.clamp_rect_to_bounds((-50, -30, 100, 80), 320, 240)
        assert x == 0 and y == 0

    def test_oversize_shrinks_preserving_aspect(self):
        # Region bigger than the frame is shrunk uniformly (aspect preserved).
        x, y, w, h = mt.clamp_rect_to_bounds((-20, -20, 400, 300), 320, 240)
        assert w <= 320 + 1e-6 and h <= 240 + 1e-6
        assert math.isclose(w / h, 400 / 300, rel_tol=1e-6)
        assert 0 <= x and x + w <= 320 + 1e-6

    def test_bad_frame_rejected(self):
        with pytest.raises(ValueError):
            mt.clamp_rect_to_bounds((0, 0, 10, 10), 0, 240)


# ---------------------------------------------------------------------------
# moving_average_smooth
# ---------------------------------------------------------------------------

class TestMovingAverageSmooth:
    def test_window_one_is_identity(self):
        rects = [(0.0, 0.0, 10.0, 10.0), (5.0, 5.0, 10.0, 10.0)]
        assert mt.moving_average_smooth(rects, 1) == rects

    def test_reduces_jitter(self):
        # Alternating x jitter around a ramp -> smoothing lowers variance.
        rects = [(float(i + (3 if i % 2 else -3)), 0.0, 10.0, 10.0)
                 for i in range(11)]
        smoothed = mt.moving_average_smooth(rects, 5)
        raw_var = _variance([r[0] - i for i, r in enumerate(rects)])
        sm_var = _variance([r[0] - i for i, r in enumerate(smoothed)])
        assert sm_var < raw_var
        assert len(smoothed) == len(rects)

    def test_centre_is_local_mean(self):
        rects = [(0.0, 0, 10, 10), (10.0, 0, 10, 10), (20.0, 0, 10, 10)]
        smoothed = mt.moving_average_smooth(rects, 3)
        # centre element averages all three -> 10.0
        assert math.isclose(smoothed[1][0], 10.0, rel_tol=1e-9)

    def test_short_sequence_unchanged(self):
        rects = [(0.0, 0, 10, 10), (10.0, 0, 10, 10)]
        assert mt.moving_average_smooth(rects, 5) == rects


def _variance(xs):
    m = sum(xs) / len(xs)
    return sum((x - m) ** 2 for x in xs) / len(xs)


# ---------------------------------------------------------------------------
# boundary_easings
# ---------------------------------------------------------------------------

class TestBoundaryEasings:
    def test_ease_in_at_start_out_before_end(self):
        e = mt.boundary_easings(6, "cubic")
        assert e[0] == "ease_in_cubic"
        assert e[-2] == "ease_out_cubic"
        assert all(x == "smooth" for x in e[1:-2])

    def test_single_keyframe_linear(self):
        assert mt.boundary_easings(1, "cubic") == ["linear"]

    def test_two_keyframes(self):
        e = mt.boundary_easings(2, "sine")
        assert e[0] == "ease_in_sine"
        assert len(e) == 2

    def test_bad_family_rejected(self):
        with pytest.raises(ValueError):
            mt.boundary_easings(4, "nope")


# ---------------------------------------------------------------------------
# parse_mlt_results
# ---------------------------------------------------------------------------

class TestParseMltResults:
    def test_parses_spike_format(self):
        s = "0~=20 96 48 48 0;5~=34 98 43 43 0;10~=46 98 43 43 0"
        got = mt.parse_mlt_results(s)
        assert got[0] == (0, (20.0, 96.0, 48.0, 48.0))
        assert got[1] == (5, (34.0, 98.0, 43.0, 43.0))
        assert len(got) == 3

    def test_handles_negative_and_no_operator(self):
        got = mt.parse_mlt_results("0=10 20 30 40;49=-7 73 40 40 0")
        assert got[0] == (0, (10.0, 20.0, 30.0, 40.0))
        assert got[1] == (49, (-7.0, 73.0, 40.0, 40.0))

    def test_empty_is_empty(self):
        assert mt.parse_mlt_results("") == []
        assert mt.parse_mlt_results("   ") == []

    def test_malformed_raises(self):
        with pytest.raises(ValueError):
            mt.parse_mlt_results("garbage-no-equals")


# ---------------------------------------------------------------------------
# keyframe assembly at multiple frame rates (plan's fps list)
# ---------------------------------------------------------------------------

FPS_CASES = [23.976, 25.0, 30.0]


class TestKeyframeAssemblyFps:
    @pytest.mark.parametrize("fps", FPS_CASES)
    def test_tracked_rebases_to_zero_and_zooms_in(self, fps):
        # Tracker frames start at 100 (mid-source); zoom must rebase to 0.
        tracked = [
            (100, (20.0, 96.0, 48.0, 48.0)),
            (105, (34.0, 96.0, 48.0, 48.0)),
            (110, (46.0, 96.0, 48.0, 48.0)),
        ]
        s = mt.build_zoom_keyframes(tracked, 320, 240, fps, smoothing=1)
        kfs = parse_keyframe_string("rect", s, fps=fps)
        frames = sorted(k.frame for k in kfs)
        # Rebased: 100->0, 105->5, 110->10 (round-trip within 1 frame).
        assert frames[0] == 0
        assert abs(frames[-1] - 10) <= 1
        # Emitted rects are affine *destination* rects that zoom IN: the whole
        # frame is scaled up (dest w >= frame width) and offset off-screen.
        for k in kfs:
            x, y, w, h = k.value[:4]
            assert w >= 320 - 1e-6 and h >= 240 - 1e-6
            assert x <= 1e-6 and y <= 1e-6

    @pytest.mark.parametrize("fps", FPS_CASES)
    def test_static_is_constant_single_keyframe(self, fps):
        s = mt.build_static_zoom_keyframes((140, 96, 48, 48), 320, 240, fps)
        assert s.count(";") == 0  # single keyframe -> no separators
        kfs = parse_keyframe_string("rect", s, fps=fps)
        assert len(kfs) == 1
        assert kfs[0].frame == 0

    def test_same_frames_differ_across_fps(self):
        tracked = [(0, (20.0, 96.0, 48.0, 48.0)), (12, (40.0, 96.0, 48.0, 48.0))]
        s25 = mt.build_zoom_keyframes(tracked, 320, 240, 25.0, smoothing=1)
        s30 = mt.build_zoom_keyframes(tracked, 320, 240, 30.0, smoothing=1)
        # Same frame index -> different wall-clock timestamp per fps.
        assert s25 != s30

    def test_empty_tracked_rejected(self):
        with pytest.raises(ValueError):
            mt.build_zoom_keyframes([], 320, 240, 25.0)


class TestRegionToTransformRect:
    def test_full_frame_is_identity(self):
        # Region == whole frame -> destination == whole frame (no zoom).
        d = mt.region_to_transform_rect((0, 0, 320, 240), 320, 240)
        assert d == (0.0, 0.0, 320.0, 240.0)

    def test_known_inversion(self):
        # Region (40,72,128,96) in 320x240 -> the config proven to zoom in a
        # real melt render: (-100, -180, 800, 600).
        d = mt.region_to_transform_rect((40, 72, 128, 96), 320, 240)
        assert tuple(round(v, 3) for v in d) == (-100.0, -180.0, 800.0, 600.0)

    def test_smaller_region_scales_more(self):
        big = mt.region_to_transform_rect((0, 0, 160, 120), 320, 240)
        small = mt.region_to_transform_rect((0, 0, 80, 60), 320, 240)
        assert small[2] > big[2]  # smaller region -> bigger dest -> more zoom

    def test_zero_region_rejected(self):
        with pytest.raises(ValueError):
            mt.region_to_transform_rect((0, 0, 0, 96), 320, 240)


# ---------------------------------------------------------------------------
# engine + algorithm resolution
# ---------------------------------------------------------------------------

class TestResolution:
    def test_algorithm_canonicalised(self):
        assert mt.resolve_algorithm("csrt") == "CSRT"
        assert mt.resolve_algorithm("KcF") == "KCF"

    def test_unknown_algorithm_rejected(self):
        with pytest.raises(ValueError):
            mt.resolve_algorithm("magic")

    def test_unknown_engine_rejected(self):
        with pytest.raises(ValueError):
            mt.resolve_engine("tensorflow")

    def test_opencv_missing_hint(self, monkeypatch):
        monkeypatch.setattr(mt, "engine_available", lambda n: False)
        with pytest.raises(mt.TrackerUnavailable) as exc:
            mt.resolve_engine("opencv")
        assert "opencv-contrib" in str(exc.value)
