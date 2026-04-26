"""Smoke test batch 8.0: audio fades, mixes, and other test-suite-driven gaps.

The 025 + 026 outputs are the first to exercise the v25 audio-fade
filter shape (verified against KDE/kdenlive-test-suite/audio-mix.kdenlive).
Future tests in this file cover patterns from the upstream test suite
that the priority backlog called out.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip, AudioFade, CreateTrack
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
# 025 -- audio fade in + fade out on a single clip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_025_audio_fade_in_and_out():
    """One clip with a 2s audio fade-in at the head and 3s fade-out at
    the tail.  Verifies the v25 ``volume`` + ``kdenlive_id=fadein|fadeout``
    filter shape against the KDE test suite.

    For Kdenlive to actually apply the volume fade, the entry carrying
    the fade filter must be on an AUDIO track (V1 video entries have
    no audio routing on their own).  Mirrors the audio-mix.kdenlive
    reference: the same source clip gets an entry on the video track
    AND a separate entry on the audio track, both referencing the
    same producer; the fade filter sits on the audio entry only."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",  # has audio
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip with audio available")

    fps = 29.97
    duration = int(8 * fps)
    fade_in_frames = int(2 * fps)
    fade_out_frames = int(3 * fps)

    project = _build_initial_project("smoke_025_audio_fades", fps=fps)
    # Video portion on V1
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    # Audio portion on A1, referencing the SAME producer.  AddClip would
    # try to create a fresh producer with a new id, so just append the
    # entry directly to the playlist.
    audio_pl = next(p for p in project.playlists if p.id == "playlist_audio")
    audio_pl.entries.append(
        PlaylistEntry(producer_id="vid", in_point=0, out_point=duration - 1)
    )
    # Now the audio fade lands on the A1 entry where Kdenlive's volume
    # filter actually has audio to ramp.
    project = patch_project(
        project,
        [
            AudioFade(
                track_ref="playlist_audio",
                clip_index=0,
                fade_type="in",
                duration_frames=fade_in_frames,
            ),
            AudioFade(
                track_ref="playlist_audio",
                clip_index=0,
                fade_type="out",
                duration_frames=fade_out_frames,
            ),
        ],
    )

    out_path = _output_dir() / "025-audio-fade-in-out.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    # Sanity: the AUDIO entry carries the fade filters, not the video entry.
    audio_entry = next(
        e for pl in project.playlists if pl.id == "playlist_audio"
        for e in pl.entries if e.producer_id
    )
    video_entry = next(
        e for pl in project.playlists if pl.id == "playlist_video"
        for e in pl.entries if e.producer_id
    )
    audio_kdenlive_ids = {f.properties.get("kdenlive_id") for f in audio_entry.filters}
    assert audio_kdenlive_ids == {"fadein", "fadeout"}
    assert video_entry.filters == []


# ---------------------------------------------------------------------------
# 026 -- audio fade-in only (head fade) on a music-bed clip
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_026_audio_fade_in_only():
    """V1 video clip + A2 music-bed clip with a slow 2-second fade-in on
    the music bed.  Mirrors the most common 'fade up the music' pattern."""
    video_clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    music_clip = _resolve_clip(GENERATED_CLIP)
    if video_clip is None or music_clip is None:
        pytest.skip("Required clips missing")

    fps = 29.97
    duration = int(5 * fps)
    project = _build_initial_project("smoke_026_music_fade_in", fps=fps)
    project = patch_project(project, [CreateTrack(track_type="audio", name="A2 Music")])

    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(video_clip),
    )
    project = _add_clip(
        project,
        producer_id="music",
        track_id="playlist_audio_1",
        in_point=0,
        out_point=duration - 1,
        source_path=str(music_clip),
    )
    project = patch_project(
        project,
        [
            AudioFade(
                track_ref="playlist_audio_1",
                clip_index=0,
                fade_type="in",
                duration_frames=int(2 * fps),  # 2-second fade
            ),
        ],
    )

    out_path = _output_dir() / "026-audio-fade-in-music-bed.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
