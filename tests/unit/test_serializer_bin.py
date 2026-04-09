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
    def test_uuid_present(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
        props = _get_props(prod)
        assert "kdenlive:uuid" in props

    def test_uuid_format(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
        props = _get_props(prod)
        assert _UUID_RE.match(props["kdenlive:uuid"]), (
            f"UUID not in {{uuid}} format: {props['kdenlive:uuid']}"
        )

    def test_uuid_deterministic(self, tmp_path):
        """Same producer id must produce the same UUID across two serializations."""
        project = _make_project()
        out1 = tmp_path / "a.kdenlive"
        out2 = tmp_path / "b.kdenlive"
        serialize_project(project, out1)
        serialize_project(project, out2)

        def _uuid(path):
            root = ET.parse(path).getroot()
            prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
            return _get_props(prod)["kdenlive:uuid"]

        assert _uuid(out1) == _uuid(out2)

    def test_kdenlive_id_starts_at_2(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
        props = _get_props(prod)
        assert props["kdenlive:id"] == "2"

    def test_kdenlive_id_sequential(self, tmp_path):
        """Multiple producers get sequential IDs starting at 2."""
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
        for prod in root.findall("producer"):
            pid = prod.get("id")
            if pid in ("p0", "p1", "p2"):
                ids[pid] = _get_props(prod)["kdenlive:id"]
        assert ids == {"p0": "2", "p1": "3", "p2": "4"}

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
        prod = next(p for p in root.findall("producer") if p.get("id") == "vid0")
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
        prod = next(p for p in root.findall("producer") if p.get("id") == "title0")
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
        prod = next(p for p in root.findall("producer") if p.get("id") == "gen0")
        assert _get_props(prod)["kdenlive:clip_type"] == "0"

    def test_folderid_default(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
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
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
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
        prod = next(p for p in root.findall("producer") if p.get("id") == "prod0")
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
        assert producer_refs == {"p0", "p1"}

    def test_main_bin_empty_project(self, tmp_path):
        """Empty project (no producers) must still produce a valid main_bin."""
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
        assert len(main_bin.findall("entry")) == 0


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

    def test_tractor_black_track_first(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        tracks = tractor.findall("track")
        assert tracks[0].get("producer") == "black_track"

    def test_tractor_content_track_present(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        track_producers = {t.get("producer") for t in tractor.findall("track")}
        assert "pl0" in track_producers

    def test_tractor_pair_track_present(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        track_producers = {t.get("producer") for t in tractor.findall("track")}
        assert "pl0_kdpair" in track_producers

    def _tractor_transitions(self, root: ET.Element) -> list[dict[str, str]]:
        tractor = root.find("tractor")
        return [_get_props(t) for t in tractor.findall("transition")]

    def test_video_track_gets_cairoblend(self, tmp_path):
        project = _make_project(
            tracks=[Track(id="pl0", track_type="video")]
        )
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._tractor_transitions(root)
        cairoblend = [t for t in transitions if t.get("mlt_service") == "frei0r.cairoblend"]
        assert len(cairoblend) >= 1

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
        transitions = self._tractor_transitions(root)
        mix = [t for t in transitions if t.get("mlt_service") == "mix"]
        assert len(mix) >= 1

    def test_cairoblend_always_active(self, tmp_path):
        project = _make_project(tracks=[Track(id="pl0", track_type="video")])
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._tractor_transitions(root)
        cb = next(t for t in transitions if t.get("mlt_service") == "frei0r.cairoblend")
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
        transitions = self._tractor_transitions(root)
        mix = next(t for t in transitions if t.get("mlt_service") == "mix")
        assert mix.get("always_active") == "1"
        assert mix.get("sum") == "1"

    def test_transition_a_track_is_0(self, tmp_path):
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._tractor_transitions(root)
        for t in transitions:
            assert t.get("a_track") == "0"

    def test_transition_b_track_matches_content_index(self, tmp_path):
        """b_track must reference the content track's index (1 for the first track)."""
        project = _make_project()
        out = tmp_path / "test.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        transitions = self._tractor_transitions(root)
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
