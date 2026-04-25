"""Smoke test 3.0: cross-dissolve between two stacked clips.

Kdenlive 25.x does NOT support same-track dissolves at the XML level
(verified in `src/transitions/transitionsrepository.cpp:113-115` --
`getSingleTrackTransitions()` is "Disabled until same track transitions
is implemented", and the value is only used for UI labelling).  Even
when the user drags a dissolve onto a single-track cut in the UI,
Kdenlive saves the project as the stacked-clip pattern: clip A on V1,
clip B on V2 starting `overlap` frames before A ends, plus a
`<transition mlt_service="luma" kdenlive_id="dissolve">` inside the
main sequence tractor whose ``in``/``out`` span the overlap and whose
``a_track``/``b_track`` are the 1-based ordinals of V1 and V2 in the
sequence's track list (track 0 = black background).

This test exercises that pattern via the new ``SequenceTransition``
model + serializer wiring, and drops a smoke output into the user's
local Kdenlive test folder for visual verification.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    SequenceTransition,
    Track,
)
from workshop_video_brain.core.models.timeline import AddClip, CreateTrack
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
    serialize_versioned,
)


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


def _add_video_track(project: KdenliveProject, name: str) -> KdenliveProject:
    return patch_project(project, [CreateTrack(track_type="video", name=name)])


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


def _track_ordinal(project: KdenliveProject, track_id: str) -> int:
    """1-based ordinal of *track_id* in the main sequence's track list.

    The sequence emits black_track at index 0, then each user track in
    ``project.tracks`` order.  This must agree with the serializer's
    sequence-track emission order (see ``serialize_project``).
    """
    for i, t in enumerate(project.tracks, start=1):
        if t.id == track_id:
            return i
    raise ValueError(f"track {track_id!r} not in project")


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
    """Insert a blank gap of *blank_frames* then a clip on *track_id*.

    Used to start the upper-track clip ``overlap`` frames before the
    lower clip ends; the gap pushes the entry to the right time slot.
    """
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


def _add_dissolve(
    project: KdenliveProject,
    *,
    a_track_id: str,
    b_track_id: str,
    in_frame: int,
    out_frame: int,
    transition_id: str = "dissolve_1",
) -> KdenliveProject:
    """Append a luma cross-dissolve to the main sequence's transitions."""
    new = project.model_copy(deep=True)
    new.sequence_transitions.append(
        SequenceTransition(
            id=transition_id,
            a_track=_track_ordinal(new, a_track_id),
            b_track=_track_ordinal(new, b_track_id),
            in_frame=in_frame,
            out_frame=out_frame,
            mlt_service="luma",
            kdenlive_id="dissolve",
            properties={
                "factory": "loader",
                "resource": "",
                "softness": "0",
                "reverse": "0",
                "alpha_over": "1",
                "fix_background_alpha": "1",
            },
        )
    )
    return new


# ---------------------------------------------------------------------------
# Pure-model assertions
# ---------------------------------------------------------------------------


class TestSmoke3Dissolve:
    def test_dissolve_emitted_inside_main_sequence(self, tmp_path):
        if not GENERATED_CLIP.exists():
            pytest.skip(f"Generated test clip missing: {GENERATED_CLIP}")

        # 5-second clips, 1-second dissolve overlap (~30 frames @ 29.97fps).
        fps = 29.97
        clip_frames = int(5 * fps) - 1  # 148, so length 149
        overlap = int(1 * fps)  # 30 frames
        a_end = clip_frames + 1  # 149 -- absolute frame just past end of clip A
        dissolve_in = a_end - overlap  # 119
        dissolve_out = a_end - 1  # 148

        project = _build_initial_project("smoke3_dissolve", fps=fps)
        project = _add_video_track(project, name="V2")
        # Clip A on V1 from frame 0
        project = _add_clip(
            project,
            producer_id="clip_a",
            track_id="playlist_video",
            in_point=0,
            out_point=clip_frames,
            source_path=str(GENERATED_CLIP),
        )
        # Clip B on V2 starting at (clip_a length - overlap)
        project = _add_blank_then_clip(
            project,
            producer_id="clip_b",
            track_id="playlist_video_1",
            blank_frames=clip_frames + 1 - overlap,
            in_point=0,
            out_point=clip_frames,
            source_path=str(GENERATED_CLIP),
        )
        # Dissolve from V1 to V2 across the overlap window
        project = _add_dissolve(
            project,
            a_track_id="playlist_video",
            b_track_id="playlist_video_1",
            in_frame=dissolve_in,
            out_frame=dissolve_out,
        )

        out = tmp_path / "smoke3.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()

        # Find the main sequence (UUID-id'd tractor) and its transitions
        seqs = [
            t for t in root.findall("tractor")
            if t.get("id", "").startswith("{")
        ]
        assert len(seqs) == 1
        seq = seqs[0]

        transitions = seq.findall("transition")
        # Must include a luma/dissolve transition with the right window
        dissolves = [
            t for t in transitions
            if t.find("./property[@name='kdenlive_id']") is not None
            and t.find("./property[@name='kdenlive_id']").text == "dissolve"
        ]
        assert len(dissolves) == 1
        d = dissolves[0]
        assert d.get("in") == str(dissolve_in)
        assert d.get("out") == str(dissolve_out)

    def test_dissolve_a_b_track_ordinals(self, tmp_path):
        """``a_track`` / ``b_track`` are 1-based ordinals into the sequence's
        track list (after the leading black_track at index 0)."""
        project = _build_initial_project("smoke3_ordinals")
        project = _add_video_track(project, name="V2")
        # Tracks now: V1 (idx 1), A1 (idx 2), V2 (idx 3)
        project = _add_dissolve(
            project,
            a_track_id="playlist_video",        # V1 -> 1
            b_track_id="playlist_video_1",      # V2 -> 3
            in_frame=0,
            out_frame=10,
        )
        out = tmp_path / "ordinals.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        seq = next(t for t in root.findall("tractor") if t.get("id", "").startswith("{"))
        d = next(
            t for t in seq.findall("transition")
            if t.find("./property[@name='kdenlive_id']") is not None
            and t.find("./property[@name='kdenlive_id']").text == "dissolve"
        )
        assert d.find("./property[@name='a_track']").text == "1"
        assert d.find("./property[@name='b_track']").text == "3"

    def test_dissolve_carries_required_properties(self, tmp_path):
        project = _build_initial_project("smoke3_props")
        project = _add_video_track(project, name="V2")
        project = _add_dissolve(
            project,
            a_track_id="playlist_video",
            b_track_id="playlist_video_1",
            in_frame=0,
            out_frame=29,
        )
        out = tmp_path / "props.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        seq = next(t for t in root.findall("tractor") if t.get("id", "").startswith("{"))
        d = next(
            t for t in seq.findall("transition")
            if t.find("./property[@name='kdenlive_id']") is not None
            and t.find("./property[@name='kdenlive_id']").text == "dissolve"
        )
        props = {
            c.get("name"): (c.text or "")
            for c in d
            if c.tag == "property"
        }
        assert props["mlt_service"] == "luma"
        assert props["factory"] == "loader"
        assert props["alpha_over"] == "1"
        assert props["fix_background_alpha"] == "1"


# ---------------------------------------------------------------------------
# Side-effect: drop a smoke file into the user's Kdenlive test folder
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_drop_smoke3_output(tmp_path):
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    clip_a_candidates = [
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",
        GENERATED_CLIP,
    ]
    clip_b_candidates = [
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",
        GENERATED_CLIP,
    ]
    clip_a = next((p for p in clip_a_candidates if p.exists()), None)
    clip_b = next((p for p in clip_b_candidates if p.exists()), None)
    if clip_a is None or clip_b is None:
        pytest.skip("No test clips available")

    fps = 29.97
    clip_a_frames = int(5 * fps)        # 5-second clip A on V1
    clip_b_frames = int(5 * fps)        # 5-second clip B on V2
    overlap_frames = int(1.5 * fps)     # 1.5-second cross-dissolve
    dissolve_in = clip_a_frames - overlap_frames
    dissolve_out = clip_a_frames - 1

    project = _build_initial_project("mcp_smoke_cross_dissolve", fps=fps)
    project = _add_video_track(project, name="V2")
    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=clip_a_frames - 1,
        source_path=str(clip_a),
    )
    project = _add_blank_then_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video_1",
        blank_frames=clip_a_frames - overlap_frames,
        in_point=0,
        out_point=clip_b_frames - 1,
        source_path=str(clip_b),
    )
    project = _add_dissolve(
        project,
        a_track_id="playlist_video",
        b_track_id="playlist_video_1",
        in_frame=dissolve_in,
        out_frame=dissolve_out,
        transition_id="cross_dissolve_v1_v2",
    )

    out_path = USER_OUTPUT_DIR / "004-cross-dissolve.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    # Sanity: the dissolve made it into the main sequence
    root = ET.parse(out_path).getroot()
    seq = next(t for t in root.findall("tractor") if t.get("id", "").startswith("{"))
    transitions = seq.findall("transition")
    dissolve_count = sum(
        1 for t in transitions
        if t.find("./property[@name='kdenlive_id']") is not None
        and t.find("./property[@name='kdenlive_id']").text == "dissolve"
    )
    assert dissolve_count == 1
