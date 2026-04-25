"""Unit tests for Kdenlive serializer bin registration (sub-specs 1, 2, 3).

Covers:
- kdenlive:uuid / kdenlive:id / kdenlive:clip_type / kdenlive:folderid on producers
- main_bin playlist with all producer entries
- root <mlt> producer="main_bin" and LC_NUMERIC="C" attributes
- black_track producer generation
- Paired empty playlists
- Internal mix / frei0r.cairoblend transitions in tractor
- Profile progressive / display_aspect / sample_aspect attributes
- Frame rate as proper num/den fraction
"""
from __future__ import annotations

import re
import uuid
import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

# UUID pattern: {xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx}
_UUID_RE = re.compile(r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$")


def _get_props(elem: ET.Element) -> dict[str, str]:
    """Collect all <property name="...">value</property> children into a dict."""
    return {
        child.get("name", ""): (child.text or "")
        for child in elem
        if child.tag == "property"
    }


def _find_producer_or_chain(root: ET.Element, producer_id: str) -> ET.Element | None:
    """Locate a media element by id; avformat sources are emitted as <chain>."""
    for tag in ("producer", "chain"):
        for elem in root.findall(tag):
            if elem.get("id") == producer_id:
                return elem
    return None


def _make_project(
    producers: list[Producer] | None = None,
    playlists: list[Playlist] | None = None,
    tracks: list[Track] | None = None,
    tractor: dict | None = None,
    fps: float = 25.0,
) -> KdenliveProject:
    if producers is None:
        producers = [
            Producer(
                id="prod0",
                resource="/media/clip.mp4",
                properties={"resource": "/media/clip.mp4", "mlt_service": "avformat"},
            )
        ]
    if playlists is None:
        playlists = [
            Playlist(
                id="pl0",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=99)],
            )
        ]
    if tracks is None:
        tracks = [Track(id="pl0", track_type="video")]
    if tractor is None:
        tractor = {"id": "tractor0", "in": "0", "out": "99"}
    return KdenliveProject(
        version="7",
        title="Bin Test",
        profile=ProjectProfile(width=1920, height=1080, fps=fps, colorspace="709"),
        producers=producers,
        playlists=playlists,
        tracks=tracks,
        tractor=tractor,
    )


# ---------------------------------------------------------------------------
# Sub-spec 1: Producer metadata
# ---------------------------------------------------------------------------


class TestProducerMetadata:
    # Kdenlive 25.x uses ``property_exists("kdenlive:uuid")`` on bin entries
    # as the discriminator for "this is a sequence".  Media producers / chains
    # therefore must NOT carry ``kdenlive:uuid`` -- only ``kdenlive:control_uuid``.
    # See projectitemmodel.cpp ``loadBinPlaylist`` in the Kdenlive source.

    def test_control_uuid_present(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        props = _get_props(prod)
        assert "kdenlive:control_uuid" in props
        # And kdenlive:uuid must be absent (otherwise Kdenlive routes the
        # entry into the sequence-handling branch and fails to register it).
        assert "kdenlive:uuid" not in props

    def test_control_uuid_format(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        props = _get_props(prod)
        assert _UUID_RE.match(props["kdenlive:control_uuid"]), (
            f"control_uuid not in {{uuid}} format: {props['kdenlive:control_uuid']}"
        )

    def test_control_uuid_deterministic(self, tmp_path):
        """Same producer id must produce the same control_uuid across two serializations."""
        project = _make_project()
        out1 = tmp_path / "a.kdenlive"
        out2 = tmp_path / "b.kdenlive"
        serialize_project(project, out1)
        serialize_project(project, out2)

        def _control_uuid(path):
            root = ET.parse(path).getroot()
            prod = _find_producer_or_chain(root, "prod0")
            return _get_props(prod)["kdenlive:control_uuid"]

        assert _control_uuid(out1) == _control_uuid(out2)

    def test_kdenlive_id_starts_at_4(self, tmp_path):
        # Kdenlive reserves integer id 2 for the "Sequences" bin folder and
        # 3 for the project's main sequence; user clips start at 4.
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        props = _get_props(prod)
        assert props["kdenlive:id"] == "4"

    def test_kdenlive_id_sequential(self, tmp_path):
        """Multiple producers get sequential IDs starting at 4."""
        project = _make_project(
            producers=[
                Producer(id="p0", resource="/a.mp4", properties={"resource": "/a.mp4"}),
                Producer(id="p1", resource="/b.mp4", properties={"resource": "/b.mp4"}),
                Producer(id="p2", resource="/c.mp4", properties={"resource": "/c.mp4"}),
            ],
            playlists=[
                Playlist(
                    id="pl0",
                    entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=9)],
                )
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        ids = {}
        for tag in ("producer", "chain"):
            for prod in root.findall(tag):
                pid = prod.get("id")
                if pid in ("p0", "p1", "p2"):
                    ids[pid] = _get_props(prod)["kdenlive:id"]
        assert ids == {"p0": "4", "p1": "5", "p2": "6"}

    def test_clip_type_avformat(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(
                    id="vid0",
                    resource="/clip.mp4",
                    properties={"resource": "/clip.mp4", "mlt_service": "avformat"},
                )
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "vid0")
        # Kdenlive 25.x writes 0 (auto-detect from chain) on avformat chains.
        assert _get_props(prod)["kdenlive:clip_type"] == "0"

    def test_clip_type_kdenlivetitle(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(
                    id="title0",
                    resource="",
                    properties={"mlt_service": "kdenlivetitle"},
                )
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "title0")
        # Kdenlive 25.x saves kdenlivetitle clips with clip_type=2 (the
        # legacy 6 from definitions.h is no longer accepted by the bin loader).
        assert _get_props(prod)["kdenlive:clip_type"] == "2"

    def test_clip_type_generic_defaults_to_0(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(
                    id="gen0",
                    resource="/image.png",
                    properties={"resource": "/image.png"},
                )
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "gen0")
        assert _get_props(prod)["kdenlive:clip_type"] == "0"

    def test_folderid_default(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        assert _get_props(prod)["kdenlive:folderid"] == "-1"

    def test_folderid_custom_preserved(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(
                    id="prod0",
                    resource="/clip.mp4",
                    properties={"resource": "/clip.mp4", "kdenlive:folderid": "3"},
                )
            ]
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        assert _get_props(prod)["kdenlive:folderid"] == "3"

    def test_existing_properties_preserved(self, tmp_path):
        """Non-managed properties from the model survive serialization."""
        project = _make_project(
            producers=[
                Producer(
                    id="prod0",
                    resource="/clip.mp4",
                    properties={"resource": "/clip.mp4", "length": "300"},
                )
            ]
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = _find_producer_or_chain(root, "prod0")
        props = _get_props(prod)
        assert props.get("length") == "300"


# ---------------------------------------------------------------------------
# Sub-spec 2: Main bin playlist
# ---------------------------------------------------------------------------


class TestMainBin:
    def test_root_has_producer_main_bin(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.get("producer") == "main_bin"

    def test_root_has_lc_numeric(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.get("LC_NUMERIC") == "C"

    def test_main_bin_playlist_exists(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        assert main_bin is not None

    def test_main_bin_docproperties_version(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        props = _get_props(main_bin)
        assert props.get("kdenlive:docproperties.version") == "1.1"

    def test_main_bin_docproperties_uuid(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        props = _get_props(main_bin)
        assert _UUID_RE.match(props.get("kdenlive:docproperties.uuid", ""))

    def test_main_bin_has_entry_per_producer(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(id="p0", resource="/a.mp4", properties={"resource": "/a.mp4"}),
                Producer(id="p1", resource="/b.mp4", properties={"resource": "/b.mp4"}),
            ],
            playlists=[
                Playlist(
                    id="pl0",
                    entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=9)],
                )
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        entries = main_bin.findall("entry")
        producer_refs = {e.get("producer") for e in entries}
        # main_bin also contains a reference to the main sequence tractor
        # (UUID-formatted).  We just require every user producer to be present.
        assert {"p0", "p1"}.issubset(producer_refs)

    def test_main_bin_empty_project(self, tmp_path):
        """Empty project (no producers) must still produce a valid main_bin.

        In the v25 shape the main_bin always contains exactly one entry: the
        UUID reference to the main sequence tractor that Kdenlive opens as
        the timeline.  No user producers means no extra entries.
        """
        project = KdenliveProject(
            title="Empty",
            profile=ProjectProfile(),
            producers=[],
            playlists=[],
            tracks=[],
            tractor=None,
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        assert main_bin is not None
        entries = main_bin.findall("entry")
        # Exactly the sequence entry; UUID-formatted producer ref.
        assert len(entries) == 1
        assert _UUID_RE.match(entries[0].get("producer", ""))


# ---------------------------------------------------------------------------
# Sub-spec 3: Track structure, black_track, transitions, profile attributes
# ---------------------------------------------------------------------------


class TestTrackStructure:
    def test_black_track_producer_exists(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        bt = root.find("./producer[@id='black_track']")
        assert bt is not None

    def test_black_track_mlt_service(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        bt = root.find("./producer[@id='black_track']")
        assert _get_props(bt).get("mlt_service") == "color"

    def test_black_track_resource(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        bt = root.find("./producer[@id='black_track']")
        assert _get_props(bt).get("resource") == "black"

    def test_black_track_length(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        bt = root.find("./producer[@id='black_track']")
        assert _get_props(bt).get("length") == "2147483647"

    def test_paired_playlist_generated(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.find("./playlist[@id='pl0_kdpair']") is not None

    def test_paired_playlist_is_empty(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        pair = root.find("./playlist[@id='pl0_kdpair']")
        assert len(list(pair)) == 0

    def test_paired_playlists_for_all_tracks(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(id="p0", resource="/a.mp4", properties={"resource": "/a.mp4"}),
                Producer(id="p1", resource="/b.mp4", properties={"resource": "/b.mp4"}),
            ],
            playlists=[
                Playlist(id="pl0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=9)]),
                Playlist(id="pl1", entries=[PlaylistEntry(producer_id="p1", in_point=0, out_point=9)]),
            ],
            tracks=[
                Track(id="pl0", track_type="video"),
                Track(id="pl1", track_type="audio"),
            ],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.find("./playlist[@id='pl0_kdpair']") is not None
        assert root.find("./playlist[@id='pl1_kdpair']") is not None

    def _main_sequence(self, root: ET.Element) -> ET.Element:
        """The v25-shape main sequence tractor (UUID id)."""
        for tractor in root.findall("tractor"):
            if _UUID_RE.match(tractor.get("id", "")):
                return tractor
        raise AssertionError("main sequence tractor not found")

    def test_main_sequence_black_track_first(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        seq = self._main_sequence(root)
        tracks = seq.findall("track")
        assert tracks[0].get("producer") == "black_track"

    def test_per_track_tractor_present(self, tmp_path):
        """Each user track gets its own ``<tractor>``."""
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        # The per-track tractor wraps two playlist refs (content + paired empty).
        per_track = [
            t for t in root.findall("tractor")
            if t.get("id", "").startswith("tractor_track_")
        ]
        assert any(t.get("id") == "tractor_track_pl0" for t in per_track)

    def test_per_track_tractor_references_kdpair_playlist(self, tmp_path):
        """The per-track tractor must reference both the content and *_kdpair playlists."""
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        per_track = next(
            t for t in root.findall("tractor")
            if t.get("id") == "tractor_track_pl0"
        )
        refs = {tr.get("producer") for tr in per_track.findall("track")}
        assert refs == {"pl0", "pl0_kdpair"}

    def _sequence_transitions(self, root: ET.Element) -> list[dict[str, str]]:
        for tractor in root.findall("tractor"):
            if _UUID_RE.match(tractor.get("id", "")):
                return [_get_props(t) for t in tractor.findall("transition")]
        return []

    def test_video_track_gets_qtblend(self, tmp_path):
        """Kdenlive 25.x uses qtblend (not frei0r.cairoblend) on video tracks."""
        project = _make_project(
            tracks=[Track(id="pl0", track_type="video")]
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        qtblend = [t for t in transitions if t.get("mlt_service") == "qtblend"]
        assert len(qtblend) >= 1

    def test_audio_track_gets_mix(self, tmp_path):
        project = _make_project(
            producers=[
                Producer(id="p0", resource="/a.mp3", properties={"resource": "/a.mp3"}),
            ],
            playlists=[
                Playlist(id="pl0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=9)])
            ],
            tracks=[Track(id="pl0", track_type="audio")],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        mix = [t for t in transitions if t.get("mlt_service") == "mix"]
        assert len(mix) >= 1

    def test_qtblend_always_active(self, tmp_path):
        project = _make_project(tracks=[Track(id="pl0", track_type="video")])
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        cb = next(t for t in transitions if t.get("mlt_service") == "qtblend")
        assert cb.get("always_active") == "1"

    def test_mix_always_active_and_sum(self, tmp_path):
        project = _make_project(
            producers=[Producer(id="p0", resource="/a.mp3", properties={"resource": "/a.mp3"})],
            playlists=[Playlist(id="pl0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=9)])],
            tracks=[Track(id="pl0", track_type="audio")],
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        mix = next(t for t in transitions if t.get("mlt_service") == "mix")
        assert mix.get("always_active") == "1"
        assert mix.get("sum") == "1"

    def test_transition_a_track_is_0(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        for t in transitions:
            assert t.get("a_track") == "0"

    def test_transition_b_track_matches_content_index(self, tmp_path):
        """b_track must reference the content track's index (1 for the first track)."""
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._sequence_transitions(root)
        # Only one track; content is at index 1 (after black_track at 0)
        assert any(t.get("b_track") == "1" for t in transitions)

    def test_profile_progressive(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        profile = root.find("profile")
        assert profile.get("progressive") == "1"

    def test_profile_sample_aspect(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        profile = root.find("profile")
        assert profile.get("sample_aspect_num") == "1"
        assert profile.get("sample_aspect_den") == "1"

    def test_profile_display_aspect_1080p(self, tmp_path):
        """1920x1080 must produce 16:9 display aspect ratio."""
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        profile = root.find("profile")
        assert profile.get("display_aspect_num") == "16"
        assert profile.get("display_aspect_den") == "9"

    def test_fps_integer_produces_num_1_den(self, tmp_path):
        """25 fps → frame_rate_num=25, frame_rate_den=1."""
        project = _make_project(fps=25.0)
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        profile = root.find("profile")
        assert profile.get("frame_rate_num") == "25"
        assert profile.get("frame_rate_den") == "1"

    def test_fps_ntsc_produces_proper_fraction(self, tmp_path):
        """29.97 fps → frame_rate_num=30000, frame_rate_den=1001."""
        project = _make_project(fps=29.97)
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        profile = root.find("profile")
        assert profile.get("frame_rate_num") == "30000"
        assert profile.get("frame_rate_den") == "1001"
