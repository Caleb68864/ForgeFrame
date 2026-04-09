"""Integration tests for Kdenlive bin registration round-trip (sub-spec 4).

End-to-end: create a project → serialize → validate structure → parse back → compare.

Covers:
- Projects with video + title clips → all producers in main_bin
- All producers have kdenlive:uuid, kdenlive:id, kdenlive:clip_type
- black_track exists, paired playlists exist
- Internal transitions present (mix for audio, frei0r.cairoblend for video)
- Round-trip: serialize → parse → serialize produces structurally equivalent XML
- Opaque elements survive round-trip
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    Guide,
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

_UUID_RE = re.compile(r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$")


def _props(elem: ET.Element) -> dict[str, str]:
    return {
        child.get("name", ""): (child.text or "")
        for child in elem
        if child.tag == "property"
    }


def _make_mixed_project() -> KdenliveProject:
    """Project with 3 video clips + 2 title clips, two timeline tracks."""
    return KdenliveProject(
        version="7",
        title="Mixed Bin Test",
        profile=ProjectProfile(width=1920, height=1080, fps=25.0, colorspace="709"),
        producers=[
            Producer(
                id="vid0",
                resource="/media/clip1.mp4",
                properties={"resource": "/media/clip1.mp4", "mlt_service": "avformat", "length": "100"},
            ),
            Producer(
                id="vid1",
                resource="/media/clip2.mp4",
                properties={"resource": "/media/clip2.mp4", "mlt_service": "avformat", "length": "150"},
            ),
            Producer(
                id="vid2",
                resource="/media/clip3.mp4",
                properties={"resource": "/media/clip3.mp4", "mlt_service": "avformat", "length": "200"},
            ),
            Producer(
                id="title0",
                resource="",
                properties={"mlt_service": "kdenlivetitle", "length": "50"},
            ),
            Producer(
                id="title1",
                resource="",
                properties={"mlt_service": "kdenlivetitle", "length": "75"},
            ),
        ],
        playlists=[
            Playlist(
                id="pl_video",
                entries=[
                    PlaylistEntry(producer_id="vid0", in_point=0, out_point=99),
                    PlaylistEntry(producer_id="vid1", in_point=0, out_point=149),
                    PlaylistEntry(producer_id="vid2", in_point=0, out_point=199),
                ],
            ),
            Playlist(
                id="pl_titles",
                entries=[
                    PlaylistEntry(producer_id="title0", in_point=0, out_point=49),
                    PlaylistEntry(producer_id="title1", in_point=0, out_point=74),
                ],
            ),
        ],
        tracks=[
            Track(id="pl_video", track_type="video"),
            Track(id="pl_titles", track_type="video"),
        ],
        tractor={"id": "tractor0", "in": "0", "out": "449"},
        guides=[Guide(position=100, label="Act 1", category="chapter")],
        opaque_elements=[
            OpaqueElement(
                tag="kdenlive_opaque_data",
                xml_string="<kdenlive_opaque_data>preserved</kdenlive_opaque_data>",
            )
        ],
    )


class TestMainBinContainsAllProducers:
    def test_all_producers_in_main_bin(self, tmp_path):
        """All 5 producers (3 video + 2 title) must appear as entries in main_bin."""
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        assert main_bin is not None
        entry_refs = {e.get("producer") for e in main_bin.findall("entry")}
        expected = {"vid0", "vid1", "vid2", "title0", "title1"}
        assert expected == entry_refs

    def test_main_bin_count_matches_producers(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        main_bin = root.find("./playlist[@id='main_bin']")
        entries = main_bin.findall("entry")
        assert len(entries) == len(project.producers)


class TestProducerKdenliveMetadata:
    def _all_user_producers(self, root: ET.Element, project: KdenliveProject) -> list[ET.Element]:
        user_ids = {p.id for p in project.producers}
        return [p for p in root.findall("producer") if p.get("id") in user_ids]

    def test_all_producers_have_uuid(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for prod in self._all_user_producers(root, project):
            assert "kdenlive:uuid" in _props(prod), f"Missing uuid on {prod.get('id')}"

    def test_all_uuids_valid_format(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for prod in self._all_user_producers(root, project):
            uid = _props(prod).get("kdenlive:uuid", "")
            assert _UUID_RE.match(uid), f"Bad UUID on {prod.get('id')}: {uid}"

    def test_all_producers_have_kdenlive_id(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for prod in self._all_user_producers(root, project):
            assert "kdenlive:id" in _props(prod)

    def test_kdenlive_ids_unique(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        ids = [
            _props(p).get("kdenlive:id")
            for p in self._all_user_producers(root, project)
        ]
        assert len(ids) == len(set(ids)), "kdenlive:id values are not unique"

    def test_all_producers_have_clip_type(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for prod in self._all_user_producers(root, project):
            assert "kdenlive:clip_type" in _props(prod)

    def test_video_producers_clip_type_0(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for pid in ("vid0", "vid1", "vid2"):
            prod = root.find(f"./producer[@id='{pid}']")
            assert _props(prod).get("kdenlive:clip_type") == "0", f"Expected 0 for {pid}"

    def test_title_producers_clip_type_2(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        for pid in ("title0", "title1"):
            prod = root.find(f"./producer[@id='{pid}']")
            assert _props(prod).get("kdenlive:clip_type") == "2", f"Expected 2 for {pid}"


class TestInfrastructureElements:
    def test_black_track_exists(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.find("./producer[@id='black_track']") is not None

    def test_paired_playlists_exist(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        assert root.find("./playlist[@id='pl_video_kdpair']") is not None
        assert root.find("./playlist[@id='pl_titles_kdpair']") is not None

    def test_tractor_has_black_track_first(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        tracks = tractor.findall("track")
        assert tracks[0].get("producer") == "black_track"

    def test_tractor_transitions_present(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        transitions = tractor.findall("transition")
        assert len(transitions) >= 2  # one per video track

    def test_cairoblend_transitions_for_video_tracks(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "mixed.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        cb = [
            t for t in tractor.findall("transition")
            if _props(t).get("mlt_service") == "frei0r.cairoblend"
        ]
        # 2 video tracks → 2 cairoblend transitions
        assert len(cb) == 2

    def test_mix_transition_for_audio_track(self, tmp_path):
        project = KdenliveProject(
            title="Audio Test",
            profile=ProjectProfile(),
            producers=[
                Producer(id="aud0", resource="/audio.mp3", properties={"resource": "/audio.mp3"}),
            ],
            playlists=[
                Playlist(id="apl0", entries=[PlaylistEntry(producer_id="aud0", in_point=0, out_point=99)])
            ],
            tracks=[Track(id="apl0", track_type="audio")],
            tractor={"id": "tractor0", "in": "0", "out": "99"},
        )
        out = tmp_path / "audio.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        mix = [
            t for t in tractor.findall("transition")
            if _props(t).get("mlt_service") == "mix"
        ]
        assert len(mix) == 1

    def test_mix_properties_via_props(self, tmp_path):
        """mix transition has always_active=1 and sum=1."""
        project = KdenliveProject(
            title="Audio Test",
            profile=ProjectProfile(),
            producers=[
                Producer(id="aud0", resource="/audio.mp3", properties={"resource": "/audio.mp3"}),
            ],
            playlists=[
                Playlist(id="apl0", entries=[PlaylistEntry(producer_id="aud0", in_point=0, out_point=99)])
            ],
            tracks=[Track(id="apl0", track_type="audio")],
            tractor={"id": "tractor0", "in": "0", "out": "99"},
        )
        out = tmp_path / "audio.kdenlive"
        serialize_project(project, out)
        root = ET.parse(out).getroot()
        tractor = root.find("tractor")
        mix_props = [
            _props(t) for t in tractor.findall("transition")
            if _props(t).get("mlt_service") == "mix"
        ]
        assert len(mix_props) == 1
        assert mix_props[0].get("always_active") == "1"
        assert mix_props[0].get("sum") == "1"


class TestRoundTrip:
    def test_serialize_parse_title_preserved(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        assert restored.title == project.title

    def test_serialize_parse_producer_count_preserved(self, tmp_path):
        """After serialize → parse, user producers are counted correctly (infrastructure filtered)."""
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        assert len(restored.producers) == len(project.producers)

    def test_serialize_parse_producer_ids_preserved(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        orig_ids = {p.id for p in project.producers}
        rest_ids = {p.id for p in restored.producers}
        assert orig_ids == rest_ids

    def test_serialize_parse_playlist_count_preserved(self, tmp_path):
        """After serialize → parse, user playlists are counted correctly (main_bin + pairs filtered)."""
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        assert len(restored.playlists) == len(project.playlists)

    def test_serialize_parse_playlist_entries_preserved(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        orig_pl = next(pl for pl in project.playlists if pl.id == "pl_video")
        rest_pl = next(pl for pl in restored.playlists if pl.id == "pl_video")
        assert len(rest_pl.entries) == len(orig_pl.entries)

    def test_serialize_parse_guides_preserved(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        assert len(restored.guides) == len(project.guides)
        orig_positions = {g.position for g in project.guides}
        rest_positions = {g.position for g in restored.guides}
        assert orig_positions == rest_positions

    def test_opaque_elements_survive_round_trip(self, tmp_path):
        project = _make_mixed_project()
        out = tmp_path / "rt.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        opaque_tags = {o.tag for o in restored.opaque_elements}
        assert "kdenlive_opaque_data" in opaque_tags

    def test_double_round_trip_consistent(self, tmp_path):
        """serialize → parse → serialize produces structurally equivalent XML."""
        project = _make_mixed_project()
        out1 = tmp_path / "first.kdenlive"
        out2 = tmp_path / "second.kdenlive"
        serialize_project(project, out1)
        restored = parse_project(out1)
        serialize_project(restored, out2)

        root1 = ET.parse(out1).getroot()
        root2 = ET.parse(out2).getroot()

        # Same producer ids present (excluding infrastructure)
        user_ids = {p.id for p in project.producers}
        ids1 = {p.get("id") for p in root1.findall("producer")} & user_ids
        ids2 = {p.get("id") for p in root2.findall("producer")} & user_ids
        assert ids1 == ids2

        # main_bin present in both
        assert root1.find("./playlist[@id='main_bin']") is not None
        assert root2.find("./playlist[@id='main_bin']") is not None

        # black_track present in both
        assert root1.find("./producer[@id='black_track']") is not None
        assert root2.find("./producer[@id='black_track']") is not None


class TestOpaqueElementRoundTrip:
    def test_filter_and_transition_opaques_survive(self, tmp_path):
        """OpaqueElement objects (filters, custom xml) added before serialization must survive."""
        project = KdenliveProject(
            title="Opaque Test",
            profile=ProjectProfile(width=1920, height=1080, fps=25.0),
            producers=[
                Producer(id="p0", resource="/clip.mp4", properties={"resource": "/clip.mp4"})
            ],
            playlists=[
                Playlist(id="pl0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=99)])
            ],
            tracks=[Track(id="pl0", track_type="video")],
            tractor={"id": "tractor0", "in": "0", "out": "99"},
            opaque_elements=[
                OpaqueElement(
                    tag="my_custom_filter",
                    xml_string='<my_custom_filter id="mf0"><param>value</param></my_custom_filter>',
                ),
                OpaqueElement(
                    tag="kdenlive_special",
                    xml_string="<kdenlive_special>data</kdenlive_special>",
                ),
            ],
        )
        out = tmp_path / "opaque.kdenlive"
        serialize_project(project, out)
        restored = parse_project(out)
        opaque_tags = {o.tag for o in restored.opaque_elements}
        assert "my_custom_filter" in opaque_tags
        assert "kdenlive_special" in opaque_tags

    def test_opaque_content_preserved(self, tmp_path):
        project = KdenliveProject(
            title="Content Test",
            profile=ProjectProfile(),
            producers=[
                Producer(id="p0", resource="/clip.mp4", properties={"resource": "/clip.mp4"})
            ],
            playlists=[
                Playlist(id="pl0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=49)])
            ],
            tracks=[Track(id="pl0", track_type="video")],
            tractor={"id": "tractor0", "in": "0", "out": "49"},
            opaque_elements=[
                OpaqueElement(
                    tag="preserved_data",
                    xml_string="<preserved_data>unique_marker_12345</preserved_data>",
                )
            ],
        )
        out = tmp_path / "content.kdenlive"
        serialize_project(project, out)
        content = out.read_text(encoding="utf-8")
        assert "unique_marker_12345" in content

        restored = parse_project(out)
        opaque = next(o for o in restored.opaque_elements if o.tag == "preserved_data")
        assert "unique_marker_12345" in opaque.xml_string
