"""Unit tests for the additive-overlay pure pipeline (``pipelines/overlay_looks``).

Covers the light-leak blend-mode set, composite geometry, the model-level
playlist-targeted overlay insert, and the day->night grade chain (static +
keyframed).
"""
from __future__ import annotations

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    PlaylistEntry,
    Playlist,
    Producer,
    Track,
)
from workshop_video_brain.edit_mcp.pipelines.overlay_looks import (
    DAY_TO_NIGHT_SERVICES,
    LIGHT_LEAK_BLEND_MODES,
    build_filter_xml,
    day_to_night_chain,
    insert_overlay_clip,
    lookup_catalog_id,
    overlay_geometry,
    overlay_producer_id,
    video_playlists,
)


def _project() -> KdenliveProject:
    """A 2-video-track project: track 0 has one clip, track 1 is empty."""
    p = KdenliveProject()
    p.tracks = [
        Track(id="playlist0", track_type="video"),
        Track(id="playlist1", track_type="video"),
        Track(id="playlist_audio", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="playlist0", entries=[PlaylistEntry(producer_id="p0", in_point=0, out_point=99)]),
        Playlist(id="playlist1", entries=[]),
        Playlist(id="playlist_audio", entries=[]),
    ]
    p.producers = [Producer(id="p0", resource="a.mp4")]
    return p


# ---------------------------------------------------------------------------
# Blend modes / geometry
# ---------------------------------------------------------------------------

def test_light_leak_blend_modes_are_lightening_only():
    assert LIGHT_LEAK_BLEND_MODES == frozenset({"screen", "lighten", "add"})


def test_overlay_geometry_maps_opacity_to_percent():
    assert overlay_geometry(1920, 1080, 1.0) == "0/0:1920x1080:100"
    assert overlay_geometry(1280, 720, 0.5) == "0/0:1280x720:50"
    assert overlay_geometry(1920, 1080, 0.0) == "0/0:1920x1080:0"


@pytest.mark.parametrize("bad", [-0.1, 1.5, "x", True])
def test_overlay_geometry_rejects_out_of_range_opacity(bad):
    with pytest.raises(ValueError):
        overlay_geometry(1920, 1080, bad)


# ---------------------------------------------------------------------------
# video_playlists / producer id
# ---------------------------------------------------------------------------

def test_video_playlists_excludes_audio():
    vps = video_playlists(_project())
    assert [pl.id for pl in vps] == ["playlist0", "playlist1"]


def test_overlay_producer_id_is_deterministic():
    a = overlay_producer_id("/media/leak.mp4")
    b = overlay_producer_id("/media/leak.mp4")
    assert a == b and a.startswith("leak_")


# ---------------------------------------------------------------------------
# Model-level overlay insert
# ---------------------------------------------------------------------------

def test_insert_overlay_clip_adds_producer_gap_and_entry():
    proj = _project()
    idx = insert_overlay_clip(proj, overlay_track=1, media_path="/m/leak.mp4",
                              at_frame=30, duration_frames=120)
    assert idx == 0  # first real clip on the (previously empty) overlay track
    pl1 = video_playlists(proj)[1]
    # gap entry then the real entry
    assert pl1.entries[0].producer_id == ""
    assert pl1.entries[0].out_point == 29  # gap length = at_frame
    assert pl1.entries[1].producer_id.startswith("leak_")
    assert pl1.entries[1].in_point == 0
    assert pl1.entries[1].out_point == 119
    # producer registered exactly once
    assert sum(1 for p in proj.producers if p.id.startswith("leak_")) == 1


def test_insert_overlay_clip_no_gap_when_at_frame_zero():
    proj = _project()
    idx = insert_overlay_clip(proj, 1, "/m/leak.mp4", at_frame=0, duration_frames=60)
    pl1 = video_playlists(proj)[1]
    assert idx == 0
    assert [e.producer_id != "" for e in pl1.entries] == [True]


def test_insert_overlay_clip_returns_real_index_after_existing_clip():
    proj = _project()
    idx = insert_overlay_clip(proj, 0, "/m/leak.mp4", at_frame=0, duration_frames=60)
    assert idx == 1  # track 0 already had one real clip


@pytest.mark.parametrize("track", [-1, 5])
def test_insert_overlay_clip_bad_track_raises(track):
    with pytest.raises(ValueError):
        insert_overlay_clip(_project(), track, "/m/leak.mp4", 0, 60)


@pytest.mark.parametrize("at_frame,dur", [(-1, 60), (0, 0), (0, -5)])
def test_insert_overlay_clip_bad_placement_raises(at_frame, dur):
    with pytest.raises(ValueError):
        insert_overlay_clip(_project(), 1, "/m/leak.mp4", at_frame, dur)


# ---------------------------------------------------------------------------
# Day -> night grade chain
# ---------------------------------------------------------------------------

def test_day_to_night_services_order():
    assert DAY_TO_NIGHT_SERVICES == ("avfilter.eq", "frei0r.colorize")


def test_day_to_night_static_values_darken_and_desaturate():
    chain = day_to_night_chain(intensity=1.0, keyframed=False, duration_frames=100)
    services = [s for s, _ in chain]
    assert services == ["avfilter.eq", "frei0r.colorize"]
    eq = dict(chain[0][1])
    # brightness negative (darker), saturation < 1 (desaturated)
    assert float(eq["av.brightness"]) < 0
    assert float(eq["av.saturation"]) < 1.0
    colorize = dict(chain[1][1])
    assert colorize["hue"] == "0.62"  # blue night tint


def test_day_to_night_intensity_scales_darkness():
    low = float(dict(day_to_night_chain(0.2, keyframed=False, duration_frames=100)[0][1])["av.brightness"])
    high = float(dict(day_to_night_chain(0.9, keyframed=False, duration_frames=100)[0][1])["av.brightness"])
    assert high < low  # higher intensity => darker


def test_day_to_night_keyframed_ramps_from_neutral():
    chain = day_to_night_chain(intensity=0.5, keyframed=True, duration_frames=100, fps=25.0)
    eq = dict(chain[0][1])
    # keyframe string: starts at neutral (0 brightness, 1 saturation)
    assert eq["av.brightness"].startswith("00:00:00.000=0;")
    assert eq["av.saturation"].startswith("00:00:00.000=1;")
    assert ";" in eq["av.brightness"]  # two keyframes


def test_day_to_night_keyframed_false_is_static_string():
    chain = day_to_night_chain(intensity=0.5, keyframed=False, duration_frames=100)
    eq = dict(chain[0][1])
    assert ";" not in eq["av.brightness"]
    assert "=" not in eq["av.brightness"]


@pytest.mark.parametrize("bad", [-0.1, 1.1, True, "x"])
def test_day_to_night_bad_intensity_raises(bad):
    with pytest.raises(ValueError):
        day_to_night_chain(intensity=bad, duration_frames=100)


# ---------------------------------------------------------------------------
# Catalog / filter XML helpers
# ---------------------------------------------------------------------------

def test_lookup_catalog_id_resolves_known_services():
    assert lookup_catalog_id("avfilter.eq") == "avfilter_eq"
    assert lookup_catalog_id("frei0r.colorize") == "frei0r_colorize"
    assert lookup_catalog_id("no.such.service") is None


def test_build_filter_xml_shape():
    xml = build_filter_xml("avfilter.eq", "avfilter_eq", track=2, clip=0,
                           props=[("av.brightness", "-0.2")])
    import xml.etree.ElementTree as ET
    el = ET.fromstring(xml)
    assert el.tag == "filter"
    assert el.attrib["mlt_service"] == "avfilter.eq"
    assert el.attrib["track"] == "2"
    assert el.attrib["clip_index"] == "0"
    props = {p.attrib["name"]: p.text for p in el.findall("property")}
    assert props["mlt_service"] == "avfilter.eq"
    assert props["kdenlive_id"] == "avfilter_eq"
    assert props["av.brightness"] == "-0.2"
