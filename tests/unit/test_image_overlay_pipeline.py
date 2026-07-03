"""Unit tests for the pure image-overlay pipeline logic.

Covers profile-aware rect/preset math, producer property assembly, the
qtblend transform-filter XML, fade-vs-static rect values, and the small
timeline helpers.  No filesystem / MCP / melt here.
"""
from __future__ import annotations

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
from workshop_video_brain.edit_mcp.pipelines import image_overlay as io


# ---------------------------------------------------------------------------
# Producer assembly
# ---------------------------------------------------------------------------

def test_producer_service_is_qimage():
    assert io.IMAGE_PRODUCER_SERVICE == "qimage"


def test_image_producer_id_deterministic_and_prefixed():
    a = io.image_producer_id("/media/Logo Watermark.png")
    b = io.image_producer_id("/media/Logo Watermark.png")
    assert a == b
    assert a.startswith("image_")
    # different path -> different id
    assert io.image_producer_id("/media/other.png") != a


def test_image_producer_properties():
    props = io.image_producer_properties("/m/diagram.png", 120)
    assert props["mlt_service"] == "qimage"
    assert props["resource"] == "/m/diagram.png"
    assert props["length"] == "120"
    assert props["ttl"] == "120"  # single still: ttl == length
    assert props["kdenlive:clipname"] == "diagram.png"


def test_image_producer_properties_rejects_nonpositive_length():
    with pytest.raises(ValueError):
        io.image_producer_properties("/m/x.png", 0)


def test_supported_and_svg_detection():
    assert io.is_supported_image("a.png")
    assert io.is_supported_image("A.JPG")
    assert io.is_supported_image("logo.svg")
    assert not io.is_supported_image("clip.mp4")
    assert io.is_svg("v.SVG")
    assert not io.is_svg("v.png")


# ---------------------------------------------------------------------------
# Geometry: presets across profiles
# ---------------------------------------------------------------------------

PROFILES = [
    (1920, 1080),   # 1080p
    (3840, 2160),   # 4K
    (1080, 1920),   # 9:16 vertical
]


@pytest.mark.parametrize("w,h", PROFILES)
def test_full_preset_is_whole_frame(w, h):
    assert io.position_rect("full", w, h) == (0, 0, w, h)


@pytest.mark.parametrize("w,h", PROFILES)
@pytest.mark.parametrize("preset", ["top_left", "top_right", "bottom_left", "bottom_right", "center"])
def test_preset_box_stays_inside_frame(w, h, preset):
    x, y, bw, bh = io.position_rect(preset, w, h, scale=0.15, margin=0.05)
    assert bw > 0 and bh > 0
    assert 0 <= x and 0 <= y
    assert x + bw <= w
    assert y + bh <= h


def test_preset_corner_placement_directions():
    w, h = 1920, 1080
    tl = io.position_rect("top_left", w, h, scale=0.2, margin=0.05)
    br = io.position_rect("bottom_right", w, h, scale=0.2, margin=0.05)
    # top-left near origin; bottom-right toward the far corner
    assert tl[0] < w / 2 and tl[1] < h / 2
    assert br[0] > w / 2 and br[1] > h / 2


def test_center_preset_is_centered():
    w, h = 1920, 1080
    x, y, bw, bh = io.position_rect("center", w, h, scale=0.3)
    assert abs((x + bw / 2) - w / 2) <= 1
    assert abs((y + bh / 2) - h / 2) <= 1


def test_aspect_ratio_drives_box_height():
    # 2:1 aspect -> box height half the width
    x, y, bw, bh = io.position_rect("top_left", 1920, 1080, scale=0.2, aspect=2.0)
    assert bh == round(bw / 2.0)


def test_position_rect_validates_inputs():
    with pytest.raises(ValueError):
        io.position_rect("nope", 1920, 1080)
    with pytest.raises(ValueError):
        io.position_rect("center", 1920, 1080, scale=0.0)
    with pytest.raises(ValueError):
        io.position_rect("center", 1920, 1080, margin=0.6)


# ---------------------------------------------------------------------------
# resolve_rect
# ---------------------------------------------------------------------------

def test_resolve_rect_empty_is_none():
    assert io.resolve_rect("", 1920, 1080) is None
    assert io.resolve_rect("   ", 1920, 1080) is None


def test_resolve_rect_preset():
    assert io.resolve_rect("full", 1920, 1080) == (0, 0, 1920, 1080)
    br = io.resolve_rect("bottom_right", 1920, 1080, scale=0.15)
    assert br == io.position_rect("bottom_right", 1920, 1080, scale=0.15)


def test_resolve_rect_explicit_space_and_comma():
    assert io.resolve_rect("10 20 100 50", 1920, 1080) == (10, 20, 100, 50)
    assert io.resolve_rect("10,20,100,50", 1920, 1080) == (10, 20, 100, 50)


def test_resolve_rect_invalid():
    with pytest.raises(ValueError):
        io.resolve_rect("1 2 3", 1920, 1080)
    with pytest.raises(ValueError):
        io.resolve_rect("a b c d", 1920, 1080)


# ---------------------------------------------------------------------------
# rect_to_string / overlay_rect_value / transform filter
# ---------------------------------------------------------------------------

def test_rect_to_string_static():
    assert io.rect_to_string((10, 20, 100, 50), 1.0) == "10 20 100 50 1"
    assert io.rect_to_string((0, 0, 320, 180), 0.6) == "0 0 320 180 0.6"


def test_overlay_rect_value_static_no_fade():
    v = io.overlay_rect_value((10, 20, 100, 50), opacity=0.8,
                              fade_in_frames=0, fade_out_frames=0,
                              duration_frames=50, fps=25.0)
    assert v == "10 20 100 50 0.8"
    assert ";" not in v  # single static rect, not a keyframe animation


def test_overlay_rect_value_with_fades_is_keyframed():
    v = io.overlay_rect_value((0, 0, 320, 180), opacity=1.0,
                              fade_in_frames=5, fade_out_frames=5,
                              duration_frames=50, fps=25.0)
    assert ";" in v                 # multiple keyframes
    assert v.count("=") >= 2
    # geometry held constant; opacity ramps from 0 at frame 0
    assert v.startswith("00:00:00.000")
    assert v.strip().split(";")[0].endswith(" 0")   # opacity 0 at start


def test_overlay_rect_value_scales_opacity_by_target():
    # fade-in to opacity 0.5 -> plateau value carries 0.5, not 1.0
    v = io.overlay_rect_value((0, 0, 320, 180), opacity=0.5,
                              fade_in_frames=5, fade_out_frames=0,
                              duration_frames=50, fps=25.0)
    assert "0.5" in v


def test_overlay_rect_value_validates():
    with pytest.raises(ValueError):
        io.overlay_rect_value((0, 0, 1, 1), opacity=2.0, fade_in_frames=0,
                              fade_out_frames=0, duration_frames=10, fps=25.0)


def test_build_transform_filter_xml():
    xml = io.build_transform_filter_xml(1, 0, "256 142 48 29 0.8")
    root = ET.fromstring(xml)
    assert root.tag == "filter"
    assert root.get("mlt_service") == "qtblend"
    assert root.get("track") == "1"
    assert root.get("clip_index") == "0"
    props = {p.get("name"): p.text for p in root.findall("property")}
    assert props["mlt_service"] == "qtblend"
    assert props["rect"] == "256 142 48 29 0.8"
    assert props["kdenlive_id"] == "qtblend"


# ---------------------------------------------------------------------------
# Timeline helpers
# ---------------------------------------------------------------------------

def _proj_with_tracks() -> KdenliveProject:
    return KdenliveProject(
        version="7",
        title="t",
        profile=ProjectProfile(width=320, height=180, fps=25.0),
        producers=[Producer(id="bg", resource="0x0000ffff",
                            properties={"mlt_service": "color", "resource": "0x0000ffff"})],
        tracks=[Track(id="v1", track_type="video"), Track(id="a1", track_type="audio")],
        playlists=[
            Playlist(id="v1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=99)]),
            Playlist(id="a1", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=99)]),
        ],
    )


def test_video_playlists_excludes_audio():
    p = _proj_with_tracks()
    vps = io.video_playlists(p)
    assert [pl.id for pl in vps] == ["v1"]


def test_timeline_duration_frames():
    p = _proj_with_tracks()
    assert io.timeline_duration_frames(p) == 100  # entry 0..99
