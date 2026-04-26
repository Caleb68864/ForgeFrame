"""Smoke test batch 9.0: avfilter, video fade-to-black, effect zones.

Hits three high-leverage gaps the test-suite coverage audit identified:

* **Generic avfilter EntryFilter shape** -- one ``mlt_service=avfilter.X``
  branch unblocks ~30 of the 59 KDE-test-suite ``avfilter-*.kdenlive``
  files (blur, colour grade, edge detect, etc.).
* **Native video fade-to-black** -- mirror of the audio fade pattern,
  using ``mlt_service=brightness`` + ``kdenlive_id=fade_to_black``
  with the same scalar ``level`` ramp and entry-local ``in``/``out``.
* **Effect zones** -- ``kdenlive:zone_in`` / ``kdenlive:zone_out``
  properties on a ``<filter>`` scope an effect to a sub-range of the
  clip (``effect-zones.kdenlive``).

These smokes build EntryFilters directly to avoid going through the
opaque-emission patcher path that the existing effect-stack tooling
still relies on; that bigger refactor is captured in the audit's
priority backlog.
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
from workshop_video_brain.core.models.timeline import AddClip
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


def _frames_to_timecode(frame: int, fps: float) -> str:
    seconds = frame / fps
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s_total = seconds - h * 3600 - m * 60
    s_int = int(s_total)
    ms = int(round((s_total - s_int) * 1000))
    if ms >= 1000:
        ms = 999
    return f"{h:02d}:{m:02d}:{s_int:02d}.{ms:03d}"


# ---------------------------------------------------------------------------
# 027 -- avfilter.gblur via direct EntryFilter
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_027_avfilter_gblur_keyframed():
    """Animated gaussian blur via the generic avfilter shape: starts
    sharp (sigma=0), ramps to heavy blur (sigma=20) over the clip.

    This is the same XML shape every ``avfilter-*.kdenlive`` in the KDE
    test suite uses, with only the service name and parameter set
    varying."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(5 * fps)
    project = _build_initial_project("smoke_027_avfilter_gblur", fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    # Two keyframes (entry-local time, same syntax as qtblend rect):
    #   00:00:00.000 -> sigma 0  (sharp)
    #   <last>      -> sigma 20 (heavy blur)
    sigma_keyframes = (
        f"{_frames_to_timecode(0, fps)}=0;"
        f"{_frames_to_timecode(duration - 1, fps)}=20"
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    entry = pl.entries[0]
    entry.filters.append(
        EntryFilter(
            id="avfilter_gblur",
            properties={
                "mlt_service": "avfilter.gblur",
                "kdenlive_id": "avfilter.gblur",
                "av.sigma": sigma_keyframes,
                "kdenlive:collapsed": "0",
            },
        )
    )

    out_path = _output_dir() / "027-avfilter-gblur.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 028 -- native video fade-from-black at start, fade-to-black at end
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_028_video_fade_from_to_black():
    """Video fade-from-black + fade-to-black via the v25 ``brightness``
    filter shape verified against the user's hand-saved
    ``06-fade to and from black.kdenlive`` (now under
    ``tests/fixtures/kdenlive_references/video_fade_black_native.kdenlive``).

    Critical contract details that differ from the obvious-from-the-audio-
    fade-pattern shape:

    1. ``level`` is the keyframe-string ``"00:00:00.000=0;<dur>=1"``
       (NOT ``alpha`` like a transparency ramp).
    2. ``alpha`` is the scalar ``"1"`` -- a constant, not a keyframe.
    3. ``start=1`` -- the property the UI's "Fade from Black" /
       "Fade to Black" toggle reads.  Without it the checkbox shows
       unchecked even though the filter would still ramp brightness.
    4. ``level`` keyframe times are FILTER-LOCAL (start at
       ``00:00:00.000`` regardless of where the filter window sits in
       the entry), NOT entry-local.  The filter's ``in``/``out``
       attributes position the window inside the entry.
    """
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(8 * fps)              # 8-second clip so the fades have room
    fade_in_frames = int(2.0 * fps)      # 2-second fade-up from black
    fade_out_frames = int(3.0 * fps)     # 3-second fade-down to black

    project = _build_initial_project("smoke_028_video_fades", fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    entry = pl.entries[0]

    # Fade-from-black at the head.  Filter window: [0, fade_in_frames-1].
    # Keyframe times are FILTER-LOCAL: start at 00:00:00.000 + ramp 0->1.
    entry.filters.append(
        EntryFilter(
            id="fade_from_black",
            in_frame=0,
            out_frame=fade_in_frames - 1,
            properties={
                "start": "1",
                "level":
                    f"{_frames_to_timecode(0, fps)}=0;"
                    f"{_frames_to_timecode(fade_in_frames - 1, fps)}=1",
                "mlt_service": "brightness",
                "kdenlive_id": "fade_from_black",
                "alpha": "1",
                "kdenlive:collapsed": "0",
            },
        )
    )
    # Fade-to-black at the tail.  Filter window:
    # [duration - fade_out_frames, duration - 1].  Keyframes again
    # filter-local: 00:00:00.000=1 -> <window-end-relative>=0.
    entry.filters.append(
        EntryFilter(
            id="fade_to_black",
            in_frame=duration - fade_out_frames,
            out_frame=duration - 1,
            properties={
                "start": "1",
                "level":
                    f"{_frames_to_timecode(0, fps)}=1;"
                    f"{_frames_to_timecode(fade_out_frames - 1, fps)}=0",
                "mlt_service": "brightness",
                "kdenlive_id": "fade_to_black",
                "alpha": "1",
                "kdenlive:collapsed": "0",
            },
        )
    )

    out_path = _output_dir() / "028-video-fade-from-to-black.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 029 -- effect zone (filter active only in a sub-range of the clip)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_030_lift_gamma_gain_three_way_grade():
    """3-way colour grading via the ``lift_gamma_gain`` MLT effect.
    Nine scalar params (lift_r/g/b, gamma_r/g/b, gain_r/g/b).  Pattern
    from ``mlt-plus-video-effects.kdenlive`` in the KDE test suite."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(5 * fps)
    project = _build_initial_project("smoke_030_three_way_grade", fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    entry = pl.entries[0]
    # Push shadows cool (negative blue lift), gamma neutral, lift highlights
    # warm (positive red gain).  Subtle teal-and-orange grade.
    entry.filters.append(
        EntryFilter(
            id="lift_gamma_gain",
            properties={
                "mlt_service": "lift_gamma_gain",
                "kdenlive_id": "lift_gamma_gain",
                "lift_r": "0.50",  "lift_g": "0.50",  "lift_b": "0.55",  # cool shadows
                "gamma_r": "0.50", "gamma_g": "0.50", "gamma_b": "0.50",  # neutral mids
                "gain_r": "0.55",  "gain_g": "0.50",  "gain_b": "0.45",  # warm highlights
                "kdenlive:collapsed": "0",
            },
        )
    )
    out_path = _output_dir() / "030-three-way-color-grade.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_031_dissolve_with_mixcut_property():
    """Cross-dissolve carrying the ``kdenlive:mixcut=12`` property the
    KDE test suite uses on every user-placed luma transition.  Same
    SequenceTransition shape as smoke 004 but with the extra property."""
    from workshop_video_brain.core.models.kdenlive import SequenceTransition
    from workshop_video_brain.core.models.timeline import CreateTrack

    clip_a = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    clip_b = _resolve_clip(
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    )
    if not (clip_a and clip_b):
        pytest.skip("Need two clips")

    fps = 29.97
    seg = int(3 * fps)
    overlap = int(1 * fps)
    project = _build_initial_project("smoke_031_dissolve_mixcut", fps=fps)
    project = patch_project(project, [CreateTrack(track_type="video", name="V2")])

    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=seg - 1,
        source_path=str(clip_a),
    )
    pl_b = next(p for p in project.playlists if p.id == "playlist_video_1")
    pl_b.entries.append(PlaylistEntry(producer_id="", in_point=0, out_point=seg - overlap - 1))
    project = _add_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video_1",
        in_point=0,
        out_point=seg - 1,
        source_path=str(clip_b),
    )

    project.sequence_transitions.append(
        SequenceTransition(
            id="dissolve_with_mixcut",
            a_track=1,        # V1 ordinal
            b_track=3,        # V2 ordinal (after A1 at 2)
            in_frame=seg - overlap,
            out_frame=seg - 1,
            mlt_service="luma",
            kdenlive_id="dissolve",
            properties={
                "factory": "loader",
                "resource": "",
                "softness": "0",
                "reverse": "0",
                "alpha_over": "1",
                "fix_background_alpha": "1",
                "kdenlive:mixcut": "12",  # the property the test suite always carries
            },
        )
    )

    out_path = _output_dir() / "031-dissolve-with-mixcut.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_029_effect_zone_scoped_brightness():
    """Demonstrates ``kdenlive:zone_in`` / ``kdenlive:zone_out`` -- the
    brightness boost only takes effect for a sub-range of the clip
    (frames 30..89), the rest plays normally.  Pattern from
    ``effect-zones.kdenlive`` in the KDE test suite."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    duration = int(4 * fps)  # ~120 frames

    project = _build_initial_project("smoke_029_effect_zones", fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=duration - 1,
        source_path=str(clip),
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    entry = pl.entries[0]
    entry.filters.append(
        EntryFilter(
            id="brightness_zone",
            zone_in_frame=30,    # frame 30 of the clip
            zone_out_frame=89,   # frame 89 of the clip
            properties={
                "mlt_service": "brightness",
                "kdenlive_id": "brightness",
                "level": "1.4",
                "kdenlive:collapsed": "0",
            },
        )
    )

    out_path = _output_dir() / "029-effect-zone-brightness.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
