"""Unit tests for the kdenlivetitle XML builder (``pipelines/titles.py``).

Every assertion parses the builder's own output and checks structure /
geometry; the safe-area and font-scaling math is exercised across 1080p, 4K and
9:16 vertical profiles per §6 of the improvements plan.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.edit_mcp.pipelines.titles import (
    TitleSpec,
    build_title_xml,
    compute_layout,
    duration_frames,
    normalize_color,
)

PROFILES = [
    pytest.param(1920, 1080, id="1080p"),
    pytest.param(3840, 2160, id="4k"),
    pytest.param(1080, 1920, id="vertical"),
]


# ---------------------------------------------------------------------------
# normalize_color
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("#FFFFFF", "255,255,255,255"),
        ("#000000B4", "0,0,0,180"),
        ("#ff0000", "255,0,0,255"),
        ("255,0,0", "255,0,0,255"),
        ("12,34,56,78", "12,34,56,78"),
    ],
)
def test_normalize_color(value, expected):
    assert normalize_color(value) == expected


@pytest.mark.parametrize("bad", ["#FFF", "not-a-color", "#GGGGGG", "1,2"])
def test_normalize_color_rejects_garbage(bad):
    with pytest.raises(ValueError):
        normalize_color(bad)


# ---------------------------------------------------------------------------
# Document structure
# ---------------------------------------------------------------------------


def test_build_title_xml_root_and_items():
    spec = TitleSpec(text="Jane Doe", subtitle="Host", width=1920, height=1080, fps=25)
    root = ET.fromstring(build_title_xml(spec))

    assert root.tag == "kdenlivetitle"
    assert root.get("width") == "1920"
    assert root.get("height") == "1080"
    assert root.get("LC_NUMERIC") == "C"
    # background rect + title + subtitle
    items = root.findall("item")
    assert len(items) == 3
    types = [i.get("type") for i in items]
    assert types == ["QGraphicsRectItem", "QGraphicsTextItem", "QGraphicsTextItem"]
    # transparent document background so it composites over footage below
    assert root.find("background").get("color") == "0,0,0,0"
    assert root.find("startviewport").get("rect") == "0,0,1920,1080"
    assert root.find("endviewport").get("rect") == "0,0,1920,1080"


def test_subtitle_omitted_when_empty():
    spec = TitleSpec(text="Solo", subtitle="", background=True)
    root = ET.fromstring(build_title_xml(spec))
    text_items = [i for i in root.findall("item") if i.get("type") == "QGraphicsTextItem"]
    assert len(text_items) == 1
    assert text_items[0].find("content").text == "Solo"


def test_background_can_be_disabled():
    spec = TitleSpec(text="No Bar", background=False)
    root = ET.fromstring(build_title_xml(spec))
    assert not root.findall("item[@type='QGraphicsRectItem']")


def test_title_text_and_font_attrs():
    spec = TitleSpec(text="Hello", font_family="DejaVu Sans", font_color="#FFFFFF")
    root = ET.fromstring(build_title_xml(spec))
    title = root.findall("item[@type='QGraphicsTextItem']")[0]
    content = title.find("content")
    assert content.text == "Hello"
    assert content.get("font") == "DejaVu Sans"
    assert content.get("font-color") == "255,255,255,255"
    # font-pixel-size is what the MLT titler actually renders with
    assert int(content.get("font-pixel-size")) > 0


@pytest.mark.parametrize("align,flag", [("left", "0"), ("center", "4"), ("right", "2")])
def test_alignment_mapping(align, flag):
    spec = TitleSpec(text="A", align=align)
    root = ET.fromstring(build_title_xml(spec))
    title = root.findall("item[@type='QGraphicsTextItem']")[0]
    assert title.find("content").get("alignment") == flag


# ---------------------------------------------------------------------------
# duration math
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fps,seconds,frames",
    [
        (25.0, 4.0, 100),
        (30.0, 1.0, 30),
        (23.976, 1.0, 24),
        (29.97, 2.0, 60),
        (60.0, 0.5, 30),
    ],
)
def test_duration_frames(fps, seconds, frames):
    spec = TitleSpec(text="T", fps=fps, duration_seconds=seconds)
    assert duration_frames(spec) == frames
    root = ET.fromstring(build_title_xml(spec))
    assert root.get("duration") == str(frames)
    assert root.get("out") == str(frames - 1)


# ---------------------------------------------------------------------------
# Safe-area geometry across profiles
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("w,h", PROFILES)
def test_safe_area_margins_scale_with_profile(w, h):
    spec = TitleSpec(text="Name", subtitle="Role", width=w, height=h, safe_margin=0.1)
    layout = compute_layout(spec)
    mx, my = layout["margin_x"], layout["margin_y"]
    assert mx == round(w * 0.1)
    assert my == round(h * 0.1)

    # Title and subtitle boxes stay inside the title-safe rectangle.
    for key in ("title_box", "subtitle_box"):
        box = layout[key]
        assert box is not None
        x, y, bw, bh = box
        assert x >= mx
        assert x + bw <= w - mx + 1  # allow rounding slack
        assert y >= my
        assert y + bh <= h - my + 1


@pytest.mark.parametrize("w,h", PROFILES)
def test_font_size_scales_with_height(w, h):
    spec = TitleSpec(text="X", width=w, height=h, title_font_scale=0.06)
    layout = compute_layout(spec)
    assert layout["title_size"] == max(12, round(h * 0.06))


def test_explicit_font_size_overrides_scale():
    spec = TitleSpec(text="X", height=1080, title_font_size=42, title_font_scale=0.06)
    assert compute_layout(spec)["title_size"] == 42


@pytest.mark.parametrize("anchor", ["top", "center", "bottom", "lower-third"])
def test_anchor_positions_stay_in_safe_area(anchor):
    spec = TitleSpec(text="T", subtitle="S", width=1920, height=1080, anchor=anchor)
    layout = compute_layout(spec)
    bx, by, bw, bh = layout["block"]
    my = layout["margin_y"]
    assert by >= my
    assert by + bh <= 1080 - my + 1


def test_lower_third_sits_below_center():
    spec = TitleSpec(text="T", width=1920, height=1080, anchor="lower-third")
    top = TitleSpec(text="T", width=1920, height=1080, anchor="top")
    assert compute_layout(spec)["block"][1] > compute_layout(top)["block"][1]


def test_background_rect_clamped_to_frame():
    spec = TitleSpec(text="Wide", width=1920, height=1080, background=True)
    bx, by, bw, bh = compute_layout(spec)["background_rect"]
    assert bx >= 0 and by >= 0
    assert bx + bw <= 1920
    assert by + bh <= 1080
