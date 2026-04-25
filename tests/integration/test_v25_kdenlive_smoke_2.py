"""Smoke test 2.0: multi-track project with two clips and a title card.

Builds on the v25 single-clip smoke test by exercising the harder paths:

* Three tracks (V1, V2 video; A1 audio) using the ``CreateTrack`` patcher
  intent -- the same code path ``track_add`` uses.
* Two media clips on different video tracks (V1 + V2).
* A color title card pre-registered as a ``mlt_service=color`` producer,
  then placed via ``AddClip``.

Drops the result into the user's local Kdenlive test folder so the file
can be opened in Kdenlive 25.x for visual verification.
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
    """Mirror ``project_create_working_copy``: V1 + A1 baseline."""
    project = KdenliveProject(
        version="7",
        title=title,
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
    )
    project.tracks = [
        Track(id="playlist_video", track_type="video", name="Video"),
        Track(id="playlist_audio", track_type="audio", name="Audio"),
    ]
    project.playlists = [
        Playlist(id="playlist_video"),
        Playlist(id="playlist_audio"),
    ]
    project.tractor = {"id": "main_seq", "in": "0", "out": "0"}
    return project


def _add_video_track(project: KdenliveProject, name: str) -> KdenliveProject:
    """Run a CreateTrack intent through the patcher (mirrors ``track_add``)."""
    return patch_project(project, [CreateTrack(track_type="video", name=name)])


def _kdenlivetitle_xmldata(
    text: str,
    *,
    width: int,
    height: int,
    length_frames: int,
    font_px: int,
    font: str,
) -> str:
    """Build the ``<kdenlivetitle>`` XML payload Kdenlive expects in
    ``<property name="xmldata">`` for an editable title card.

    The text is centered inside the project frame.  ``font_px`` controls
    the font size in pixels (Kdenlive renders at the title's own width/
    height, not the project's, so the size should make sense at the title
    resolution).  ``font`` must name a font that's actually installed on
    the host -- ``Sans`` works on Linux but is unknown on Windows, where
    Kdenlive will pop up a "Clip Problems" dialog and offer to substitute.
    Default callers should pass a platform-safe font (e.g. ``Segoe UI``).
    """
    out = max(0, length_frames - 1)
    # Rough centered text box: 80% of frame width, 20% of frame height,
    # placed at the visual center of the frame.
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
        f'font="{font}" font-color="255,255,255,255" font-italic="0" '
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


# Default font for generated title cards.  ``Segoe UI`` is shipped with all
# modern Windows; ``DejaVu Sans`` is the typical Linux/macOS fallback.  Pick
# Windows-safe by default since the project's primary deployment is Windows;
# override via ``_register_kdenlivetitle(..., font="...")`` for cross-platform
# tests.
_DEFAULT_TITLE_FONT = "Segoe UI"


def _register_kdenlivetitle(
    project: KdenliveProject,
    producer_id: str,
    label: str,
    length_frames: int,
    *,
    font_px: int = 72,
    font: str = _DEFAULT_TITLE_FONT,
) -> KdenliveProject:
    """Pre-register an editable ``mlt_service=kdenlivetitle`` producer.

    The serializer emits this as a ``<producer>`` (not ``<chain>``); the
    ``xmldata`` property carries the title document Kdenlive's title editor
    opens when the user double-clicks the clip in the bin.
    """
    new = project.model_copy(deep=True)
    width = new.profile.width
    height = new.profile.height
    fps = new.profile.fps or 25.0
    # Format kdenlive:duration as ``HH:MM:SS;FF`` (semicolon separator
    # signals the value is in NTSC-style timecode with a frame component).
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


# Backwards-compat alias used by older structural tests below.  The new
# tests use ``_register_kdenlivetitle`` directly.
def _register_color_title(
    project: KdenliveProject,
    producer_id: str,
    color_hex: str,
    label: str,
    length_frames: int,
) -> KdenliveProject:
    """Pre-register a ``mlt_service=color`` solid-color clip."""
    new = project.model_copy(deep=True)
    new.producers.append(
        Producer(
            id=producer_id,
            resource=color_hex,
            properties={
                "mlt_service": "color",
                "resource": color_hex,
                "length": str(length_frames),
                "kdenlive:clipname": label,
            },
        )
    )
    return new


def _add_clip(
    project: KdenliveProject,
    *,
    producer_id: str,
    track_id: str,
    in_point: int,
    out_point: int,
    source_path: str = "",
) -> KdenliveProject:
    """Run an AddClip intent through the patcher (mirrors ``clip_insert``)."""
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


# ---------------------------------------------------------------------------
# Pure-model assertions (no Kdenlive needed)
# ---------------------------------------------------------------------------


class TestSmoke2Structure:
    def test_create_track_then_three_tracks(self, tmp_path):
        """``CreateTrack`` adds a third track that the serializer wires correctly."""
        project = _build_initial_project("smoke2_three_tracks")
        project = _add_video_track(project, name="V2")

        assert len(project.tracks) == 3
        assert {t.id for t in project.tracks} == {
            "playlist_video", "playlist_audio", "playlist_video_1",
        }
        assert project.tracks[2].track_type == "video"

        out = tmp_path / "smoke2.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()

        # Expect: 3 per-track tractors + 1 main sequence + 1 project wrapper = 5 tractors
        per_track = [
            t for t in root.findall("tractor")
            if t.get("id", "").startswith("tractor_track_")
        ]
        assert {t.get("id") for t in per_track} == {
            "tractor_track_playlist_video",
            "tractor_track_playlist_audio",
            "tractor_track_playlist_video_1",
        }

        # Main sequence should reference all three per-track tractors.
        seq = next(
            t for t in root.findall("tractor")
            if "-" in t.get("id", "") and t.get("id", "").startswith("{")
        )
        seq_track_refs = {t.get("producer") for t in seq.findall("track")}
        assert "tractor_track_playlist_video_1" in seq_track_refs

    def test_color_producer_emitted_as_producer_not_chain(self, tmp_path):
        """Title cards (``mlt_service=color``) must stay as ``<producer>``,
        never become ``<chain>``."""
        project = _build_initial_project("smoke2_title")
        project = _register_color_title(
            project, "title_intro", "#1a1a2e", "Intro", length_frames=60
        )
        out = tmp_path / "title.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()

        # The color producer must appear as <producer>, not <chain>
        as_producer = root.find("./producer[@id='title_intro']")
        as_chain = root.find("./chain[@id='title_intro']")
        assert as_producer is not None
        assert as_chain is None

        # ...and no `_bin` twin (chains have twins; producers do not)
        assert root.find("./producer[@id='title_intro_bin']") is None
        assert root.find("./chain[@id='title_intro_bin']") is None

    def test_color_producer_referenced_directly_by_main_bin(self, tmp_path):
        """``main_bin`` references the color producer by its raw id, not ``_bin``."""
        project = _build_initial_project("smoke2_title_bin")
        project = _register_color_title(
            project, "title_intro", "#1a1a2e", "Intro", length_frames=60
        )
        out = tmp_path / "title.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()

        main_bin = root.find("./playlist[@id='main_bin']")
        entry_refs = {e.get("producer") for e in main_bin.findall("entry")}
        assert "title_intro" in entry_refs

    def test_multi_clip_multi_track(self, tmp_path):
        """Two media clips on different video tracks; both reach the timeline."""
        if not GENERATED_CLIP.exists():
            pytest.skip(f"Generated test clip missing: {GENERATED_CLIP}")

        project = _build_initial_project("smoke2_multi_clip")
        project = _add_video_track(project, name="V2")
        # Clip on V1
        project = _add_clip(
            project,
            producer_id="clip_a",
            track_id="playlist_video",
            in_point=0,
            out_point=148,
            source_path=str(GENERATED_CLIP),
        )
        # Clip on V2 (same source for the smoke; in real use this would be
        # a second clip)
        project = _add_clip(
            project,
            producer_id="clip_b",
            track_id="playlist_video_1",
            in_point=0,
            out_point=89,
            source_path=str(GENERATED_CLIP),
        )

        out = tmp_path / "multi.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()

        # V1 playlist entries
        v1_entries = root.findall("./playlist[@id='playlist_video']/entry")
        assert any(e.get("producer") == "clip_a" for e in v1_entries)
        # V2 playlist entries
        v2_entries = root.findall("./playlist[@id='playlist_video_1']/entry")
        assert any(e.get("producer") == "clip_b" for e in v2_entries)
        # A1 playlist has no entries
        a1_entries = root.findall("./playlist[@id='playlist_audio']/entry")
        assert a1_entries == []

    def test_round_trip_preserves_all_tracks(self, tmp_path):
        """Parse → re-serialize keeps the V1+V2+A1 layout intact (clip_insert path)."""
        if not GENERATED_CLIP.exists():
            pytest.skip(f"Generated test clip missing: {GENERATED_CLIP}")

        project = _build_initial_project("smoke2_roundtrip")
        project = _add_video_track(project, name="V2")
        project = _add_clip(
            project,
            producer_id="clip_a",
            track_id="playlist_video",
            in_point=0,
            out_point=148,
            source_path=str(GENERATED_CLIP),
        )

        v1 = serialize_versioned(project, tmp_path, "smoke2_roundtrip")
        parsed = parse_project(v1)

        # Round-trip preserved tracks (count + types)
        track_ids = {t.id for t in parsed.tracks}
        assert {"playlist_video", "playlist_audio", "playlist_video_1"}.issubset(track_ids)
        # The clip survived
        v1_pl = next(p for p in parsed.playlists if p.id == "playlist_video")
        clip_entries = [e for e in v1_pl.entries if e.producer_id == "clip_a"]
        assert len(clip_entries) == 1
        assert clip_entries[0].out_point == 148


# ---------------------------------------------------------------------------
# Side-effect: write a file the user can open in Kdenlive
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not USER_OUTPUT_DIR.parent.exists(),
    reason="User's Video Production tests folder not available",
)
def test_drop_smoke2_output(tmp_path):
    """Build the multi-track + title-card project the user asked for and drop it
    into the local Kdenlive test folder."""
    USER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Pick two real clips if available; fall back to the generated one.
    clip_a_candidates = [
        USER_TEST_KDENLIVE / "15647204_3840_2160_30fps.mp4",   # 9 MB, 30fps UHD
        GENERATED_CLIP,
    ]
    clip_b_candidates = [
        USER_TEST_KDENLIVE / "13203211_2160_3840_60fps.mp4",   # 17 MB, vertical UHD
        GENERATED_CLIP,
    ]
    clip_a = next((p for p in clip_a_candidates if p.exists()), None)
    clip_b = next((p for p in clip_b_candidates if p.exists()), None)
    if clip_a is None or clip_b is None:
        pytest.skip("No test clips available to build smoke2 output")

    # Build the project: V1 (clip_a + title at start), V2 (clip_b), A1.
    fps = 29.97
    project = _build_initial_project("mcp_smoke_two_clips_one_title", fps=fps)
    project = _add_video_track(project, name="V2")
    # Pre-register the title card as an editable Kdenlive title (not a flat
    # color clip) so the user can double-click it in Kdenlive to edit.
    project = _register_kdenlivetitle(
        project,
        producer_id="title_intro",
        label="Intro Title",
        length_frames=int(2 * fps),  # 2 seconds
    )
    # Title card on V1 first.
    project = _add_clip(
        project,
        producer_id="title_intro",
        track_id="playlist_video",
        in_point=0,
        out_point=int(2 * fps) - 1,
        source_path="",  # color producer; resource already set in _register_color_title
    )
    # Clip A on V1 after the title.
    project = _add_clip(
        project,
        producer_id="clip_a",
        track_id="playlist_video",
        in_point=0,
        out_point=int(5 * fps) - 1,  # ~5 seconds
        source_path=str(clip_a),
    )
    # Clip B on V2 starting at frame 0 (overlapping the title).
    project = _add_clip(
        project,
        producer_id="clip_b",
        track_id="playlist_video_1",
        in_point=0,
        out_point=int(3 * fps) - 1,  # ~3 seconds
        source_path=str(clip_b),
    )

    out_path = USER_OUTPUT_DIR / "003-two-clips-one-title.kdenlive"
    serialize_project(project, out_path)
    assert out_path.exists()

    # Sanity: every chunk we promised actually landed.
    root = ET.parse(out_path).getroot()
    main_bin = root.find("./playlist[@id='main_bin']")
    bin_refs = {e.get("producer") for e in main_bin.findall("entry")}
    assert "title_intro" in bin_refs                         # color producer ref
    assert any(r.endswith("_bin") for r in bin_refs)         # at least one chain twin
    assert root.find("./tractor[@id='tractor_track_playlist_video']") is not None
    assert root.find("./tractor[@id='tractor_track_playlist_video_1']") is not None
    assert root.find("./tractor[@id='tractor_track_playlist_audio']") is not None
