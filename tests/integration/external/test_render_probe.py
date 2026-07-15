"""render-and-probe: a built project renders to valid media with the right
container metadata (duration, resolution, fps, stream counts).

Catches "filter written but project won't render" classes of bug that XML
assertions can't. Uses ffprobe as the external oracle.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.timeline import AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import builders
from ._oracle import probe, render_video

pytestmark = pytest.mark.external

FPS = 25.0
FRAMES = 50  # 2 seconds


def _build_project():
    """Clip + root-level effect + two-track composite -- a realistic mix."""
    proj = builders.two_video_track_project(frames=FRAMES, fps=FPS)
    # A root-level effect on the bottom clip.
    xml = builders.build_filter_xml("avfilter.negate", track=0, clip=0)
    patcher.insert_effect_xml(proj, (0, 0), xml, position=0)
    # A composite between the two video tracks.
    proj = patcher.patch_project(
        proj,
        [AddComposition(track_a=0, track_b=1, start_frame=0, end_frame=FRAMES - 1,
                        composition_type="frei0r.cairoblend")],
    )
    return proj


def test_render_produces_expected_container(melt_bin, ffprobe_bin, render_dir: Path):
    proj = _build_project()
    project_path = render_dir / "probe.kdenlive"
    serialize_project(proj, project_path)

    out = render_video(project_path, render_dir / "probe.mp4", frames=FRAMES, melt_bin=melt_bin)
    meta = probe(out, ffprobe_bin=ffprobe_bin)

    # Duration within ~1 frame of 2 seconds.
    expected = FRAMES / FPS
    assert meta.duration is not None
    assert abs(meta.duration - expected) <= (1.0 / FPS) + 0.1, (
        f"duration {meta.duration} != ~{expected}"
    )
    assert meta.width == builders.DEFAULT_WIDTH
    assert meta.height == builders.DEFAULT_HEIGHT
    assert meta.fps is not None and abs(meta.fps - FPS) < 0.5
    assert len(meta.video_streams) >= 1
    assert len(meta.audio_streams) >= 1
