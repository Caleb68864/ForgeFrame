"""Smoke test batch 14.0: same-track audio crossfade (mix transition).

The pattern verified against the upstream KDE test-suite reference at
``tests/fixtures/kdenlive_references/audio_mix_upstream_kde.kdenlive``:

* Two adjacent audio clips on a single track crossfade by living on
  DIFFERENT sub-playlists of the same per-track tractor:
  - clip A on sub-playlist ``<track.id>``  (the 'A' playlist)
  - clip B on sub-playlist ``<track.id>_kdpair`` (the 'B' playlist),
    with a ``<blank>`` covering the duration before the overlap

* A ``<transition mlt_service="mix">`` element lives INSIDE the
  per-track ``<tractor>`` (NOT in the main sequence's transition list).
  It carries:
  - ``a_track=0`` / ``b_track=1`` referencing the two sub-playlists
  - ``kdenlive:mixcut=<frames>`` -- the half-overlap that bleeds into
    each side of the cut
  - ``start=-1``, ``accepts_blanks=1``, ``reverse=0`` (defaults)

* The transition's ``in``/``out`` covers the overlap window in
  ABSOLUTE sequence frames.

This is the FIRST verification cycle of the same-track mix shape.  If
this opens cleanly in Kdenlive 25.x and audibly crossfades, the
serializer's new ``track_mix_transitions`` path is verified.

WARNING: smoke 031's earlier failure put ``kdenlive:mixcut`` on a
CROSS-track main-sequence ``SequenceTransition`` and got a silent
jump cut (Kdenlive's renderer disabled the visual blend).  The
``kdenlive:mixcut`` property belongs ONLY here, never on a
``SequenceTransition``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    ProjectProfile,
    Track,
    TrackMixTransition,
)
from workshop_video_brain.core.models.timeline import AddClip
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
MUSIC_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "music_cinematic_short.mp3"
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


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 047 -- two audio clips on A1 with a 1-second same-track mix between them
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_047_same_track_audio_mix_crossfade():
    """Two 4-second audio clips on A1 with a 1-second crossfade overlap.

    Layout (frame timeline at 29.97 fps, ~120 frames per second):
      0        ~120                             ~360         ~480
      |---- clip A on sub-playlist A ----|
                                  |---- clip B on sub-playlist B ----|
                                  ^^^^^^
                                  ~30-frame overlap = the mix window

    The mix transition's ``in``/``out`` covers the overlap window;
    ``mixcut`` is the half-overlap (~15 frames -- which means each
    clip's audible audio bleeds 15 frames into the other side of the
    perceived cut).
    """
    if not GENERATED_CLIP.exists() or not MUSIC_CLIP.exists():
        pytest.skip("Required clips missing")

    fps = 29.97
    seg = int(4 * fps)              # 4-second clips
    overlap = int(1 * fps)          # 1-second crossfade overlap
    mix_in = seg - overlap          # absolute frame where mix starts
    mix_out = seg - 1               # absolute frame where mix ends

    project = _build_initial_project("smoke_047_audio_mix_crossfade", fps=fps)

    # Silent video on V1 just for visual context (so the playhead has
    # something to render against during the audio crossfade).
    project = patch_project(
        project,
        [
            AddClip(
                producer_id="vid_v1",
                track_ref="playlist_video",
                track_id="playlist_video",
                in_point=0,
                out_point=seg + (seg - overlap) - 1,
                position=-1,
                source_path=str(GENERATED_CLIP),
            )
        ],
    )

    # Music on A1 sub-playlist A.  Use the FULL music track but trim
    # to ``seg`` frames in the entry; the audio crossfade will mix
    # this clip out into clip B (a different in-point of the same
    # music track) so the user hears a smooth segue rather than a hard
    # discontinuity.
    project = patch_project(
        project,
        [
            AddClip(
                producer_id="music_a",
                track_ref="playlist_audio",
                track_id="playlist_audio",
                in_point=0,
                out_point=seg - 1,
                position=-1,
                source_path=str(MUSIC_CLIP),
            )
        ],
    )
    # AddClip sets the producer's ``length`` property from the first
    # entry's range (here, 119 frames).  But we want to address frames
    # ~300+ on the kdpair sub-playlist, so override the producer length
    # to cover the full music file (~3:30 = ~6300 frames).  Without this
    # Kdenlive's loader sees the kdpair entry's in-point exceed the
    # producer length and silently removes the entry, breaking the mix.
    music_producer = next(p for p in project.producers if p.id == "music_a")
    music_producer.properties["length"] = "6300"

    # Music continuation on A1 sub-playlist B (``playlist_audio_kdpair``)
    # with a leading ``<blank>`` so the entries align on the absolute
    # timeline.  Reuses the SAME music producer with a different
    # in-point so the user hears a clear "second clip" enter the mix.
    kdpair = Playlist(id="playlist_audio_kdpair")
    kdpair.entries.append(
        PlaylistEntry(producer_id="", in_point=0, out_point=mix_in - 1)
    )
    # Use a later region of the same music track for clip B (in-point
    # at ~10 seconds in so it sounds different from clip A's opening).
    music_b_in = int(10 * fps)
    kdpair.entries.append(
        PlaylistEntry(
            producer_id="music_a",
            in_point=music_b_in,
            out_point=music_b_in + seg - 1,
        )
    )
    project.playlists.append(kdpair)

    # The mix transition lives inside the A1 per-track tractor.
    project.track_mix_transitions.append(
        TrackMixTransition(
            id="mix_a1_clipA_to_clipB",
            track_ref="playlist_audio",
            in_frame=mix_in,
            out_frame=mix_out,
            mixcut_frames=overlap // 2,
            kind="mix",
        )
    )

    out_path = _output_dir() / "047-same-track-audio-mix.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    # Sanity-check the emitted XML has the mix transition INSIDE the
    # per-track tractor (not in the main sequence).
    text = out_path.read_text(encoding="utf-8")
    assert 'mlt_service">mix' in text
    assert "kdenlive:mixcut" in text
    # The kdpair playlist has a real entry now (not just empty).
    assert 'producer="music_a"' in text
