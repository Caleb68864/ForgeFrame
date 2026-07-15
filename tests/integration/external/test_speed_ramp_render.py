"""External oracle: a speed ramp must change the rendered duration to match the
ramp integral.

Builds a 100-frame (4 s @25fps) solid clip, applies a two-phase ramp -- 2x for
the first 2 s (source frames 0..50 -> 25 output frames) then 0.5x for the last
2 s (source frames 50..100 -> 100 output frames) -- and renders it with real
melt. Expected timeline length is 125 frames / 5.0 s (up from the original 4.0 s),
proving the ``timewarp`` producer swaps actually re-time the clip.

This is the non-self-referential proof: melt + ffprobe, not our parser agreeing
with our serializer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import SpeedRamp
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr

from . import builders
from ._oracle import probe, render_video

pytestmark = pytest.mark.external

FPS = 25.0
SRC_FRAMES = 100  # 4 seconds


def _two_phase_segments():
    kfs = [
        {"at_seconds": 0, "speed": 2.0},
        {"at_seconds": 2, "speed": 2.0},
        {"at_seconds": 2, "speed": 0.5},
        {"at_seconds": 4, "speed": 0.5},
    ]
    return sr.plan_segments(kfs, clip_frames=SRC_FRAMES, fps=FPS, easing="linear")


def test_ramp_changes_rendered_duration_to_match_integral(
    melt_bin, ffprobe_bin, render_dir: Path
):
    segs = _two_phase_segments()
    expected_frames = sr.total_output_frames(0, segs)
    assert expected_frames == 125  # sanity: matches the hand-computed integral
    expected_seconds = expected_frames / FPS

    proj = builders.sequence_project(colors=[builders.RED], frames_each=SRC_FRAMES, fps=FPS)
    proj = patcher.patch_project(
        proj,
        [SpeedRamp(
            track_ref=builders.VIDEO_TRACK,
            clip_index=0,
            segments=[(s.src_in, s.src_out, s.speed) for s in segs],
        )],
    )
    project_path = render_dir / "ramp.kdenlive"
    serialize_project(proj, project_path)

    # Render generously past the expected length; the tractor bounds the output.
    out = render_video(
        project_path, render_dir / "ramp.mp4", frames=expected_frames + 40, melt_bin=melt_bin
    )
    meta = probe(out, ffprobe_bin=ffprobe_bin)

    assert meta.duration is not None
    # Duration must reflect the ramp integral (5.0 s), NOT the original 4.0 s.
    # Allow ~2 frames of container/encoder rounding.
    tol = 2.0 / FPS + 0.02
    assert abs(meta.duration - expected_seconds) <= tol, (
        f"ramp duration {meta.duration}s != expected {expected_seconds}s "
        f"(tol {tol:.3f}s)"
    )
    # And it is clearly distinct from the un-ramped 4.0 s length.
    assert abs(meta.duration - (SRC_FRAMES / FPS)) > 0.5
