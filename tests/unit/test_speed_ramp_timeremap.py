"""Unit tests for the native ``timeremap`` engine helpers in ``speed_ramp``."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr


def _two_phase_segments():
    kfs = [
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ]
    return sr.plan_segments(kfs, clip_frames=100, fps=25.0, easing="linear")


def test_speed_map_total_matches_segments_engine():
    segs = _two_phase_segments()
    speed_map, total = sr.speed_map_from_segments(segs)
    # Native timeremap output length agrees with the timewarp/segments integral.
    assert total == sr.total_output_frames(0, segs)
    assert total == 125
    # Keyed by output frame; carries both segment speeds.
    assert speed_map.startswith("0=2")
    assert "0.5" in speed_map


def test_speed_map_is_a_step_function_per_segment():
    # A single constant-speed segment emits a flat step: start & end keys equal.
    segs = sr.plan_segments(
        [{"at_seconds": 0, "speed": 2.0}, {"at_seconds": 4, "speed": 2.0}],
        clip_frames=100, fps=25.0, easing="linear",
    )
    speed_map, total = sr.speed_map_from_segments(segs)
    assert total == 50  # 100 source frames at 2x
    keys = dict(kv.split("=") for kv in speed_map.split(";"))
    assert all(float(v) == 2.0 for v in keys.values())
    assert "0" in keys and "49" in keys


def test_speed_map_empty_rejected():
    with pytest.raises(ValueError):
        sr.speed_map_from_segments([])


def test_timeremap_link_properties_defaults():
    props = sr.timeremap_link_properties("0=1")
    assert props == {"speed_map": "0=1", "image_mode": "nearest", "pitch": "0"}


def test_timeremap_link_properties_blend_and_pitch():
    props = sr.timeremap_link_properties("0=0.5", image_mode="blend", pitch=True)
    assert props["image_mode"] == "blend"
    assert props["pitch"] == "1"


def test_timeremap_link_properties_bad_image_mode():
    with pytest.raises(ValueError):
        sr.timeremap_link_properties("0=1", image_mode="wobble")
