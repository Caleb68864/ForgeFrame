"""Unit tests for the camera-shake / drop-shadow pipeline pure functions.

Covers ``workshop_video_brain.edit_mcp.pipelines.shake_shadow`` -- the pure
logic behind the ``effect_camera_shake`` / ``effect_drop_shadow`` bundle tools.
"""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string
from workshop_video_brain.edit_mcp.pipelines.shake_shadow import (
    AMP_FRACTION,
    ZOOM_PER_INTENSITY,
    _clamp_offset,
    camera_shake_keyframes,
    drop_shadow_params,
    shake_step_frames,
)

W, H, FPS = 1920, 1080, 30.0


def _shake(**kw):
    base = dict(width=W, height=H, start_frame=0, end_frame=90, fps=FPS)
    base.update(kw)
    return camera_shake_keyframes(**base)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_same_seed_is_byte_identical():
    a = _shake(seed=42)
    b = _shake(seed=42)
    assert a["rect"] == b["rect"]


def test_different_seed_changes_output():
    a = _shake(seed=1)
    b = _shake(seed=2)
    assert a["rect"] != b["rect"]


def test_seed_none_is_deterministic():
    # seed=None must still be reproducible (fixed default seed).
    a = _shake(seed=None)
    b = _shake(seed=None)
    assert a["rect"] == b["rect"]


# ---------------------------------------------------------------------------
# Frequency / cadence math
# ---------------------------------------------------------------------------

def test_shake_step_frames_rounds_fps_over_freq():
    assert shake_step_frames(8.0, 30.0) == 4    # round(3.75)
    assert shake_step_frames(15.0, 30.0) == 2   # round(2.0)
    assert shake_step_frames(1000.0, 30.0) == 1  # floor clamps to >= 1


@pytest.mark.parametrize("bad", [0.0, -3.0])
def test_shake_step_frames_rejects_nonpositive_freq(bad):
    with pytest.raises(ValueError):
        shake_step_frames(bad, 30.0)


def test_higher_frequency_yields_more_keyframes():
    slow = _shake(frequency_hz=2.0)
    fast = _shake(frequency_hz=20.0)
    assert fast["keyframe_count"] > slow["keyframe_count"]
    assert fast["step_frames"] < slow["step_frames"]


def test_keyframe_count_matches_written_rect_keyframes():
    out = _shake(seed=7)
    parsed = parse_keyframe_string("rect", out["rect"], fps=FPS)
    assert len(parsed) == out["keyframe_count"]


def test_last_frame_always_included():
    out = _shake(start_frame=0, end_frame=91, frequency_hz=8.0)
    parsed = parse_keyframe_string("rect", out["rect"], fps=FPS)
    assert parsed[-1].frame == 91


# ---------------------------------------------------------------------------
# Intensity scaling
# ---------------------------------------------------------------------------

def test_zoom_scales_with_intensity():
    assert _shake(intensity=0.0)["zoom"] == pytest.approx(1.0)
    assert _shake(intensity=1.0)["zoom"] == pytest.approx(1.0 + ZOOM_PER_INTENSITY)
    assert _shake(intensity=0.5)["zoom"] < _shake(intensity=1.0)["zoom"]


def test_zero_intensity_is_static_centered():
    out = _shake(intensity=0.0, seed=99)
    parsed = parse_keyframe_string("rect", out["rect"], fps=FPS)
    # No overscan, no jitter: every rect is exactly (0, 0, W, H, 1).
    for kf in parsed:
        assert kf.value[:4] == [0.0, 0.0, float(W), float(H)]


def test_amplitude_reported_from_margin():
    out = _shake(intensity=1.0)
    margin_x = (round(W * out["zoom"]) - W) / 2.0
    ax, _ay = out["amplitude_px"]
    assert ax == pytest.approx(AMP_FRACTION * margin_x)


# ---------------------------------------------------------------------------
# Bounds / edge coverage invariant
# ---------------------------------------------------------------------------

def test_clamp_offset_bounds():
    assert _clamp_offset(500.0, 10.0) == 10.0
    assert _clamp_offset(-500.0, 10.0) == -10.0
    assert _clamp_offset(3.0, 10.0) == 3.0


def test_jitter_never_reveals_black_edges():
    # For every keyframe the enlarged, shifted rect must still cover [0, W]x[0, H].
    out = _shake(intensity=1.0, seed=123, frequency_hz=15.0)
    parsed = parse_keyframe_string("rect", out["rect"], fps=FPS)
    for kf in parsed:
        x, y, w, h = kf.value[0], kf.value[1], kf.value[2], kf.value[3]
        assert x <= 0.0 + 1e-6, f"left edge exposed at {kf.frame}: x={x}"
        assert y <= 0.0 + 1e-6, f"top edge exposed at {kf.frame}: y={y}"
        assert x + w >= W - 1e-6, f"right edge exposed at {kf.frame}"
        assert y + h >= H - 1e-6, f"bottom edge exposed at {kf.frame}"


def test_first_keyframe_at_rest():
    out = _shake(intensity=1.0, seed=5, rotation=True)
    rect = parse_keyframe_string("rect", out["rect"], fps=FPS)
    margin = (round(W * out["zoom"]) - W) / 2.0
    # First rect sits at the centered overscan position (dx=dy=0).
    assert rect[0].value[0] == pytest.approx(-margin, abs=1e-3)
    rot = parse_keyframe_string("scalar", out["rotation"], fps=FPS)
    assert rot[0].value == 0.0


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------

def test_rotation_false_returns_none():
    assert _shake(rotation=False)["rotation"] is None


def test_rotation_true_emits_scalar_keyframes():
    out = _shake(rotation=True, seed=3)
    assert out["rotation"] is not None
    rot = parse_keyframe_string("scalar", out["rotation"], fps=FPS)
    assert len(rot) == out["keyframe_count"]
    # At least one non-zero roll away from the anchored start.
    assert any(kf.value != 0.0 for kf in rot[1:])


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "kwargs",
    [
        {"intensity": 1.5},
        {"intensity": -0.1},
        {"frequency_hz": 0.0},
        {"start_frame": -1},
        {"end_frame": 0},          # not > start_frame (0)
        {"end_frame": -5, "start_frame": 0},
        {"width": 0},
        {"height": -10},
    ],
)
def test_camera_shake_validation(kwargs):
    with pytest.raises(ValueError):
        _shake(**kwargs)


def test_bool_intensity_rejected():
    with pytest.raises(ValueError):
        _shake(intensity=True)


# ---------------------------------------------------------------------------
# drop_shadow_params
# ---------------------------------------------------------------------------

def test_drop_shadow_defaults():
    p = drop_shadow_params()
    assert p == {"radius": "6", "x": "8", "y": "8", "color": "#b4000000"}


def test_drop_shadow_custom_values():
    p = drop_shadow_params(blur_radius=20, offset_x=-5, offset_y=12, color="#80ff0000")
    assert p["radius"] == "20"
    assert p["x"] == "-5"
    assert p["y"] == "12"
    assert p["color"] == "#80ff0000"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"blur_radius": -1},
        {"blur_radius": True},
        {"offset_x": 1.5},
        {"color": ""},
        {"color": 123},
    ],
)
def test_drop_shadow_validation(kwargs):
    with pytest.raises(ValueError):
        drop_shadow_params(**kwargs)
