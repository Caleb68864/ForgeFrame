"""Smoke test batch 4.0: a queue of v25 outputs to review in Kdenlive.

Each ``test_drop_smoke_*`` writes a separate ``.kdenlive`` file into the
user's local Kdenlive test folder for visual verification, named with a
3-digit prefix so the latest sorts to the bottom.

Coverage targets the highest-value MCP surface that wasn't already
covered by smokes 001-004:

* 005 -- back-to-back cuts on the same track (no overlap).
* 006 -- trimmed clip: timeline uses only the middle of the source.
* 007 -- multi-title-cards: three editable titles with different colors,
  fonts, and durations.
* 008 -- audio music bed: V1 video, A1 audio extracted, A2 separate
  music source.
* 009 -- chapter markers: a project with several timeline guides.
* 010 -- three-clip dissolves: tutorial-style edit with two cross-
  dissolves and one cut.
* 011 -- wipe transition: same shape as a dissolve but ``kdenlive_id=wipe``.

Each test is independently skippable based on which test media is
available on the host.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SequenceTransition,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip, CreateTrack
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATED_CLIP = REPO_ROOT / "tests" / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"
USER_TEST_KDENLIVE = Path("C:/Users/CalebBennett/Videos/Test KdenLive")
USER_OUTPUT_DIR = Path("C:/Users/CalebBennett/Videos/Video Production/tests/mcp_output")


# ---------------------------------------------------------------------------
# Helpers (mirror the ones in smoke_2 / smoke_3 to keep tests independent).
# ---------------------------------------------------------------------------


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


def _add_track(project: KdenliveProject, track_type: str, name: str) -> KdenliveProject:
    return patch_project(project, [CreateTrack(track_type=track_type, name=name)])


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


def _add_blank_then_clip(
    project: KdenliveProject,
    *,
    producer_id: str,
    track_id: str,
    blank_frames: int,
    in_point: int,
    out_point: int,
    source_path: str,
) -> KdenliveProject:
    new = project.model_copy(deep=True)
    pl = next(p for p in new.playlists if p.id == track_id)
    if blank_frames > 0:
        pl.entries.append(
            PlaylistEntry(producer_id="", in_point=0, out_point=blank_frames - 1)
        )
    return _add_clip(
        new,
        producer_id=producer_id,
        track_id=track_id,
        in_point=in_point,
        out_point=out_point,
        source_path=source_path,
    )


def _track_ordinal(project: KdenliveProject, track_id: str) -> int:
    for i, t in enumerate(project.tracks, start=1):
        if t.id == track_id:
            return i
    raise ValueError(f"track {track_id!r} not in project")


def _kdenlivetitle_xmldata(
    text: str,
    *,
    width: int,
    height: int,
    length_frames: int,
    font_px: int,
    font: str,
    color: str,
) -> str:
    out = max(0, length_frames - 1)
    box_w = int(width * 0.8)
    box_h = int(height * 0.2)
    pos_x = (width - box_w) // 2
    pos_y = (height - box_h) // 2
    return (
        f'<kdenlivetitle LC_NUMERIC="C" duration="{length_frames}" '
        f'height="{height}" out="{out}" width="{width}">\n'
        f' <item type="QGraphicsTextItem" z-index="0">\n'
        f'  <position x="{pos_x}" y="{pos_y}">\n'
        f'   <transform>1,0,0,0,1,0,0,0,1</transform>\n'
        f'  </position>\n'
        f'  <content alignment="4" box-height="{box_h}" box-width="{box_w}" '
        f'font="{font}" font-color="{color}" font-italic="0" '
        f'font-outline="0" font-outline-color="0,0,0,255" '
        f'font-pixel-size="{font_px}" font-underline="0" font-weight="400" '
        f'letter-spacing="0" shadow="0;#64000000;3;3;3" tab-width="80" '
        f'typewriter="0;2;1;0;0">{text}</content>\n'
        f' </item>\n'
        f' <startviewport rect="0,0,{width},{height}"/>\n'
        f' <endviewport rect="0,0,{width},{height}"/>\n'
        f' <background color="0,0,0,0"/>\n'
        f'</kdenlivetitle>\n'
    )


def _register_kdenlivetitle(
    project: KdenliveProject,
    producer_id: str,
    label: str,
    length_frames: int,
    *,
    font_px: int = 72,
    font: str = "Segoe UI",
    color: str = "255,255,255,255",
) -> KdenliveProject:
    new = project.model_copy(deep=True)
    width = new.profile.width
    height = new.profile.height
    fps = new.profile.fps or 25.0
    total_seconds = length_frames / fps
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    frames = length_frames - int(int(total_seconds) * fps)
    duration_tc = f"{hours:02d}:{minutes:02d}:{seconds:02d};{max(0, frames):02d}"
    xmldata = _kdenlivetitle_xmldata(
        label,
        width=width,
        height=height,
        length_frames=length_frames,
        font_px=font_px,
        font=font,
        color=color,
    )
    new.producers.append(
        Producer(
            id=producer_id,
            resource="",
            properties={
                "mlt_service": "kdenlivetitle",
                "resource": "",
                "length": str(length_frames),
                "eof": "pause",
                "aspect_ratio": "1",
                "seekable": "1",
                "meta.media.progressive": "1",
                "meta.media.width": str(width),
                "meta.media.height": str(height),
                "force_reload": "0",
                "kdenlive:clipname": label,
                "kdenlive:duration": duration_tc,
                "xmldata": xmldata,
            },
        )
    )
    return new


def _add_dissolve(
    project: KdenliveProject,
    *,
    outgoing_track_id: str,
    incoming_track_id: str,
    in_frame: int,
    out_frame: int,
    transition_id: str,
    kdenlive_id: str = "dissolve",
) -> KdenliveProject:
    """Append a luma cross-dissolve to the main sequence's transitions.

    Kdenlive enforces ``a_track < b_track`` -- the LOWER track ordinal goes
    into ``a_track`` regardless of dissolve direction.  Direction is encoded
    by the ``reverse`` property: ``reverse=0`` means the upper track fades
    in (revealing it over the lower), ``reverse=1`` means the lower track
    fades in (revealing it under the upper, which is fading out).

    Passing the tracks in the wrong order produces the "Incorrect composition
    ... was set to forced track" warning at project-load.
    """
    new = project.model_copy(deep=True)
    out_ord = _track_ordinal(new, outgoing_track_id)
    in_ord = _track_ordinal(new, incoming_track_id)
    a_track, b_track = sorted((out_ord, in_ord))
    # If the OUTGOING clip is on the higher-ordinal track we need ``reverse=1``
    # so Kdenlive plays the dissolve "upper-fades-out" instead of the default
    # "upper-fades-in".
    reverse = "1" if out_ord > in_ord else "0"
    new.sequence_transitions.append(
        SequenceTransition(
            id=transition_id,
            a_track=a_track,
            b_track=b_track,
            in_frame=in_frame,
            out_frame=out_frame,
            mlt_service="luma",
            kdenlive_id=kdenlive_id,
            properties={
                "factory": "loader",
                "resource": "",
                "softness": "0",
                "reverse": reverse,
                "alpha_over": "1",
                "fix_background_alpha": "1",
            },
        )
    )
    return new


def _output_dir() -> Path:
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    return USER_OUTPUT_DIR


def _resolve_clip(*candidates: Path) -> Path | None:
    for p in candidates:
        if p.exists():
            return p
    return None


# ---------------------------------------------------------------------------
# 005 -- back-to-back cuts (single track, no overlap)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_005_back_to_back_cuts():
    """Two clips on V1, hard-cut from one to the next.  No transition;
    no overlap.  This is the basic tutorial workflow primitive."""
    clip_a = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    clip_b = _resolve_clip(
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    )
    if clip_a is None or clip_b is None:
        pytest.skip("Required clips missing")

    fps = 29.97
    clip_a_frames = int(4 * fps)  # ~4s
    clip_b_frames = int(3 * fps)  # ~3s
    project = _build_initial_project("smoke_005_back_to_back", fps=fps)
    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=clip_a_frames - 1,
        source_path=str(clip_a),
    )
    project = _add_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video",
        in_point=0,
        out_point=clip_b_frames - 1,
        source_path=str(clip_b),
    )
    out_path = _output_dir() / "005-back-to-back-cuts.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 006 -- trimmed clip (timeline shows only the middle of the source)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_006_trimmed_clip():
    """Source clip is ~4 seconds; the timeline entry uses only the middle 2
    seconds (in_point=fps, out_point=3*fps).  Tests that ``in_point`` is
    respected and the chain's ``length`` covers the full source."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    src_frames = int(4 * fps)
    in_pt = int(1 * fps)
    out_pt = int(3 * fps) - 1
    project = _build_initial_project("smoke_006_trimmed_clip", fps=fps)
    # Pre-register the chain with full source length so Kdenlive sees the
    # whole source as available; the timeline entry uses a sub-range.
    project.producers.append(
        Producer(
            id="clip_trimmed",
            resource=str(clip).replace("\\", "/"),
            properties={
                "resource": str(clip).replace("\\", "/"),
                "mlt_service": "avformat-novalidate",
                "length": str(src_frames),
                "eof": "pause",
                "seekable": "1",
                "audio_index": "1",
                "video_index": "0",
                "vstream": "0",
                "astream": "0",
                "mute_on_pause": "0",
            },
        )
    )
    pl = next(p for p in project.playlists if p.id == "playlist_video")
    pl.entries.append(
        PlaylistEntry(producer_id="clip_trimmed", in_point=in_pt, out_point=out_pt)
    )
    out_path = _output_dir() / "006-trimmed-clip.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 007 -- multi-title-cards (three editable titles back to back)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_007_multi_title_cards():
    """Three editable Kdenlive titles with different text, font sizes, and
    colors, back-to-back on V1."""
    fps = 29.97
    project = _build_initial_project("smoke_007_multi_titles", fps=fps)

    titles = [
        ("title_intro",  "Welcome",         int(2 * fps), 96, "255,255,255,255"),
        ("title_chapter", "Chapter 1",      int(3 * fps), 72, "255,210,80,255"),
        ("title_outro",  "Thanks for watching", int(2 * fps), 84, "180,220,255,255"),
    ]
    for pid, text, length, font_px, color in titles:
        project = _register_kdenlivetitle(
            project,
            producer_id=pid,
            label=text,
            length_frames=length,
            font_px=font_px,
            color=color,
        )
        project = _add_clip(
            project,
            producer_id=pid,
            track_id="playlist_video",
            in_point=0,
            out_point=length - 1,
            source_path="",
        )
    out_path = _output_dir() / "007-multi-title-cards.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 008 -- audio music bed (V1 video, A1 sync audio, A2 secondary track)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_008_audio_music_bed():
    """V1 = video clip with audio, A2 = a second audio source as a music
    bed.  A1 stays empty so Kdenlive uses the V1 clip's audio for sync,
    and A2 plays underneath."""
    video_clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",  # has audio
        GENERATED_CLIP,
    )
    music_clip = _resolve_clip(GENERATED_CLIP)  # 1kHz tone is a stand-in
    if video_clip is None or music_clip is None:
        pytest.skip("Required clips missing")

    fps = 29.97
    project = _build_initial_project("smoke_008_audio_bed", fps=fps)
    project = _add_track(project, "audio", name="A2 Music")

    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=int(5 * fps) - 1,
        source_path=str(video_clip),
    )
    project = _add_clip(
        project,
        producer_id="music",
        track_id="playlist_audio_1",  # the A2 track CreateTrack just added
        in_point=0,
        out_point=int(5 * fps) - 1,
        source_path=str(music_clip),
    )
    out_path = _output_dir() / "008-audio-music-bed.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 009 -- chapter markers / guides (YouTube chapter style)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_009_chapter_markers():
    """Single clip on V1 with several timeline guides marking
    chapter starts.  Guides translate to YouTube chapters when published."""
    clip = _resolve_clip(
        USER_TEST_KDENLIVE / "8832126-uhd_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    )
    if clip is None:
        pytest.skip("No clip available")

    fps = 29.97
    clip_frames = int(8 * fps)
    project = _build_initial_project("smoke_009_chapters", fps=fps)
    project = _add_clip(
        project,
        producer_id="vid",
        track_id="playlist_video",
        in_point=0,
        out_point=clip_frames - 1,
        source_path=str(clip),
    )
    project.guides = [
        Guide(position=0,                     label="Intro",          category="0"),
        Guide(position=int(2 * fps),          label="Setup",          category="1"),
        Guide(position=int(4 * fps),          label="Main demo",      category="2"),
        Guide(position=int(6 * fps),          label="Outro",          category="3"),
    ]
    out_path = _output_dir() / "009-chapter-markers.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 010 -- three-clip dissolves (tutorial-style edit)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_010_three_clip_dissolves():
    """Three clips A→B→C with cross-dissolves between A/B and B/C.

    Layout (frames @ 29.97fps):
        V1: [A 0..119]
        V2: [blank 90][B 90..240]                      (overlap with A: 90..119)
        V1 cont: [blank 30 frames after B][C 220..345]  (overlap with B: 220..240)

    To keep emission simple we put A and C on V1, B on V2, with two
    dissolves -- A→B (V1→V2) and B→C (V2→V1).
    """
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
        pytest.skip("Need three distinct clips")

    fps = 29.97
    seg = int(3 * fps)            # 3 seconds per clip
    overlap = int(1 * fps)        # 1 second overlap

    project = _build_initial_project("smoke_010_three_dissolves", fps=fps)
    project = _add_track(project, "video", name="V2")

    # V1: clip A from 0
    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=seg - 1,
        source_path=str(clip_a),
    )
    # V1: blank + clip C, overlapping the tail of B on V2
    a_end = seg
    b_start = a_end - overlap
    b_end = b_start + seg
    c_start = b_end - overlap
    c_end = c_start + seg
    blank_before_c = c_start - a_end
    project = _add_blank_then_clip(
        project,
        producer_id="clip_c",
        track_id="playlist_video",
        blank_frames=blank_before_c,
        in_point=0,
        out_point=seg - 1,
        source_path=str(clip_c),
    )

    # V2: blank + clip B, overlapping A's tail and C's head
    project = _add_blank_then_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video_1",
        blank_frames=b_start,
        in_point=0,
        out_point=seg - 1,
        source_path=str(clip_b),
    )

    # Dissolves
    project = _add_dissolve(
        project,
        outgoing_track_id="playlist_video",
        incoming_track_id="playlist_video_1",
        in_frame=b_start,
        out_frame=a_end - 1,
        transition_id="dissolve_a_to_b",
    )
    project = _add_dissolve(
        project,
        outgoing_track_id="playlist_video_1",  # B is on V2
        incoming_track_id="playlist_video",     # C lands back on V1
        in_frame=c_start,
        out_frame=b_end - 1,
        transition_id="dissolve_b_to_c",
    )

    out_path = _output_dir() / "010-three-clip-dissolves.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()


# ---------------------------------------------------------------------------
# 011 -- wipe transition (variant of dissolve, different kdenlive_id)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_011_wipe_transition():
    """Same XML pattern as a dissolve but with ``kdenlive_id=wipe``.
    Kdenlive's transition system treats ``luma`` + ``kdenlive_id``
    discriminators as the family selector."""
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
    clip_frames = int(3 * fps)
    overlap = int(1 * fps)

    project = _build_initial_project("smoke_011_wipe", fps=fps)
    project = _add_track(project, "video", name="V2")
    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=clip_frames - 1,
        source_path=str(clip_a),
    )
    project = _add_blank_then_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video_1",
        blank_frames=clip_frames - overlap,
        in_point=0,
        out_point=clip_frames - 1,
        source_path=str(clip_b),
    )
    project = _add_dissolve(
        project,
        outgoing_track_id="playlist_video",
        incoming_track_id="playlist_video_1",
        in_frame=clip_frames - overlap,
        out_frame=clip_frames - 1,
        transition_id="wipe_v1_v2",
        kdenlive_id="wipe",
    )
    out_path = _output_dir() / "011-wipe-transition.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()
