"""Unit tests for the pure rewind pipeline helpers (segment math, ffmpeg args,
filename construction) and effect_rewind tool registration."""
from __future__ import annotations

import pytest

from workshop_video_brain.edit_mcp.pipelines import rewind as rw


# ---------------------------------------------------------------------------
# Segment / duration math
# ---------------------------------------------------------------------------

def test_segment_duration_basic():
    assert rw.segment_duration(1.0, 3.0) == 2.0


def test_segment_duration_rejects_inverted():
    with pytest.raises(ValueError):
        rw.segment_duration(3.0, 1.0)


def test_segment_duration_rejects_empty():
    with pytest.raises(ValueError):
        rw.segment_duration(2.0, 2.0)


def test_segment_duration_rejects_negative_start():
    with pytest.raises(ValueError):
        rw.segment_duration(-1.0, 2.0)


def test_reversed_duration_applies_speed():
    assert rw.reversed_duration(1.0, 3.0, 2.0) == pytest.approx(1.0)
    assert rw.reversed_duration(0.0, 6.0, 3.0) == pytest.approx(2.0)


def test_reversed_duration_rejects_bad_speed():
    with pytest.raises(ValueError):
        rw.reversed_duration(0.0, 2.0, 0.0)


def test_reversed_frame_count_rounds_and_floors_to_one():
    assert rw.reversed_frame_count(1.0, 3.0, 2.0, 25.0) == 25
    assert rw.reversed_frame_count(0.0, 6.0, 3.0, 30.0) == 60
    # Very short segment still yields at least one frame.
    assert rw.reversed_frame_count(0.0, 0.01, 2.0, 25.0) == 1


def test_reversed_frame_count_rejects_bad_fps():
    with pytest.raises(ValueError):
        rw.reversed_frame_count(0.0, 2.0, 2.0, 0.0)


# ---------------------------------------------------------------------------
# atempo decomposition (ffmpeg's 0.5..2.0 constraint)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "speed,expected",
    [
        (2.0, [2.0]),
        (1.5, [1.5]),
        (0.5, [0.5]),
        (3.0, [2.0, 1.5]),
        (4.0, [2.0, 2.0]),
        (5.0, [2.0, 2.0, 1.25]),
    ],
)
def test_atempo_factors(speed, expected):
    factors = rw.atempo_factors(speed)
    assert factors == pytest.approx(expected)
    # Every factor stays within ffmpeg's allowed range.
    for f in factors:
        assert 0.5 - 1e-9 <= f <= 2.0 + 1e-9
    # Product reconstructs the requested speed.
    prod = 1.0
    for f in factors:
        prod *= f
    assert prod == pytest.approx(speed)


def test_atempo_chain_strings():
    assert rw.atempo_chain(3.0) == ["atempo=2", "atempo=1.5"]


def test_atempo_factors_rejects_zero():
    with pytest.raises(ValueError):
        rw.atempo_factors(0.0)


# ---------------------------------------------------------------------------
# ffmpeg filter / argument construction
# ---------------------------------------------------------------------------

def test_build_video_filter_trims_before_reverse_and_applies_speed():
    vf = rw.build_video_filter(1.0, 3.0, 2.0)
    # trim precedes reverse so only the segment is buffered/reversed.
    assert vf.index("trim=start=1:end=3") < vf.index("reverse")
    assert "reverse" in vf
    assert vf.endswith("setpts=PTS/2")


def test_build_audio_filter_mirrors_video():
    af = rw.build_audio_filter(1.0, 3.0, 3.0)
    assert "atrim=start=1:end=3" in af
    assert "areverse" in af
    assert af.endswith("atempo=2,atempo=1.5")


def test_build_reverse_args_with_audio():
    args = rw.build_reverse_args(1.0, 3.0, 2.0, include_audio=True)
    assert args[0] == "-vf"
    assert "-af" in args
    assert "-an" not in args


def test_build_reverse_args_without_audio_drops_audio():
    args = rw.build_reverse_args(1.0, 3.0, 2.0, include_audio=False)
    assert "-af" not in args
    assert "-an" in args


def test_build_reverse_args_validates_window():
    with pytest.raises(ValueError):
        rw.build_reverse_args(3.0, 1.0, 2.0)


# ---------------------------------------------------------------------------
# Output filename construction
# ---------------------------------------------------------------------------

def test_reversed_clip_name_is_deterministic_and_encodes_params():
    n1 = rw.reversed_clip_name("clip", 1.0, 3.0, 2.0)
    n2 = rw.reversed_clip_name("clip", 1.0, 3.0, 2.0)
    assert n1 == n2
    assert n1 == "clip_rewind_1-3_x2.mp4"


def test_reversed_clip_name_sanitizes_unsafe_characters():
    name = rw.reversed_clip_name("My Clip/final:take", 1.5, 2.5, 2.0)
    assert " " not in name
    assert "/" not in name
    assert ":" not in name
    assert name.endswith(".mp4")
    assert "rewind" in name


def test_reversed_clip_name_distinct_segments_do_not_collide():
    a = rw.reversed_clip_name("clip", 1.0, 3.0, 2.0)
    b = rw.reversed_clip_name("clip", 2.0, 4.0, 2.0)
    c = rw.reversed_clip_name("clip", 1.0, 3.0, 3.0)
    assert len({a, b, c}) == 3


# ---------------------------------------------------------------------------
# Tool registration
# ---------------------------------------------------------------------------

def test_effect_rewind_registered_with_mcp():
    from workshop_video_brain import server  # noqa: F401  (registers the tools)
    from tests._testkit import registered_tool_names

    names = registered_tool_names()
    assert "effect_rewind" in names, f"effect_rewind not registered: {names}"
