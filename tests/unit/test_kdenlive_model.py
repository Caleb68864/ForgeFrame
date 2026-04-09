"""Tests for KdenliveProject and sub-models (MD-03)."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

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


# ---------------------------------------------------------------------------
# ProjectProfile
# ---------------------------------------------------------------------------

def test_project_profile_defaults():
    p = ProjectProfile()
    assert p.width == 1920
    assert p.height == 1080
    assert p.fps == 25.0
    assert p.colorspace is None


def test_project_profile_all_fields():
    p = ProjectProfile(width=3840, height=2160, fps=60.0, colorspace="rec709")
    d = p.model_dump()
    assert d["width"] == 3840
    assert d["height"] == 2160
    assert d["fps"] == 60.0
    assert d["colorspace"] == "rec709"


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------

def test_producer_required():
    with pytest.raises(ValidationError):
        Producer()  # type: ignore[call-arg]


def test_producer_defaults():
    p = Producer(id="clip1")
    assert p.resource == ""
    assert p.properties == {}


def test_producer_properties():
    p = Producer(id="clip2", resource="/path/to/file.mp4", properties={"mlt_service": "avformat"})
    d = p.model_dump()
    assert d["properties"] == {"mlt_service": "avformat"}
    p2 = Producer.model_validate(d)
    assert p2.properties == {"mlt_service": "avformat"}


# ---------------------------------------------------------------------------
# PlaylistEntry
# ---------------------------------------------------------------------------

def test_playlist_entry_gap():
    e = PlaylistEntry()
    assert e.producer_id == ""


def test_playlist_entry_all_fields():
    e = PlaylistEntry(producer_id="clip1", in_point=10, out_point=50)
    d = e.model_dump()
    assert d["producer_id"] == "clip1"
    assert d["in_point"] == 10
    assert d["out_point"] == 50
    e2 = PlaylistEntry.model_validate(d)
    assert e2 == e


# ---------------------------------------------------------------------------
# Playlist
# ---------------------------------------------------------------------------

def test_playlist_defaults():
    p = Playlist(id="main")
    assert p.entries == []


def test_playlist_with_entries():
    entries = [PlaylistEntry(producer_id="c1", in_point=0, out_point=25)]
    p = Playlist(id="main", entries=entries)
    p2 = Playlist.from_json(p.to_json())
    assert len(p2.entries) == 1
    assert p2.entries[0].producer_id == "c1"


# ---------------------------------------------------------------------------
# Track
# ---------------------------------------------------------------------------

def test_track_defaults():
    t = Track(id="v0")
    assert t.track_type == "video"
    assert t.name is None


def test_track_audio():
    t = Track(id="a0", track_type="audio")
    assert t.track_type == "audio"


# ---------------------------------------------------------------------------
# Guide
# ---------------------------------------------------------------------------

def test_guide_required():
    with pytest.raises(ValidationError):
        Guide()  # type: ignore[call-arg]


def test_guide_optional_none():
    g = Guide(position=100)
    assert g.category is None
    assert g.comment is None


# ---------------------------------------------------------------------------
# OpaqueElement
# ---------------------------------------------------------------------------

def test_opaque_element_required():
    with pytest.raises(ValidationError):
        OpaqueElement()  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        OpaqueElement(tag="mlt")  # type: ignore[call-arg]

    with pytest.raises(ValidationError):
        OpaqueElement(xml_string="<foo/>")  # type: ignore[call-arg]


def test_opaque_element_position_hint_none():
    o = OpaqueElement(tag="mlt", xml_string="<mlt/>")
    assert o.position_hint is None


# ---------------------------------------------------------------------------
# KdenliveProject
# ---------------------------------------------------------------------------

def test_kdenlive_project_defaults():
    kp = KdenliveProject()
    assert kp.version == "7"
    assert kp.title == ""
    assert kp.producers == []
    assert kp.tracks == []
    assert kp.playlists == []
    assert kp.guides == []
    assert kp.opaque_elements == []
    assert kp.tractor is None


def test_kdenlive_project_full():
    producer = Producer(id="clip1", resource="/path/video.mp4")
    track = Track(id="v0")
    entry = PlaylistEntry(producer_id="clip1", in_point=0, out_point=100)
    playlist = Playlist(id="main", entries=[entry])
    guide = Guide(position=50, label="Start")
    opaque = OpaqueElement(tag="filter", xml_string="<filter/>")

    kp = KdenliveProject(
        version="7",
        title="My Project",
        producers=[producer],
        tracks=[track],
        playlists=[playlist],
        guides=[guide],
        opaque_elements=[opaque],
        tractor={"foo": "bar"},
    )
    kp2 = KdenliveProject.from_json(kp.to_json())
    assert kp2.title == "My Project"
    assert len(kp2.producers) == 1
    assert len(kp2.tracks) == 1
    assert len(kp2.playlists) == 1
    assert len(kp2.guides) == 1
    assert len(kp2.opaque_elements) == 1
    assert kp2.tractor == {"foo": "bar"}


def test_kdenlive_project_tractor_dict():
    kp = KdenliveProject(tractor={"a_track": "0", "b_track": "1"})
    kp2 = KdenliveProject.from_json(kp.to_json())
    assert kp2.tractor == {"a_track": "0", "b_track": "1"}


def test_kdenlive_project_yaml_round_trip():
    producer = Producer(id="p1", resource="/foo.mp4")
    kp = KdenliveProject(title="YAML Test", producers=[producer])
    kp2 = KdenliveProject.from_yaml(kp.to_yaml())
    assert kp2.title == "YAML Test"
    assert len(kp2.producers) == 1
    assert kp2.producers[0].id == "p1"
