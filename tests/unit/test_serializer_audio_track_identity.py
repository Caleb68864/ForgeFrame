"""Kdenlive identifies an audio track by ``kdenlive:audio_track``, not by its lanes.

Without the property ``kdenlive --render`` loads the track as video, drops the
clip's audio and renders silence (-91 dB) while melt stays audible. Ground truth:
tests/fixtures/kdenlive_references/cross_dissolve_native.kdenlive, whose audio
track carries it on both playlists and the track-tractor.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from tests._testkit import sequence_project
from workshop_video_brain.core.models.kdenlive import Track
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project

NATIVE = Path(__file__).parents[1] / "fixtures/kdenlive_references/cross_dissolve_native.kdenlive"


def _audio_track_ids(root: ET.Element) -> set[str]:
    """Ids of every element directly marked as belonging to an audio track."""
    return {
        element.get("id")
        for element in root
        if element.tag in ("playlist", "tractor")
        for prop in element.findall("property")
        if prop.get("name") == "kdenlive:audio_track" and prop.text == "1"
    }


def _project_with_audio_track():
    project = sequence_project()
    audio = next((t for t in project.tracks if t.track_type == "audio"), None)
    if audio is None:
        project.tracks.append(Track(id="playlist_audio", track_type="audio"))
        from workshop_video_brain.core.models.kdenlive import Playlist
        project.playlists.append(Playlist(id="playlist_audio"))
        audio = project.tracks[-1]
    return project, audio


def test_native_fixture_marks_playlists_and_tractor():
    """Pins the ground truth the serializer copies."""
    marked = _audio_track_ids(ET.parse(NATIVE).getroot())
    assert {"playlist0", "playlist1", "tractor0"} <= marked


def test_audio_track_marks_both_lanes_and_tractor(tmp_path):
    project, audio = _project_with_audio_track()
    path = tmp_path / "audio.kdenlive"
    serialize_project(project, path)
    marked = _audio_track_ids(ET.parse(path).getroot())
    assert {audio.id, f"{audio.id}_kdpair", f"tractor_{audio.id}"} <= marked


def test_video_tracks_are_not_marked(tmp_path):
    project, audio = _project_with_audio_track()
    path = tmp_path / "audio.kdenlive"
    serialize_project(project, path)
    marked = _audio_track_ids(ET.parse(path).getroot())
    video_ids = {t.id for t in project.tracks if t.track_type == "video"}
    assert video_ids, "the builder must include a video track"
    for track_id in video_ids:
        assert not {track_id, f"{track_id}_kdpair", f"tractor_{track_id}"} & marked


def _speed_project():
    from workshop_video_brain.core.models.kdenlive import (
        KdenliveProject, Playlist, PlaylistEntry, Producer,
    )

    base = Producer(id="clip", resource="/m/a.mp4", properties={"resource": "/m/a.mp4", "length": "100"})
    warp = Producer(
        id="clip_tw2", resource="2:/m/a.mp4",
        properties={"mlt_service": "timewarp", "resource": "2:/m/a.mp4", "warp_speed": "2",
                    "warp_resource": "/m/a.mp4", "length": "50"},
    )
    entry = PlaylistEntry(producer_id="clip_tw2", in_point=0, out_point=49)
    return KdenliveProject(
        producers=[base, warp],
        playlists=[Playlist(id="v", entries=[entry]), Playlist(id="a", entries=[entry.model_copy()])],
        tracks=[Track(id="v", track_type="video"), Track(id="a", track_type="audio")],
    )


def _entry_producer(root: ET.Element, playlist_id: str) -> str:
    return root.find(f"playlist[@id='{playlist_id}']/entry").get("producer")


def test_speed_clip_on_both_tracks_gets_a_producer_per_track(tmp_path):
    """Kdenlive disables both streams of a timewarp producer shared across tracks."""
    path = tmp_path / "speed.kdenlive"
    serialize_project(_speed_project(), path)
    root = ET.parse(path).getroot()
    video, audio = _entry_producer(root, "v"), _entry_producer(root, "a")
    assert video == "clip_tw2"
    assert audio != video
    twin = root.find(f"producer[@id='{audio}']")
    assert {p.get("name"): p.text for p in twin.findall("property")}["warp_speed"] == "2"
    props = {
        element.get("id"): {p.get("name"): p.text for p in element.findall("property")}
        for element in root.findall("producer") if element.get("id") in (video, audio)
    }
    assert props[video]["kdenlive:id"] == props[audio]["kdenlive:id"]
    assert audio not in {e.get("producer") for e in root.findall("playlist[@id='main_bin']/entry")}


def test_speed_clip_on_one_track_stays_a_single_producer(tmp_path):
    project = _speed_project()
    project.playlists[1].entries.clear()
    path = tmp_path / "speed.kdenlive"
    serialize_project(project, path)
    root = ET.parse(path).getroot()
    assert [p.get("id") for p in root.findall("producer") if "clip_tw2" in p.get("id")] == ["clip_tw2"]


def test_round_trip_is_stable_and_leaves_no_stray_root_properties(tmp_path):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project

    first = tmp_path / "first.kdenlive"
    second = tmp_path / "second.kdenlive"
    serialize_project(_speed_project(), first)
    parsed = parse_project(first)
    assert {p.id for p in parsed.producers} == {"clip", "clip_tw2"}
    assert {e.producer_id for pl in parsed.playlists for e in pl.entries if e.producer_id} == {"clip_tw2"}
    serialize_project(parsed, second)
    root = ET.parse(second).getroot()
    assert [c.get("name") for c in root if c.tag == "property"] == []
    assert [p.get("id") for p in ET.parse(first).getroot().findall("producer")] == [
        p.get("id") for p in root.findall("producer")
    ]
    assert _audio_track_ids(root) == {"a", "a_kdpair", "tractor_a"}

