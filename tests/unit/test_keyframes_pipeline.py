"""Unit tests for the keyframes pipeline module."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    Keyframe,
    VALID_EASE_FAMILIES,
    VALID_EASING_NAMES,
    build_keyframe_string,
    merge_keyframes,
    normalize_time,
    parse_keyframe_string,
    resolve_easing,
)


# --- normalize_time -------------------------------------------------------

def test_normalize_time_frame():
    assert normalize_time({"frame": 60}, 30.0) == "00:00:02.000"


def test_normalize_time_seconds():
    assert normalize_time({"seconds": 2.0}, 30.0) == "00:00:02.000"


def test_normalize_time_timestamp_passthrough():
    assert normalize_time({"timestamp": "00:00:02.000"}, 30.0) == "00:00:02.000"


def test_normalize_time_missing_keys_raises():
    with pytest.raises(ValueError, match="missing required key"):
        normalize_time({}, 30.0)


def test_normalize_time_negative_frame_raises():
    with pytest.raises(ValueError, match="frame"):
        normalize_time({"frame": -1}, 30.0)


def test_normalize_time_malformed_timestamp_raises():
    with pytest.raises(ValueError, match="timestamp"):
        normalize_time({"timestamp": "2s"}, 30.0)


def test_normalize_time_rejects_multiple_keys():
    with pytest.raises(ValueError, match="exactly one"):
        normalize_time({"frame": 1, "seconds": 2.0}, 30.0)


# --- resolve_easing -------------------------------------------------------

def test_resolve_easing_linear_empty():
    assert resolve_easing("linear") == ""


def test_resolve_easing_smooth_tilde():
    assert resolve_easing("smooth") == "~"


def test_resolve_easing_hold_pipe():
    assert resolve_easing("hold") == "|"


def test_resolve_easing_ease_in_out_expo():
    assert resolve_easing("ease_in_out_expo") == "r"


def test_resolve_easing_ease_in_with_family_default():
    assert resolve_easing("ease_in", ease_family_default="expo") == "p"


def test_resolve_easing_raw_operator_passthrough():
    assert resolve_easing("$=") == "$"
    assert resolve_easing("~=") == "~"
    assert resolve_easing("|=") == "|"
    assert resolve_easing("=") == ""


def test_resolve_easing_unknown_name_lists_valid_set():
    with pytest.raises(ValueError) as ei:
        resolve_easing("wibble")
    msg = str(ei.value)
    assert "wibble" in msg
    # Should include some valid names.
    assert "cubic_in" in msg or "ease_in_expo" in msg or "linear" in msg


def test_resolve_easing_unknown_raw_operator():
    with pytest.raises(ValueError, match="keyframe-operators.md"):
        resolve_easing("Z=")


def test_valid_easing_names_and_families_exposed():
    assert "linear" in VALID_EASING_NAMES
    assert "ease_in_out_expo" in VALID_EASING_NAMES
    assert "cubic" in VALID_EASE_FAMILIES


# --- build_keyframe_string ------------------------------------------------

def test_build_keyframe_string_rect_two_frames():
    kfs = [
        Keyframe(frame=0, value=[0, 0, 1920, 1080, 1], easing="linear"),
        Keyframe(frame=60, value=[100, 50, 1920, 1080, 0.5], easing="ease_in_out"),
    ]
    out = build_keyframe_string("rect", kfs, 30.0, "cubic")
    assert out == "00:00:00.000=0 0 1920 1080 1;00:00:02.000i=100 50 1920 1080 0.5"


def test_build_keyframe_string_rect_four_tuple_adds_default_opacity():
    kfs = [Keyframe(frame=0, value=[10, 20, 1920, 1080], easing="linear")]
    out = build_keyframe_string("rect", kfs, 30.0, "cubic")
    assert out == "00:00:00.000=10 20 1920 1080 1"


def test_build_keyframe_string_scalar():
    kfs = [
        Keyframe(frame=0, value=0.0, easing="linear"),
        Keyframe(frame=30, value=0.5, easing="smooth"),
    ]
    out = build_keyframe_string("scalar", kfs, 30.0, "cubic")
    assert out == "00:00:00.000=0;00:00:01.000~=0.5"


def test_build_keyframe_string_color():
    kfs = [
        Keyframe(frame=0, value="#ff0000", easing="linear"),
        Keyframe(frame=30, value="#00ff00aa", easing="linear"),
    ]
    out = build_keyframe_string("color", kfs, 30.0, "cubic")
    assert out == "00:00:00.000=0xff0000ff;00:00:01.000=0x00ff00aa"


def test_build_keyframe_string_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        build_keyframe_string("scalar", [], 30.0, "cubic")


def test_build_keyframe_string_collision_different_values_raises():
    kfs = [
        Keyframe(frame=0, value=1.0, easing="linear"),
        Keyframe(frame=0, value=2.0, easing="linear"),
    ]
    with pytest.raises(ValueError, match="collision"):
        build_keyframe_string("scalar", kfs, 30.0, "cubic")


# --- parse_keyframe_string -------------------------------------------------

def test_parse_keyframe_string_roundtrip_scalar():
    kfs = [
        Keyframe(frame=0, value=0.0, easing="linear"),
        Keyframe(frame=30, value=0.5, easing="smooth"),
    ]
    s = build_keyframe_string("scalar", kfs, 30.0, "cubic")
    parsed = parse_keyframe_string("scalar", s, fps=30.0)
    assert len(parsed) == 2
    assert parsed[0].frame == 0
    assert parsed[0].value == 0.0
    assert parsed[0].easing == "linear"
    assert parsed[1].frame == 30
    assert parsed[1].value == 0.5
    assert parsed[1].easing == "smooth"


def test_parse_keyframe_string_roundtrip_rect():
    kfs = [
        Keyframe(frame=0, value=[0, 0, 1920, 1080, 1], easing="linear"),
        Keyframe(frame=60, value=[100, 50, 1920, 1080, 0.5], easing="ease_in_out_cubic"),
    ]
    s = build_keyframe_string("rect", kfs, 30.0, "cubic")
    parsed = parse_keyframe_string("rect", s, fps=30.0)
    assert len(parsed) == 2
    assert parsed[0].frame == 0
    assert parsed[0].value == [0.0, 0.0, 1920.0, 1080.0, 1.0]
    assert parsed[0].easing == "linear"
    assert parsed[1].frame == 60
    assert parsed[1].value == [100.0, 50.0, 1920.0, 1080.0, 0.5]
    # 'i' reverse-lookups to 'cubic_in_out' (terse alias).
    assert parsed[1].easing == "cubic_in_out"


def test_parse_keyframe_string_roundtrip_color():
    kfs = [
        Keyframe(frame=0, value="#ff0000", easing="linear"),
        Keyframe(frame=30, value="#00ff00aa", easing="hold"),
    ]
    s = build_keyframe_string("color", kfs, 30.0, "cubic")
    parsed = parse_keyframe_string("color", s, fps=30.0)
    assert parsed[0].value == "0xff0000ff"
    assert parsed[0].easing == "linear"
    assert parsed[1].value == "0x00ff00aa"
    assert parsed[1].easing == "hold"


def test_parse_keyframe_string_empty_returns_empty():
    assert parse_keyframe_string("scalar", "") == []
    assert parse_keyframe_string("scalar", "   ") == []


# --- merge_keyframes -----------------------------------------------------

def test_merge_keyframes_overlap_overwrites():
    existing = [
        Keyframe(frame=0, value=0.0, easing="linear"),
        Keyframe(frame=30, value=0.5, easing="linear"),
        Keyframe(frame=60, value=1.0, easing="linear"),
    ]
    new = [Keyframe(frame=30, value=0.9, easing="smooth")]
    merged = merge_keyframes(existing, new)
    assert [k.frame for k in merged] == [0, 30, 60]
    assert merged[1].value == 0.9
    assert merged[1].easing == "smooth"


def test_merge_keyframes_static_string_treated_as_frame_zero():
    merged = merge_keyframes("0.5", [Keyframe(frame=30, value=0.9, easing="linear")])
    assert len(merged) == 2
    assert merged[0].frame == 0
    assert merged[0].value == "0.5"
    assert merged[0].easing == "linear"
    assert merged[1].frame == 30


def test_merge_keyframes_duplicate_frames_in_new_last_wins():
    existing: list[Keyframe] = []
    new = [
        Keyframe(frame=10, value=1.0, easing="linear"),
        Keyframe(frame=10, value=2.0, easing="linear"),
    ]
    merged = merge_keyframes(existing, new)
    assert len(merged) == 1
    assert merged[0].value == 2.0


def test_merge_keyframes_sorted_output():
    existing = [Keyframe(frame=60, value=1.0, easing="linear")]
    new = [
        Keyframe(frame=0, value=0.0, easing="linear"),
        Keyframe(frame=30, value=0.5, easing="linear"),
    ]
    merged = merge_keyframes(existing, new)
    assert [k.frame for k in merged] == [0, 30, 60]
