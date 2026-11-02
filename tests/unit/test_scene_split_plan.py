"""Shot planning: pure, no binaries."""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines.scene_split import build_shot_command_args, shot_ranges


def test_no_cuts_is_one_shot():
    assert shot_ranges([], 10.0) == [(0.0, 10.0)]


def test_zero_duration_is_no_shots():
    assert shot_ranges([1.0], 0.0) == []


def test_cuts_at_the_ends_are_dropped():
    assert shot_ranges([0.0, 5.0, 10.0, 12.0], 10.0) == [(0.0, 5.0), (5.0, 10.0)]


def test_unsorted_and_duplicate_cuts():
    assert shot_ranges([6.0, 2.0, 6.0], 10.0) == [(0.0, 2.0), (2.0, 6.0), (6.0, 10.0)]


def test_short_shot_merges_into_predecessor():
    assert shot_ranges([4.0, 4.2], 10.0, min_shot_seconds=0.5) == [(0.0, 4.2), (4.2, 10.0)]


def test_short_first_shot_merges_forward():
    assert shot_ranges([0.2, 5.0], 10.0, min_shot_seconds=0.5) == [(0.0, 5.0), (5.0, 10.0)]


def test_short_last_shot_merges_back():
    assert shot_ranges([9.8], 10.0, min_shot_seconds=0.5) == [(0.0, 10.0)]


def test_reencode_args():
    pre, args = build_shot_command_args(1.5, 4.0, reencode=True, has_video=True, has_audio=True)
    assert pre == ["-ss", "1.500"]
    assert args == ["-t", "2.500", "-map", "0:v:0?", "-map", "0:a:0?",
                    "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                    "-c:a", "aac"]


def test_reencode_without_audio_has_no_audio_codec():
    _pre, args = build_shot_command_args(0.0, 1.0, reencode=True, has_video=True, has_audio=False)
    assert "-c:a" not in args


def test_stream_copy_args():
    _pre, args = build_shot_command_args(0.0, 1.0, reencode=False, has_video=True, has_audio=True)
    assert args[-2:] == ["-c", "copy"]
    assert "libx264" not in args
