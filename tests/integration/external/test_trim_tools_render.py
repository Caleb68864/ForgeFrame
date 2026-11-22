"""Real melt: slip, slide, replace and ripple insert change the right pixels (prompt 20)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import requires_ffmpeg, sequence_project
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import ReplaceClip, RippleInsert, SlideClip, SlipClip
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines.clip_place import clip_start_frame

from . import builders
from ._oracle import audio_stats, mean_color, probe, render_frame, render_video

pytestmark = pytest.mark.external

RED, GREEN, BLUE = builders.RED, builders.GREEN, builders.BLUE


def _dominant(png) -> str:
    r, g, b = mean_color(png)
    if r > 120 and g < 90 and b < 90:
        return "red"
    if g > 120 and r < 90 and b < 90:
        return "green"
    if b > 120 and r < 90 and g < 90:
        return "blue"
    return f"other({r:.0f},{g:.0f},{b:.0f})"


def _frame_colour(project, frame: int, render_dir: Path, name: str, melt_bin: str) -> str:
    path = render_dir / f"{name}.kdenlive"
    serialize_project(project, path)
    return _dominant(render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}_{frame}.png"))


def _duration(project, render_dir: Path, name: str, melt_bin: str, frames: int) -> float:
    path = render_dir / f"{name}.kdenlive"
    serialize_project(project, path)
    out = render_video(path, render_dir / f"{name}.mp4", frames + 25, melt_bin=melt_bin)
    return probe(out).duration


def _rgb_media(tmp_path: Path) -> Path:
    """6 s: red, green, blue 2 s each at 25 fps, with a sine track."""
    out = tmp_path / "rgb.mp4"
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=25:d=2",
        "-f", "lavfi", "-i", "color=c=lime:s=320x180:r=25:d=2",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=25:d=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]",
        "-map", "[v]", "-map", "3:a", "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-shortest", str(out),
    ], check=True, capture_output=True, timeout=120)
    return out


def _media_project(media: Path) -> KdenliveProject:
    project = KdenliveProject(title="slip", profile=ProjectProfile(width=320, height=180, fps=25.0))
    project.producers = [Producer(id="rgb", resource=str(media), properties={
        "resource": str(media), "mlt_service": "avformat", "length": "150"})]
    project.tracks = [Track(id="v1", track_type="video"), Track(id="a1", track_type="audio")]
    entry = PlaylistEntry(producer_id="rgb", in_point=0, out_point=49)  # the red segment
    project.playlists = [Playlist(id="v1", entries=[entry]),
                         Playlist(id="a1", entries=[entry.model_copy()])]
    return project


@requires_ffmpeg
def test_slip_shows_the_next_segment(melt_bin, tmp_path, render_dir):
    project = _media_project(_rgb_media(tmp_path))
    assert _frame_colour(project, 20, render_dir, "slip_before", melt_bin) == "red"
    slipped = patch_project(project, [SlipClip(track_ref="v1", clip_index=0, delta_frames=50, source_frames=150)])
    assert _frame_colour(slipped, 20, render_dir, "slip_after", melt_bin) == "green"
    assert _duration(slipped, render_dir, "slip_dur", melt_bin, 50) == pytest.approx(
        _duration(project, render_dir, "slip_dur0", melt_bin, 50), abs=0.05)


def test_slide_moves_the_cut_points(melt_bin, render_dir):
    project = sequence_project([RED, BLUE, GREEN])
    project = patch_project(project, [SlipClip(track_ref="playlist_video", clip_index=2, delta_frames=5)])
    old_start, old_end = 25, 49
    slid = patch_project(project, [SlideClip(track_ref="playlist_video", clip_index=1, delta_frames=5,
                                             prev_source_frames=35, next_source_frames=35)])
    assert clip_start_frame(slid.playlists[0].entries, 1) == 30
    assert _frame_colour(slid, old_start + 2, render_dir, "slide", melt_bin) == "red"
    assert _frame_colour(slid, old_end + 2, render_dir, "slide", melt_bin) == "blue"
    assert _duration(slid, render_dir, "slide_dur", melt_bin, 75) == pytest.approx(
        _duration(project, render_dir, "slide_dur0", melt_bin, 75), abs=0.05)


def test_replace_renders_the_new_media(melt_bin, render_dir):
    project = sequence_project([RED, BLUE, RED])
    project.producers.append(Producer(id="green_new", resource=GREEN, properties={
        "resource": GREEN, "mlt_service": "color", "length": "40"}))
    replaced = patch_project(project, [ReplaceClip(track_ref="playlist_video", clip_index=1,
                                                   producer_id="green_new", new_has_audio=False)])
    for frame, colour in ((10, "red"), (37, "green"), (60, "red")):
        assert _frame_colour(replaced, frame, render_dir, "replace", melt_bin) == colour
    assert _duration(replaced, render_dir, "rep_dur", melt_bin, 75) == pytest.approx(
        _duration(project, render_dir, "rep_dur0", melt_bin, 75), abs=0.05)


@requires_ffmpeg
def test_ripple_insert_with_audio(melt_bin, tmp_path, render_dir):
    media = _rgb_media(tmp_path)
    project = sequence_project([RED, BLUE])
    project.producers.append(Producer(id="rgb", resource=str(media), properties={
        "resource": str(media), "mlt_service": "avformat", "length": "150"}))
    inserted = patch_project(project, [RippleInsert(track_ref="playlist_video", before_clip_index=1,
                                                    producer_id="rgb", in_point=50, out_point=74)])
    for frame, colour in ((10, "red"), (37, "green"), (60, "blue")):
        assert _frame_colour(inserted, frame, render_dir, "ripple", melt_bin) == colour
    path = render_dir / "ripple_av.kdenlive"
    serialize_project(inserted, path)
    out = render_video(path, render_dir / "ripple_av.mp4", 75, melt_bin=melt_bin)
    assert probe(out).duration == pytest.approx(3.0, abs=0.1)  # 50 + 25 frames
    assert audio_stats(out)["RMS level dB"] > -60
