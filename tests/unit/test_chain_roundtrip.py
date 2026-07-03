"""Round-trip tests for ``<chain>`` / ``<link>`` serialization + parsing.

The native timeremap engine needs a producer that serializes as a ``<chain>``
with a ``<link mlt_service="timeremap">`` child; the parser must read it back
into a :class:`Producer` with ``links``. These tests pin that round-trip.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Link,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)


def _chain_project() -> KdenliveProject:
    p = KdenliveProject(
        version="7", title="chain",
        profile=ProjectProfile(width=320, height=180, fps=25.0),
    )
    p.producers = [
        Producer(
            id="chain0",
            resource="src.mp4",
            properties={"mlt_service": "avformat", "length": "125"},
            links=[
                Link(
                    mlt_service="timeremap",
                    properties={"speed_map": "0=2;24=2;25=0.5;124=0.5", "image_mode": "nearest", "pitch": "0"},
                )
            ],
            chain_out=124,
        )
    ]
    p.tracks = [Track(id="pv", track_type="video")]
    p.playlists = [
        Playlist(id="pv", entries=[PlaylistEntry(producer_id="chain0", in_point=0, out_point=124)])
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "124"}
    return p


def test_chain_serializes_as_chain_with_link(tmp_path: Path):
    path = tmp_path / "chain.kdenlive"
    serialize_project(_chain_project(), path)
    xml = path.read_text()
    assert "<chain " in xml
    assert 'out="124"' in xml
    assert '<link mlt_service="timeremap">' in xml
    assert "speed_map" in xml
    # A plain producer must NOT be emitted for this producer.
    assert '<producer id="chain0"' not in xml


def test_chain_round_trips_into_links(tmp_path: Path):
    path = tmp_path / "chain.kdenlive"
    serialize_project(_chain_project(), path)
    reparsed = parse_project(path)
    prod = next(p for p in reparsed.producers if p.id == "chain0")
    assert prod.resource == "src.mp4"
    assert prod.chain_out == 124
    assert len(prod.links) == 1
    link = prod.links[0]
    assert link.mlt_service == "timeremap"
    assert link.properties["speed_map"] == "0=2;24=2;25=0.5;124=0.5"
    assert link.properties["image_mode"] == "nearest"


def test_plain_producer_still_serializes_as_producer(tmp_path: Path):
    p = KdenliveProject(
        version="7", title="plain",
        profile=ProjectProfile(width=320, height=180, fps=25.0),
    )
    p.producers = [Producer(id="producer_0", resource="0xff0000ff", properties={"mlt_service": "color"})]
    p.tracks = [Track(id="pv", track_type="video")]
    p.playlists = [Playlist(id="pv", entries=[PlaylistEntry(producer_id="producer_0", in_point=0, out_point=49)])]
    p.tractor = {"id": "tractor0", "in": "0", "out": "49"}
    path = tmp_path / "plain.kdenlive"
    serialize_project(p, path)
    xml = path.read_text()
    assert '<producer id="producer_0"' in xml
    assert "<chain" not in xml
    reparsed = parse_project(path)
    prod = next(pr for pr in reparsed.producers if pr.id == "producer_0")
    assert prod.links == []
    assert prod.chain_out is None
