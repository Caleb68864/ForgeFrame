"""Smoke test batch 7.0: timeline editing primitives (split / trim / move / ripple) + PIP.

Covers the daily-use timeline operations that mutate ``project.playlists``
directly through patcher intents (no opaque-element rewrites).  Each test
drops a separate ``.kdenlive`` into the local Kdenlive test folder.

Order:
- 018 clip-split: split a clip mid-frame; both halves on V1.
- 019 clip-trim: clip with adjusted out_point via ``TrimClip``.
- 020 clip-move: clip moved from position 0 to position 2 in same track.
- 021 ripple-delete: remove the middle clip of three (gap auto-closes).
- 022 composite-pip: webcam-style PIP -- main clip on V1, small clip in
  bottom-right corner on V2 via a static ``qtblend`` rect.
- 023 clip-speed: clip at 2x speed via ``SetClipSpeed`` -- this currently
  emits an opaque ``<filter>`` at document root (NOT inside the entry),
  so Kdenlive may render the clip at normal speed.  Verifies whether the
  existing patcher path works for v25 or needs rework.

Skipped for follow-up:
- track_mute / track_visibility -- the patcher emits these as opaque
  ``<property>`` fragments at document root, but Kdenlive expects them
  on the per-track tractor.  Needs model + serializer changes (e.g. a
  ``Track.muted`` field that the serializer writes inside the track's
  tractor element).
- audio_fade -- same opaque-fragment problem.
- composite_set blend modes -- in Kdenlive these set properties on the
  auto-internal ``qtblend`` track transition, which our serializer
  rebuilds from scratch on every save.  Needs serializer to accept
  per-track-transition overrides.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    EntryFilter,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import (
    AddClip,
    CreateTrack,
    MoveClip,
    RippleDelete,
    SetClipSpeed,
    SplitClip,
    TrimClip,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")
REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"


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
    intent = AddClip(
        producer_id=producer_id,
        track_ref=track_id,
        track_id=track_id,
        in_point=in_point,
        out_point=out_point,
        position=-1,
        source_path=source_path,
    )
    return patch_project(project, [intent])


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 018 -- clip_split: split a clip mid-frame, both halves on V1
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_018_clip_split():
    """Place a clip on V1, then split it at the midpoint via ``SplitClip``.
    The serialized playlist should have two consecutive entries pointing
    at the same producer with adjacent in/out frames."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    full_frames = int(6 * fps)
    project = _build_initial_project("smoke_018_clip_split", fps=fps)
    project = _add_clip(
        project,
        producer_id="clip_full",
        track_id="playlist_video",
        in_point=0,
        out_point=full_frames - 1,
        source_path=str(clip),
    )
    # Split at the midpoint (frame 89 within the clip).
    split_at = full_frames // 2
    project = patch_project(
        project,
        [SplitClip(track_ref="playlist_video", clip_index=0, split_at_frame=split_at)],
    )

    out_path = _output_dir() / "018-clip-split.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
    # The playlist should now have two real entries
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    real_entries = [e for e in pl.entries if e.producer_id]
    assert len(real_entries) == 2


# ---------------------------------------------------------------------------
# 019 -- clip_trim: shorten a clip by adjusting its out_point
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_019_clip_trim():
    """Place a 6-second clip, trim 2 seconds off the tail via ``TrimClip``."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    full_frames = int(6 * fps)
    keep_frames = int(4 * fps)
    project = _build_initial_project("smoke_019_clip_trim", fps=fps)
    project = _add_clip(
        project,
        producer_id="clip_full",
        track_id="playlist_video",
        in_point=0,
        out_point=full_frames - 1,
        source_path=str(clip),
    )
    # Trim: keep frames 0..(keep_frames-1), drop the rest.  ``clip_ref``
    # is "<playlist_id>:<index>" or just the bare index.
    project = patch_project(
        project,
        [
            TrimClip(
                clip_ref="playlist_video:0",
                new_in=0,
                new_out=keep_frames - 1,
            )
        ],
    )
    out_path = _output_dir() / "019-clip-trim.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    assert pl.entries[0].out_point == keep_frames - 1


# ---------------------------------------------------------------------------
# 020 -- clip_move: move clip from index 0 to index 2 within same track
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_020_clip_move():
    """Three clips A B C on V1; move A to the end so the order becomes B C A."""
    clip_a = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    clip_b = _resolve_clip(
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    )
    clip_c = _resolve_clip(
        USER_TEST_KDENLIVE / "9341428-uhd_3840_2160_24fps.mp4",
        GENERATED_CLIP,
    )
    if not (clip_a and clip_b and clip_c):
        pytest.skip("Need three clips")

    fps = 29.97
    seg = int(2 * fps)
    project = _build_initial_project("smoke_020_clip_move", fps=fps)
    for pid, p in [("a", clip_a), ("b", clip_b), ("c", clip_c)]:
        project = _add_clip(
            project,
            producer_id=f"clip_{pid}",
            track_id="playlist_video",
            in_point=0,
            out_point=seg - 1,
            source_path=str(p),
        )
    # Move clip at index 0 (A) to the end (index 2).
    project = patch_project(
        project,
        [MoveClip(track_ref="playlist_video", from_index=0, to_index=2)],
    )

    out_path = _output_dir() / "020-clip-move.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    real = [e for e in pl.entries if e.producer_id]
    assert [e.producer_id for e in real] == ["clip_b", "clip_c", "clip_a"]


# ---------------------------------------------------------------------------
# 021 -- ripple_delete: remove middle clip; the gap auto-closes
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_021_ripple_delete():
    """Three clips A B C on V1; ripple-delete B so the timeline is A C with no gap."""
    clip_a = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    clip_b = _resolve_clip(
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    )
    clip_c = _resolve_clip(
        USER_TEST_KDENLIVE / "9341428-uhd_3840_2160_24fps.mp4",
        GENERATED_CLIP,
    )
    if not (clip_a and clip_b and clip_c):
        pytest.skip("Need three clips")

    fps = 29.97
    seg = int(2 * fps)
    project = _build_initial_project("smoke_021_ripple_delete", fps=fps)
    for pid, p in [("a", clip_a), ("b", clip_b), ("c", clip_c)]:
        project = _add_clip(
            project,
            producer_id=f"clip_{pid}",
            track_id="playlist_video",
            in_point=0,
            out_point=seg - 1,
            source_path=str(p),
        )
    # Ripple-delete the middle clip (index 1).
    project = patch_project(
        project,
        [RippleDelete(track_ref="playlist_video", clip_index=1)],
    )

    out_path = _output_dir() / "021-ripple-delete.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    real = [e for e in pl.entries if e.producer_id]
    assert [e.producer_id for e in real] == ["clip_a", "clip_c"]


# ---------------------------------------------------------------------------
# 022 -- composite_pip: webcam-style PIP in bottom-right corner
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_022_composite_pip():
    """V1 = full-canvas main clip; V2 = small clip scaled to a 480x270 thumbnail
    in the bottom-right corner via a static ``qtblend`` rect.  This is the
    XML pattern Kdenlive uses for picture-in-picture."""
    main_clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    pip_clip = _resolve_clip(
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    )
    if not (main_clip and pip_clip):
        pytest.skip("Need two clips")

    fps = 29.97
    duration = int(5 * fps)
    project = _build_initial_project("smoke_022_composite_pip", fps=fps)
    # Add V2 for the PIP overlay.
    project = patch_project(project, [CreateTrack(track_type="video", name="V2 PIP")])

    # V1: main clip
    project = _add_clip(
        project,
        producer_id="main",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(main_clip),
    )
    # V2: PIP clip
    project = _add_clip(
        project,
        producer_id="pip",
        track_id="playlist_video_1",
        in_point=0,
        out_point=duration - 1,
        source_path=str(pip_clip),
    )

    # Find the PIP entry and attach a static qtblend rect that scales it to
    # 480x270 and positions it in the bottom-right corner with a 32-pixel
    # margin.  Canvas is 1920x1080.
    canvas_w, canvas_h = 1920, 1080
    pip_w, pip_h = 480, 270
    margin = 32
    pip_x = canvas_w - pip_w - margin
    pip_y = canvas_h - pip_h - margin
    rect_str = f"00:00:00.000={pip_x} {pip_y} {pip_w} {pip_h} 1.000000"

    pip_pl = next(p for p in project.playlists if p.id == "playlist_video_1")
    pip_entry = next(e for e in pip_pl.entries if e.producer_id == "pip")
    pip_entry.filters.append(
        EntryFilter(
            properties={
                "rotate_center": "1",
                "mlt_service": "qtblend",
                "kdenlive_id": "qtblend",
                "compositing": "0",
                "distort": "0",
                "rect": rect_str,
                "rotation": "00:00:00.000=0",
                "kdenlive:collapsed": "0",
            }
        )
    )

    out_path = _output_dir() / "022-composite-pip.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 023 -- clip_speed: 2x playback via SetClipSpeed
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_023_clip_speed_via_intent():
    """Apply ``SetClipSpeed`` with speed=4.0 to a clip on V1.

    Uses the largest UHD source so any motion is obvious if speed kicks in.

    NOTE: the current patcher emits this as an opaque ``<filter type="speed">``
    at document root level (not inside the playlist ``<entry>`` and not in
    MLT's expected ``mlt_service=timewarp`` chain form).  Kdenlive 25.x
    ignores the opaque fragment entirely and plays the clip at 1x.  Verified
    with this smoke: the timeline duration matches a 1x clip and visual
    speed is normal.

    To make speed actually work we need a v25-shape reference (Kdenlive
    save with one speed-changed clip) and then:
      * either replace the timeline producer reference with a ``timewarp``
        chain whose ``resource`` is ``"<speed>:<original_path>"`` and whose
        properties include ``warp_speed`` / ``warp_pitch`` /
        ``warp_resource`` / ``kdenlive:original.length``,
      * or insert a ``<filter mlt_service="timeremap">`` inside the
        playlist entry with a remap curve.

    This smoke is left in to document the broken behaviour and as a
    target for the fix; ask the user to save a hand-made example so we
    have a concrete diff target.
    """
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",  # most motion
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(4 * fps)
    project = _build_initial_project("smoke_023_clip_speed", fps=fps)
    project = _add_clip(
        project,
        producer_id="clip",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    project = patch_project(
        project,
        [SetClipSpeed(track_ref="playlist_video", clip_index=0, speed=4.0)],
    )

    out_path = _output_dir() / "023-clip-speed.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
