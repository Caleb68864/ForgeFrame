"""Structural assertions on the serializer output against the Kdenlive 25.x shape.

Reference fixture: ``tests/fixtures/kdenlive_references/single_clip_kdenlive_native.kdenlive``
This file was saved by Kdenlive 25.08.3 / MLT 7.33.0 after dragging in one clip.
Our serializer must produce a document with the same critical structural pieces
so that Kdenlive can open it.

The tests here are intentionally structural, not byte-equal: UUIDs, integer ids,
default trackheights, etc. are allowed to differ. What must NOT differ:

* Per-track ``<tractor>`` (each timeline track is its own tractor with 2 playlists).
* Internal audio filters (volume / panner / audiolevel) on each audio track tractor.
* A UUID-id'd "main sequence" ``<tractor>`` with ``kdenlive:uuid`` and the
  required ``kdenlive:sequenceproperties.*`` keys.
* ``main_bin`` ``<playlist>`` carries the doc-properties block including
  ``kdenlive:docproperties.uuid``, ``opensequences``, and ``activetimeline``,
  plus a ``<entry>`` for the sequence tractor and one for each user clip.
* A final ``<tractor>`` with ``kdenlive:projectTractor=1`` wrapping the
  sequence as its single ``<track>``.
"""
from __future__ import annotations

import re
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
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

_UUID_RE = re.compile(
    r"^\{[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\}$"
)


def _props(elem: ET.Element) -> dict[str, str]:
    return {
        c.get("name", ""): (c.text or "")
        for c in elem
        if c.tag == "property"
    }


def _build_one_clip_project() -> KdenliveProject:
    """One video clip on a single video track plus an empty audio track."""
    return KdenliveProject(
        version="7",
        title="single clip",
        profile=ProjectProfile(width=1920, height=1080, fps=29.97, colorspace="709"),
        producers=[
            Producer(
                id="prod0",
                resource="C:/media/clip.mp4",
                properties={
                    "resource": "C:/media/clip.mp4",
                    "mlt_service": "avformat-novalidate",
                    "audio_index": "1",
                    "video_index": "0",
                },
            )
        ],
        playlists=[
            Playlist(
                id="pl_v1",
                entries=[PlaylistEntry(producer_id="prod0", in_point=0, out_point=149)],
            ),
            Playlist(id="pl_a1"),
        ],
        tracks=[
            Track(id="pl_v1", track_type="video"),
            Track(id="pl_a1", track_type="audio"),
        ],
        tractor={"id": "main_seq", "in": "0", "out": "149"},
    )


@pytest.fixture
def serialized_root(tmp_path) -> ET.Element:
    project = _build_one_clip_project()
    out = tmp_path / "single.kdenlive"
    serialize_project(project, out)
    return ET.parse(out).getroot()


# ---------------------------------------------------------------------------
# Per-track tractors
# ---------------------------------------------------------------------------


class TestPerTrackTractors:
    def test_each_user_track_has_its_own_tractor(self, serialized_root):
        tractors = serialized_root.findall("tractor")
        # We expect at least: 1 per user track (2) + 1 main sequence + 1 project wrapper
        assert len(tractors) >= 4, (
            f"Expected ≥4 tractors (per-track + sequence + wrapper); got {len(tractors)}"
        )

    def test_each_track_tractor_has_two_playlists(self, serialized_root):
        # Each track tractor must reference exactly 2 playlists via <track> children
        # and they must be playlists, not other tractors.
        tractors = serialized_root.findall("tractor")
        playlist_ids = {p.get("id") for p in serialized_root.findall("playlist")}
        per_track = [
            t for t in tractors
            if all(
                tr.get("producer") in playlist_ids
                for tr in t.findall("track")
            ) and len(t.findall("track")) == 2
        ]
        assert len(per_track) >= 2, (
            f"Expected ≥2 per-track tractors with 2 playlist tracks each; got {len(per_track)}"
        )

    def test_audio_track_tractor_has_required_internal_filters(self, serialized_root):
        """Every audio track tractor must carry volume / panner / audiolevel filters."""
        services_per_audio_tractor: list[set[str]] = []
        for tractor in serialized_root.findall("tractor"):
            tracks = tractor.findall("track")
            if not tracks or len(tracks) != 2:
                continue
            # An audio track tractor hides video on its sub-playlists
            if not all(t.get("hide") == "video" for t in tracks):
                continue
            services = {
                _props(f).get("mlt_service", "")
                for f in tractor.findall("filter")
            }
            services_per_audio_tractor.append(services)

        assert services_per_audio_tractor, "No audio track tractor found"
        for services in services_per_audio_tractor:
            assert "volume" in services
            assert "panner" in services
            assert "audiolevel" in services


# ---------------------------------------------------------------------------
# Main sequence tractor
# ---------------------------------------------------------------------------


class TestMainSequenceTractor:
    def _find_main_sequence(self, root: ET.Element) -> ET.Element:
        for tractor in root.findall("tractor"):
            tractor_id = tractor.get("id", "")
            if _UUID_RE.match(tractor_id):
                return tractor
        pytest.fail("No tractor with UUID id found (main sequence missing)")

    def test_main_sequence_has_uuid_id(self, serialized_root):
        seq = self._find_main_sequence(serialized_root)
        assert _UUID_RE.match(seq.get("id", ""))

    def test_main_sequence_has_kdenlive_uuid_property(self, serialized_root):
        seq = self._find_main_sequence(serialized_root)
        props = _props(seq)
        assert _UUID_RE.match(props.get("kdenlive:uuid", ""))
        assert props["kdenlive:uuid"] == seq.get("id")

    def test_main_sequence_has_required_sequenceproperties(self, serialized_root):
        seq = self._find_main_sequence(serialized_root)
        props = _props(seq)
        required = {
            "kdenlive:sequenceproperties.hasAudio",
            "kdenlive:sequenceproperties.hasVideo",
            "kdenlive:sequenceproperties.activeTrack",
            "kdenlive:sequenceproperties.tracksCount",
            "kdenlive:sequenceproperties.documentuuid",
        }
        missing = required - props.keys()
        assert not missing, f"Main sequence missing seq-properties: {missing}"

    def test_main_sequence_producer_type_is_17(self, serialized_root):
        seq = self._find_main_sequence(serialized_root)
        assert _props(seq).get("kdenlive:producer_type") == "17"

    def test_main_sequence_lists_all_track_tractors(self, serialized_root):
        """The main sequence must include each per-track tractor as a <track>."""
        seq = self._find_main_sequence(serialized_root)
        track_refs = {t.get("producer") for t in seq.findall("track")}
        per_track_tractor_ids = set()
        playlist_ids = {p.get("id") for p in serialized_root.findall("playlist")}
        for tractor in serialized_root.findall("tractor"):
            if tractor is seq:
                continue
            tracks = tractor.findall("track")
            if (
                len(tracks) == 2
                and all(t.get("producer") in playlist_ids for t in tracks)
            ):
                per_track_tractor_ids.add(tractor.get("id"))
        # Every per-track tractor must appear in the sequence's tracks
        assert per_track_tractor_ids.issubset(track_refs), (
            f"Sequence missing per-track tractor refs: {per_track_tractor_ids - track_refs}"
        )


# ---------------------------------------------------------------------------
# main_bin docproperties + sequence references
# ---------------------------------------------------------------------------


class TestMainBinDocProperties:
    def _main_bin(self, root: ET.Element) -> ET.Element:
        mb = root.find("./playlist[@id='main_bin']")
        assert mb is not None
        return mb

    def test_main_bin_doc_uuid_matches_main_sequence(self, serialized_root):
        mb = self._main_bin(serialized_root)
        doc_uuid = _props(mb).get("kdenlive:docproperties.uuid", "")
        seq_ids = {
            t.get("id")
            for t in serialized_root.findall("tractor")
            if _UUID_RE.match(t.get("id", ""))
        }
        assert doc_uuid in seq_ids, (
            f"docproperties.uuid={doc_uuid!r} does not match any sequence tractor id"
        )

    def test_main_bin_has_opensequences_and_activetimeline(self, serialized_root):
        mb = self._main_bin(serialized_root)
        props = _props(mb)
        assert _UUID_RE.match(
            props.get("kdenlive:docproperties.opensequences", "")
        )
        assert _UUID_RE.match(
            props.get("kdenlive:docproperties.activetimeline", "")
        )

    def test_main_bin_has_entry_for_main_sequence(self, serialized_root):
        mb = self._main_bin(serialized_root)
        entry_refs = {e.get("producer") for e in mb.findall("entry")}
        seq_ids = {
            t.get("id")
            for t in serialized_root.findall("tractor")
            if _UUID_RE.match(t.get("id", ""))
        }
        # The sequence must be referenced at least once in main_bin
        assert seq_ids & entry_refs, (
            "main_bin must contain an <entry> for the main sequence tractor"
        )

    def test_main_bin_has_entry_for_each_user_producer(self, serialized_root):
        mb = self._main_bin(serialized_root)
        entry_refs = {e.get("producer") for e in mb.findall("entry")}
        # main_bin entries reference the bin twin of each chain (id + "_bin")
        # for avformat media; non-chain producers (color/title) reference id.
        assert "prod0_bin" in entry_refs or "prod0" in entry_refs

    def test_main_bin_xml_retain_set(self, serialized_root):
        mb = self._main_bin(serialized_root)
        assert _props(mb).get("xml_retain") == "1"


# ---------------------------------------------------------------------------
# Project tractor wrapper
# ---------------------------------------------------------------------------


class TestProjectTractorWrapper:
    def test_project_tractor_exists(self, serialized_root):
        wrappers = [
            t
            for t in serialized_root.findall("tractor")
            if _props(t).get("kdenlive:projectTractor") == "1"
        ]
        assert len(wrappers) == 1, (
            f"Expected exactly one tractor with kdenlive:projectTractor=1; got {len(wrappers)}"
        )

    def test_project_tractor_wraps_main_sequence(self, serialized_root):
        wrapper = next(
            t
            for t in serialized_root.findall("tractor")
            if _props(t).get("kdenlive:projectTractor") == "1"
        )
        seq_ids = {
            t.get("id")
            for t in serialized_root.findall("tractor")
            if _UUID_RE.match(t.get("id", ""))
        }
        wrapper_track_refs = {t.get("producer") for t in wrapper.findall("track")}
        assert wrapper_track_refs & seq_ids, (
            f"Project tractor must wrap the main sequence; "
            f"wrapper tracks={wrapper_track_refs} seq_ids={seq_ids}"
        )


# ---------------------------------------------------------------------------
# Reference cross-check (golden-file inspired)
# ---------------------------------------------------------------------------


class TestReferenceFixtureSatisfiesAssertions:
    """Sanity: the same assertions must pass on the real Kdenlive-saved file.

    If these fail we have wrong assumptions about Kdenlive's shape, not bugs in
    our serializer. Skip if the reference fixture is not present in the repo.
    """

    REFERENCE = (
        Path(__file__).resolve().parents[1]
        / "fixtures"
        / "kdenlive_references"
        / "single_clip_kdenlive_native.kdenlive"
    )

    @pytest.fixture
    def reference_root(self):
        if not self.REFERENCE.exists():
            pytest.skip(f"Reference fixture missing: {self.REFERENCE}")
        return ET.parse(self.REFERENCE).getroot()

    def test_reference_has_main_sequence_tractor(self, reference_root):
        seqs = [
            t for t in reference_root.findall("tractor")
            if _UUID_RE.match(t.get("id", ""))
        ]
        assert len(seqs) >= 1

    def test_reference_has_project_tractor_wrapper(self, reference_root):
        wrappers = [
            t for t in reference_root.findall("tractor")
            if _props(t).get("kdenlive:projectTractor") == "1"
        ]
        assert len(wrappers) == 1

    def test_reference_has_per_track_tractors_with_audio_filters(self, reference_root):
        playlist_ids = {p.get("id") for p in reference_root.findall("playlist")}
        audio_track_tractors_with_filters = 0
        for tractor in reference_root.findall("tractor"):
            tracks = tractor.findall("track")
            if (
                len(tracks) == 2
                and all(t.get("producer") in playlist_ids for t in tracks)
                and all(t.get("hide") == "video" for t in tracks)
            ):
                services = {
                    _props(f).get("mlt_service", "")
                    for f in tractor.findall("filter")
                }
                if {"volume", "panner", "audiolevel"} <= services:
                    audio_track_tractors_with_filters += 1
        assert audio_track_tractors_with_filters >= 1
