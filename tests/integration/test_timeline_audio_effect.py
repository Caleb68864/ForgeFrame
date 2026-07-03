"""Integration round-trips for track-level audio filters.

Exercises the intent -> patcher -> serializer -> parser chain (no melt): a
track filter must nest inside the track's ``<playlist>`` on write and survive a
parse/serialize round-trip without loss. The render-level proofs (melt+astats)
live in ``tests/integration/external/test_track_audio.py``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import (
    AddTrackFilter,
    ClearTrackFilters,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project


def _project() -> KdenliveProject:
    prod = Producer(
        id="p0",
        resource="/tmp/a.wav",
        properties={"resource": "/tmp/a.wav", "mlt_service": "avformat", "length": "100"},
    )
    return KdenliveProject(
        title="t",
        profile=ProjectProfile(width=320, height=240, fps=25.0),
        producers=[prod],
        tracks=[
            Track(id="pl_v", track_type="video"),
            Track(id="pl_a", track_type="audio"),
        ],
        playlists=[
            Playlist(id="pl_v", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=49)]),
            Playlist(id="pl_a", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=49)]),
        ],
        tractor={"id": "tractor0", "in": "0", "out": "49"},
    )


def _playlist_filters(xml_path, playlist_id):
    root = ET.parse(xml_path).getroot()
    for pl in root.findall("playlist"):
        if pl.get("id") == playlist_id:
            return pl.findall("filter")
    return []


def test_track_volume_nests_in_playlist(tmp_path):
    proj = patcher.patch_project(
        _project(),
        [AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="volume",
                        filter_id="vol1", properties={"level": "-12"})],
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(proj, out)

    filters = _playlist_filters(out, "pl_a")
    assert len(filters) == 1
    f = filters[0]
    assert f.get("mlt_service") == "volume"
    # the association attribute must NOT leak into the emitted XML
    assert f.get("track") is None and f.get("clip_index") is None
    level = next(p for p in f if p.get("name") == "level")
    assert level.text == "-12"
    # video track has no filter
    assert _playlist_filters(out, "pl_v") == []


def test_track_filter_roundtrips(tmp_path):
    proj = patcher.patch_project(
        _project(),
        [AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="volume",
                        filter_id="vol1", properties={"level": "-6"})],
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(proj, out)

    # parse it back -- the track filter must be recovered as a track-scoped
    # opaque (track attr, no clip_index)
    reparsed = parse_project(out)
    tfs = [e for e in reparsed.opaque_elements if e.tag == "filter"]
    assert len(tfs) == 1
    root = ET.fromstring(tfs[0].xml_string)
    assert root.get("track") == "1"
    assert root.get("clip_index") is None

    # re-serialize -- still exactly one filter on the audio playlist (no dup/loss)
    out2 = tmp_path / "p2.kdenlive"
    serialize_project(reparsed, out2)
    assert len(_playlist_filters(out2, "pl_a")) == 1


def test_track_volume_replace_is_idempotent(tmp_path):
    proj = _project()
    proj = patcher.patch_project(
        proj,
        [AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="volume",
                        filter_id="vol1", properties={"level": "-12"})],
    )
    # apply again with a new level -- replace=True (default) => still one filter
    proj = patcher.patch_project(
        proj,
        [AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="volume",
                        filter_id="vol1", properties={"level": "-3"})],
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(proj, out)
    filters = _playlist_filters(out, "pl_a")
    assert len(filters) == 1
    level = next(p for p in filters[0] if p.get("name") == "level")
    assert level.text == "-3"


def test_eq_bands_then_clear(tmp_path):
    proj = _project()
    intents = [
        AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="avfilter.equalizer",
                       filter_id=f"eq1_b{i}", properties={"av.frequency": str(f)}, replace=False)
        for i, f in enumerate((100, 1000, 5000))
    ]
    proj = patcher.patch_project(proj, intents)
    out = tmp_path / "p.kdenlive"
    serialize_project(proj, out)
    assert len(_playlist_filters(out, "pl_a")) == 3

    # ClearTrackFilters by prefix removes the whole EQ stack
    proj2 = patcher.patch_project(
        parse_project(out),
        [ClearTrackFilters(track_index=1, track_ref="pl_a", id_prefix="eq1_")],
    )
    out2 = tmp_path / "p2.kdenlive"
    serialize_project(proj2, out2)
    assert _playlist_filters(out2, "pl_a") == []


def test_clip_and_track_filters_coexist(tmp_path):
    """A clip filter (track+clip_index) and a track filter (track only) on the
    same track must land in different places without cross-contamination."""
    from workshop_video_brain.core.models.timeline import AddEffect

    proj = patcher.patch_project(
        _project(),
        [
            AddEffect(track_index=1, clip_index=0, effect_name="volume",
                      params={"level": "-3"}),
            AddTrackFilter(track_index=1, track_ref="pl_a", mlt_service="panner",
                           filter_id="pan1", properties={"start": "0.75"}),
        ],
    )
    out = tmp_path / "p.kdenlive"
    serialize_project(proj, out)

    root = ET.parse(out).getroot()
    pl_a = next(pl for pl in root.findall("playlist") if pl.get("id") == "pl_a")
    # clip filter is inside the <entry>; track filter is a direct playlist child
    entry = pl_a.find("entry")
    assert entry is not None and entry.find("filter") is not None
    track_filters = pl_a.findall("filter")
    assert len(track_filters) == 1
    assert track_filters[0].get("mlt_service") == "panner"
