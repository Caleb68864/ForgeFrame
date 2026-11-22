"""Real melt: the sound stays with the picture after every clip edit.

Each A/V clip is a video entry plus an audio entry (prompt 02). These edits
used to change only the video track: TrimClip, RemoveClip, RippleDelete,
MoveClip, SplitClip, InsertGap, and a PlaceClip insert put silence under the
new clip. Each test renders the edited timeline and checks that, at frames
where the old behaviour would drift, the colour and the tone name the same
source segment (red/300 Hz, green/600, blue/900, white/1200).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import requires_ffmpeg
from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject, Playlist, PlaylistEntry, Producer, ProjectProfile, Track,
)
from workshop_video_brain.core.models.timeline import (
    InsertGap, MoveClip, PlaceClip, RemoveClip, RippleDelete, SplitClip, TrimClip,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

from . import _av_sync as av
from ._oracle import render_video

pytestmark = [pytest.mark.external, requires_ffmpeg]


@pytest.fixture(scope="module")
def media(tmp_path_factory) -> Path:
    return av.make_media(tmp_path_factory.mktemp("avmedia") / "segments.mp4")


def _project(media: Path) -> KdenliveProject:
    """Red, green, blue A/V clips (source frames 0-49, 50-99, 100-149) on V1 + A1."""
    p = KdenliveProject(title="sync", profile=ProjectProfile(width=320, height=180, fps=25.0))
    p.producers = [Producer(id="seg", resource=str(media), properties={
        "resource": str(media), "mlt_service": "avformat", "length": "200"})]
    p.tracks = [Track(id="v1", track_type="video"), Track(id="a1", track_type="audio")]
    clips = [PlaylistEntry(producer_id="seg", in_point=a, out_point=a + 49) for a in (0, 50, 100)]
    p.playlists = [Playlist(id="v1", entries=[c.model_copy() for c in clips]),
                   Playlist(id="a1", entries=[c.model_copy() for c in clips])]
    return p


def _check(project, frames_and_colours, render_dir: Path, name: str, melt_bin: str, total: int):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(project, path)
    video = render_video(path, render_dir / f"{name}.mp4", total, melt_bin=melt_bin)
    for frame, colour in frames_and_colours:
        got = av.av_at(video, frame, render_dir)
        assert got == av.segment(colour), f"{name} frame {frame}: picture/sound {got}, expected {av.segment(colour)}"


def test_remove_clip_removes_its_sound(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [RemoveClip(track_ref="v1", clip_index=1)])
    _check(edited, [(60, "blue")], render_dir, "remove", melt_bin, 100)


def test_ripple_delete_keeps_sync(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [RippleDelete(track_ref="v1", clip_index=0)])
    _check(edited, [(10, "green"), (60, "blue")], render_dir, "ripple", melt_bin, 100)


def test_trim_shortens_the_sound_too(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [TrimClip(clip_ref="v1:0", new_in=-1, new_out=24)])
    _check(edited, [(30, "green"), (80, "blue")], render_dir, "trim", melt_bin, 125)


def test_move_takes_the_sound_along(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [MoveClip(track_ref="v1", from_index=0, to_index=2)])
    _check(edited, [(10, "green"), (110, "red")], render_dir, "move", melt_bin, 150)


def test_split_then_remove_the_second_half(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [SplitClip(track_ref="v1", clip_index=0, split_at_frame=20),
                                            RemoveClip(track_ref="v1", clip_index=1)])
    _check(edited, [(10, "red"), (30, "green")], render_dir, "split", melt_bin, 120)


def test_insert_gap_shifts_the_sound(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [InsertGap(track_id="v1", position=1, duration_frames=25)])
    _check(edited, [(110, "green"), (140, "blue")], render_dir, "gap", melt_bin, 175)


def test_place_clip_insert_brings_its_sound(media, melt_bin, render_dir):
    edited = patch_project(_project(media), [PlaceClip(
        track_ref="v1", producer_id="seg", in_point=150, out_point=174, at_frame=50, mode="insert",
        ripple_all_tracks=True, with_audio=True)])
    _check(edited, [(60, "white"), (80, "green")], render_dir, "place", melt_bin, 175)
