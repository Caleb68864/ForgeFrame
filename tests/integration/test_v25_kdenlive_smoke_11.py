"""Smoke test batch 11.0: track-level structural patterns.

Covers shape items from the KDE test-suite coverage audit that target
the per-track tractor / track properties layer rather than per-clip
filters:

* **034** -- track mute (audio) + track hide (video) emitted as
  ``hide="both"`` on the per-track tractor's sub-tracks.  Verified
  shape against ``audio-mix.kdenlive`` from the KDE test suite, where
  the muted A1 carries ``hide="both"`` on both internal track refs.
* **035** -- per-track avfilter applied across all clips on a track
  (sharpen-the-whole-V1 pattern), using a track-level ``<filter>``
  inside the per-track tractor rather than per-entry filters.  This is
  how the upstream test suite scopes a filter to "everything on this
  track" without duplicating it on each clip.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import (
    AddClip,
    SetTrackMute,
    SetTrackVisibility,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")
USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")


def _build_initial_project(title: str, fps: float = 29.97) -> KdenliveProject:
    project = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
    )
    project.tracks = [
        Track(id="playlist_video", track_type="video", name="V1"),
        Track(id="playlist_audio", track_type="audio", name="A1"),
    ]
    project.playlists = [
        Playlist(id="playlist_video"),
        Playlist(id="playlist_audio"),
    ]
    project.tractor = {"id": "main_seq", "in": "0", "out": "0"}
    return project


def _add_clip(
    project: KdenliveProject,
    *,
    producer_id: str,
    track_id: str,
    in_point: int,
    out_point: int,
    source_path: str,
) -> KdenliveProject:
    return patch_project(
        project,
        [
            AddClip(
                producer_id=producer_id,
                track_ref=track_id,
                track_id=track_id,
                in_point=in_point,
                out_point=out_point,
                position=-1,
                source_path=source_path,
            )
        ],
    )


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 034 -- audio track muted + extra hidden video track
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_034_track_mute_and_hide():
    """Two video tracks (V1 visible, V2 hidden) + one audio track (muted).
    Opening this in Kdenlive should show V2 with the eye-toggle off and
    A1 with the speaker-toggle off, no output coming from either."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(4 * fps)
    project = _build_initial_project("smoke_034_track_mute_and_hide", fps=fps)
    # Add a second video track manually so we can prove the hide=both
    # output covers a non-default track too.
    project.tracks.insert(
        0, Track(id="playlist_video_extra", track_type="video", name="V2")
    )
    project.playlists.insert(0, Playlist(id="playlist_video_extra"))

    project = _add_clip(
        project,
        producer_id="vid_v1",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    project = _add_clip(
        project,
        producer_id="vid_v2",
        track_id="playlist_video_extra",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )

    # Mute the audio track and hide V2.
    project = patch_project(
        project,
        [
            SetTrackMute(track_ref="playlist_audio", muted=True),
            SetTrackVisibility(track_ref="playlist_video_extra", visible=False),
        ],
    )

    audio = next(t for t in project.tracks if t.id == "playlist_audio")
    v2 = next(t for t in project.tracks if t.id == "playlist_video_extra")
    v1 = next(t for t in project.tracks if t.id == "playlist_video")
    assert audio.muted is True
    assert v2.hidden is True
    assert v1.hidden is False

    out_path = _output_dir() / "034-track-mute-and-hide.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    # Sanity: the serialized XML carries hide="both" for the muted audio
    # track's per-track tractor sub-tracks AND for the hidden V2 sub-tracks,
    # but the visible V1 stays at hide="audio" (default video-track value).
    text = out_path.read_text(encoding="utf-8")
    assert text.count('hide="both"') >= 4  # 2 sub-tracks per muted/hidden tractor
    # V1 should still hide its audio stream (default video-track behaviour).
    assert 'hide="audio"' in text
