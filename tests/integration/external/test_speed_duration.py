"""speed-duration: a 2x speed change should halve the clip's rendered duration.

``SetClipSpeed`` emits ``<filter type="speed">`` at the MLT root -- MLT speed
requires a ``timewarp:`` producer, so the filter is a no-op (melt logs a load
warning and renders the clip at normal speed). The rendered duration therefore
stays unchanged today.

xfail(strict): flips to passing when the timewarp fix lands (§1.1 / §3 "working
speed control").
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import SetClipSpeed
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import probe, render_video

pytestmark = pytest.mark.external

FPS = 25.0
SRC_FRAMES = 100  # 4 seconds


def test_2x_speed_halves_duration(melt_bin, ffprobe_bin, render_dir: Path):
    proj = builders.sequence_project(colors=[builders.RED], frames_each=SRC_FRAMES, fps=FPS)
    proj = patcher.patch_project(
        proj, [SetClipSpeed(track_ref=builders.VIDEO_TRACK, clip_index=0, speed=2.0)]
    )
    project_path = render_dir / "speed.kdenlive"
    serialize_project(proj, project_path)

    out = render_video(project_path, render_dir / "speed.mp4", frames=SRC_FRAMES, melt_bin=melt_bin)
    meta = probe(out, ffprobe_bin=ffprobe_bin)

    expected = (SRC_FRAMES / FPS) / 2.0  # ~2 s at 2x
    assert meta.duration is not None
    assert abs(meta.duration - expected) <= 0.25, (
        f"2x speed did not change duration: got {meta.duration}s, expected ~{expected}s"
    )
