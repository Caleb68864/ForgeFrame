"""Native timeremap engine: a ``<chain>`` + ``timeremap`` link renders to the
ramp's integral duration, agreeing with the piecewise ``segments`` engine.

The speed-ramp agent proved the ``timeremap`` link *loads* headless but needed
``<chain>``/``<link>`` XML the serializer could not emit. Wave-4a added chain/
link serialization; this is the render proof that the native route now works:

* Generate a 100-frame (4 s @25fps) test-pattern source.
* Plan a two-phase ramp -- 2x for the first 2 s (source 0..50 -> 25 output
  frames) then 0.5x for the last 2 s (source 50..100 -> 100 output frames) --
  whose integral is 125 output frames / 5.0 s.
* Render it two ways on the same keyframes: the native ``timeremap`` chain and
  the ``segments`` (``timewarp``) engine. Both rendered durations must match the
  5.0 s integral, and each other, within a few frames.
* Sanity: the ramped duration is clearly distinct from the un-ramped 4.0 s.

Skips when the ``timeremap`` link is absent from this melt build.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Link,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import SpeedRamp
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.pipelines import speed_ramp as sr

from ._oracle import probe, render_video

pytestmark = pytest.mark.external

FPS = 25.0
SRC_FRAMES = 100  # 4 s
WIDTH, HEIGHT = 320, 180
VIDEO_TRACK = "playlist_video"

# Two-phase ramp: 2x then 0.5x -> integral is 125 frames (25 + 100).
_KEYFRAMES = [
    {"at_seconds": 0, "speed": 2.0},
    {"at_seconds": 2, "speed": 2.0},
    {"at_seconds": 2, "speed": 0.5},
    {"at_seconds": 4, "speed": 0.5},
]


def _skip_without_timeremap(melt_bin: str) -> None:
    from .conftest import melt_has_service

    if not melt_has_service(melt_bin, "links", "timeremap"):
        pytest.skip("timeremap link not on this melt build")


def _make_source(render_dir: Path) -> Path:
    src = render_dir / "trsrc.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"testsrc=size={WIDTH}x{HEIGHT}:rate={int(FPS)}:duration=4",
            "-pix_fmt", "yuv420p", str(src),
        ],
        capture_output=True, check=True, timeout=60,
    )
    return src


def _footage_project(src: Path) -> KdenliveProject:
    p = KdenliveProject(
        version="7", title="tr",
        profile=ProjectProfile(width=WIDTH, height=HEIGHT, fps=FPS, colorspace="709"),
    )
    p.producers = [
        Producer(
            id="producer_0",
            resource=str(src),
            properties={"resource": str(src), "mlt_service": "avformat", "length": "400"},
        )
    ]
    p.tracks = [Track(id=VIDEO_TRACK, track_type="video", name="V1")]
    p.playlists = [
        Playlist(
            id=VIDEO_TRACK,
            entries=[PlaylistEntry(producer_id="producer_0", in_point=0, out_point=SRC_FRAMES - 1)],
        )
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(SRC_FRAMES - 1)}
    return p


def _apply_timeremap(project: KdenliveProject, segments) -> int:
    """Rewrite the single clip to a timeremap chain; return total output frames."""
    entry = project.playlists[0].entries[0]
    src = project.producers[0]
    speed_map, total = sr.speed_map_from_segments(segments)
    chain = Producer(
        id="chain_tr",
        resource=src.resource,
        properties={"mlt_service": "avformat", "length": str(total)},
        links=[Link(mlt_service="timeremap", properties=sr.timeremap_link_properties(speed_map))],
        chain_out=total - 1,
    )
    project.producers.append(chain)
    entry.producer_id = "chain_tr"
    entry.in_point = 0
    entry.out_point = total - 1
    return total


def test_timeremap_duration_matches_integral_and_segments(
    melt_bin, ffprobe_bin, render_dir: Path
):
    _skip_without_timeremap(melt_bin)
    src = _make_source(render_dir)
    segs = sr.plan_segments(_KEYFRAMES, clip_frames=SRC_FRAMES, fps=FPS, easing="linear")
    expected_frames = sr.total_output_frames(0, segs)
    assert expected_frames == 125  # hand-computed integral
    expected_seconds = expected_frames / FPS
    tol = 3.0 / FPS + 0.02  # a few frames of encoder/link rounding

    # --- native timeremap engine ---
    tr_proj = _footage_project(src)
    tr_total = _apply_timeremap(tr_proj, segs)
    assert tr_total == expected_frames
    tr_path = render_dir / "tr.kdenlive"
    serialize_project(tr_proj, tr_path)
    tr_out = render_video(tr_path, render_dir / "tr.mp4", frames=expected_frames + 40, melt_bin=melt_bin)
    tr_meta = probe(tr_out, ffprobe_bin=ffprobe_bin)
    assert tr_meta.duration is not None
    assert abs(tr_meta.duration - expected_seconds) <= tol, (
        f"timeremap duration {tr_meta.duration}s != integral {expected_seconds}s"
    )

    # --- segments (timewarp) engine on the same keyframes ---
    seg_proj = _footage_project(src)
    seg_proj = patcher.patch_project(
        seg_proj,
        [SpeedRamp(
            track_ref=VIDEO_TRACK, clip_index=0,
            segments=[(s.src_in, s.src_out, s.speed) for s in segs],
        )],
    )
    seg_path = render_dir / "seg.kdenlive"
    serialize_project(seg_proj, seg_path)
    seg_out = render_video(seg_path, render_dir / "seg.mp4", frames=expected_frames + 40, melt_bin=melt_bin)
    seg_meta = probe(seg_out, ffprobe_bin=ffprobe_bin)
    assert seg_meta.duration is not None

    # The two engines agree within a few frames on the same ramp.
    assert abs(tr_meta.duration - seg_meta.duration) <= 4.0 / FPS + 0.02, (
        f"timeremap {tr_meta.duration}s vs segments {seg_meta.duration}s disagree"
    )
    # And both are clearly the ramped 5.0 s, not the un-ramped 4.0 s.
    assert abs(tr_meta.duration - (SRC_FRAMES / FPS)) > 0.5
