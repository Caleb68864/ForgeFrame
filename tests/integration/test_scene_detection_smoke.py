"""Scene-change detection adapter smoke tests.

Exercises ``workshop_video_brain.edit_mcp.adapters.ffmpeg.scene`` against
``tests/fixtures/media_generated/greenscreen_reporter_720.mp4``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import detect_scene_changes

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "media_generated"
VIDEO_CLIP = FIXTURES / "greenscreen_reporter_720.mp4"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Fixture not available: {path}")


def test_detect_scene_changes_within_range_respects_minimum_gap(tmp_path):
    _require(VIDEO_CLIP)
    duration = probe_media(VIDEO_CLIP).duration_seconds

    changes = detect_scene_changes(
        VIDEO_CLIP,
        start_seconds=0.0,
        end_seconds=duration,
        threshold=0.30,
        minimum_gap_seconds=0.5,
    )

    assert len(changes) > 0
    for change in changes:
        assert 0.0 - 1e-6 <= change.timestamp_seconds <= duration + 1e-6

    timestamps = [c.timestamp_seconds for c in changes]
    assert timestamps == sorted(timestamps)
    for earlier, later in zip(timestamps, timestamps[1:]):
        assert (later - earlier) >= 0.5 - 1e-6


def test_detect_scene_changes_static_range_falls_back_to_uniform_sample(tmp_path):
    _require(VIDEO_CLIP)

    # An extremely high threshold means ffmpeg's scene filter will not fire,
    # exercising the bounded uniform-sampling fallback path.
    changes = detect_scene_changes(
        VIDEO_CLIP,
        start_seconds=0.0,
        end_seconds=2.0,
        threshold=0.999,
        minimum_gap_seconds=0.5,
    )

    assert len(changes) > 0
    assert len(changes) <= 8
    for change in changes:
        assert -1e-6 <= change.timestamp_seconds <= 2.0 + 1e-6


def test_detect_scene_changes_returns_list_of_scene_change(tmp_path):
    _require(VIDEO_CLIP)

    changes = detect_scene_changes(VIDEO_CLIP)

    assert isinstance(changes, list)
    assert len(changes) > 0
    for change in changes:
        assert hasattr(change, "timestamp_seconds")
        assert hasattr(change, "score")
