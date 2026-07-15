"""Frame-extraction adapter smoke tests.

Exercises ``workshop_video_brain.edit_mcp.adapters.ffmpeg.frames`` against
``tests/fixtures/media_generated/greenscreen_reporter_720.mp4``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.frames import (
    extract_centered_burst,
    extract_frame,
    extract_frame_burst,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "media_generated"
VIDEO_CLIP = FIXTURES / "greenscreen_reporter_720.mp4"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Fixture not available: {path}")


def test_run_ffmpeg_pre_input_args_default_is_unchanged(tmp_path):
    """Omitting pre_input_args yields byte-identical command to before."""
    result = run_ffmpeg(
        ["-frames:v", "1"],
        VIDEO_CLIP,
        tmp_path / "out.png",
        dry_run=True,
    )
    assert result.command == [
        "ffmpeg", "-y", "-i", str(VIDEO_CLIP), "-frames:v", "1", str(tmp_path / "out.png"),
    ]


def test_run_ffmpeg_pre_input_args_placed_before_input(tmp_path):
    result = run_ffmpeg(
        ["-frames:v", "1"],
        VIDEO_CLIP,
        tmp_path / "out.png",
        dry_run=True,
        pre_input_args=["-ss", "1.0"],
    )
    cmd = result.command
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "1.0"


def test_extract_frame_writes_matching_png(tmp_path):
    _require(VIDEO_CLIP)
    output_path = tmp_path / "frame.png"
    candidate = extract_frame(VIDEO_CLIP, timestamp_seconds=0.5, output_path=output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert candidate.timestamp_seconds == 0.5

    probed = probe_media(output_path)
    assert probed.width == candidate.width
    assert probed.height == candidate.height
    assert candidate.width > 0
    assert candidate.height > 0


def test_extract_frame_burst_respects_max_frames(tmp_path):
    _require(VIDEO_CLIP)
    candidates = extract_frame_burst(
        VIDEO_CLIP,
        start_seconds=0.0,
        end_seconds=2.0,
        interval_seconds=0.1,
        max_frames=5,
    )
    assert len(candidates) == 5

    timestamps = [c.timestamp_seconds for c in candidates]
    assert timestamps == sorted(timestamps)
    assert len(set(timestamps)) == len(timestamps)


def test_extract_centered_burst_spans_anchor(tmp_path):
    _require(VIDEO_CLIP)
    candidates = extract_centered_burst(
        VIDEO_CLIP,
        anchor_seconds=1.0,
        before_seconds=0.5,
        after_seconds=0.5,
        interval_seconds=0.25,
    )
    assert len(candidates) > 0
    for c in candidates:
        assert -1e-6 <= c.timestamp_seconds <= 1.5 + 1e-6
