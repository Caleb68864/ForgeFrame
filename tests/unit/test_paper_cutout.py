"""Unit tests for ``edit_mcp/pipelines/paper_cutout.py``.

Covers the torn-paper cutout stack builder distilled from Mint Visual's
"Paper Cutout Transition" tutorial. See
``docs/research/2026-07-03-tutorial-effect-analysis/paper-cutout-transition.md``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.edit_mcp.pipelines import paper_cutout


CLIP = (2, 0)


def _services(xmls: list[str]) -> list[str]:
    return [ET.fromstring(x).attrib["mlt_service"] for x in xmls]


def _props(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)
    return {p.attrib["name"]: (p.text or "") for p in root.findall("property")}


# ---------------------------------------------------------------------------
# Module exports
# ---------------------------------------------------------------------------

def test_exports_present():
    for name in (
        "build_torn_polygon",
        "transform_rect",
        "distort_props",
        "dropshadow_props",
        "paper_cutout_filter_xml",
        "DEFAULT_TORN_BOUNDS",
    ):
        assert hasattr(paper_cutout, name), f"{name} missing"


# ---------------------------------------------------------------------------
# build_torn_polygon
# ---------------------------------------------------------------------------

def test_torn_polygon_is_deterministic():
    a = paper_cutout.build_torn_polygon()
    b = paper_cutout.build_torn_polygon()
    assert a == b


def test_torn_polygon_seed_changes_shape():
    a = paper_cutout.build_torn_polygon(seed=1)
    b = paper_cutout.build_torn_polygon(seed=99)
    assert a != b


def test_torn_polygon_count_and_normalized():
    pts = paper_cutout.build_torn_polygon(sides=16)
    assert len(pts) == 16
    for x, y in pts:
        assert 0.0 <= x <= 1.0
        assert 0.0 <= y <= 1.0


def test_torn_polygon_rejects_too_few_sides():
    with pytest.raises(ValueError):
        paper_cutout.build_torn_polygon(sides=2)


def test_torn_polygon_rejects_negative_jitter():
    with pytest.raises(ValueError):
        paper_cutout.build_torn_polygon(jitter=-0.1)


# ---------------------------------------------------------------------------
# transform_rect
# ---------------------------------------------------------------------------

def test_transform_rect_centred_scale_up():
    rect = paper_cutout.transform_rect(1.1, 1000, 1000)
    x, y, w, h, opacity = rect.split()
    assert float(w) == pytest.approx(1100.0)
    assert float(h) == pytest.approx(1100.0)
    # Centred: negative offset equal to half the growth.
    assert float(x) == pytest.approx(-50.0)
    assert float(y) == pytest.approx(-50.0)
    assert opacity == "1"


def test_transform_rect_rejects_nonpositive_scale():
    with pytest.raises(ValueError):
        paper_cutout.transform_rect(0.0, 1920, 1080)


def test_transform_rect_rejects_bad_dims():
    with pytest.raises(ValueError):
        paper_cutout.transform_rect(1.1, 0, 1080)


# ---------------------------------------------------------------------------
# distort_props / dropshadow_props
# ---------------------------------------------------------------------------

def test_distort_props_uses_frei0r_indices():
    props = dict(paper_cutout.distort_props(0.6, 0.03))
    assert props["mlt_service"] == "frei0r.distort0r"
    assert props["0"] == "0.6000"
    assert props["1"] == "0.0300"


def test_distort_props_rejects_negatives():
    with pytest.raises(ValueError):
        paper_cutout.distort_props(-1.0, 0.02)
    with pytest.raises(ValueError):
        paper_cutout.distort_props(0.5, -0.02)


def test_dropshadow_props_black_hex_and_offsets():
    props = dict(paper_cutout.dropshadow_props(4, 8.0, "#000000"))
    assert props["mlt_service"] == "dropshadow"
    assert props["x"] == "4"
    assert props["y"] == "4"
    assert props["radius"] == "8.00"
    assert props["color"] == "0x000000ff"


def test_dropshadow_props_rejects_negative_blur():
    with pytest.raises(ValueError):
        paper_cutout.dropshadow_props(4, -1.0, "#000000")


# ---------------------------------------------------------------------------
# paper_cutout_filter_xml -- stack composition
# ---------------------------------------------------------------------------

def test_default_stack_is_mask_plus_dropshadow():
    xmls = paper_cutout.paper_cutout_filter_xml(CLIP)
    assert _services(xmls) == ["rotoscoping", "dropshadow"]


def test_full_stack_order():
    xmls = paper_cutout.paper_cutout_filter_xml(
        CLIP,
        edge_scale=1.05,
        distort_amplitude=0.5,
        drop_shadow=True,
    )
    assert _services(xmls) == [
        "affine",
        "rotoscoping",
        "frei0r.distort0r",
        "dropshadow",
    ]


def test_no_transform_when_scale_is_one():
    xmls = paper_cutout.paper_cutout_filter_xml(CLIP, edge_scale=1.0)
    assert "affine" not in _services(xmls)


def test_no_distort_when_amplitude_zero():
    xmls = paper_cutout.paper_cutout_filter_xml(CLIP, distort_amplitude=0.0)
    assert "frei0r.distort0r" not in _services(xmls)


def test_drop_shadow_can_be_disabled():
    xmls = paper_cutout.paper_cutout_filter_xml(CLIP, drop_shadow=False)
    assert _services(xmls) == ["rotoscoping"]


def test_rotoscoping_feather_defaults_to_two():
    xmls = paper_cutout.paper_cutout_filter_xml(CLIP)
    roto = next(x for x in xmls if ET.fromstring(x).attrib["mlt_service"] == "rotoscoping")
    props = _props(roto)
    assert props["feather"] == "2"
    assert props["feather_passes"] == "2"


def test_custom_points_used_in_spline():
    pts = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    xmls = paper_cutout.paper_cutout_filter_xml(
        CLIP, points=tuple((p[0], p[1]) for p in pts)
    )
    roto = next(x for x in xmls if ET.fromstring(x).attrib["mlt_service"] == "rotoscoping")
    props = _props(roto)
    assert "0.9" in props["spline"]


def test_too_few_points_raises():
    with pytest.raises(ValueError):
        paper_cutout.paper_cutout_filter_xml(CLIP, points=((0.1, 0.1), (0.9, 0.9)))


def test_out_of_range_points_raise():
    with pytest.raises(ValueError):
        paper_cutout.paper_cutout_filter_xml(
            CLIP, points=((0.1, 0.1), (1.5, 0.2), (0.5, 0.9))
        )


def test_bad_alpha_operation_raises():
    with pytest.raises(ValueError):
        paper_cutout.paper_cutout_filter_xml(CLIP, alpha_operation="bogus")


def test_clip_ref_propagates_to_attrs():
    xmls = paper_cutout.paper_cutout_filter_xml((3, 5))
    for xml in xmls:
        root = ET.fromstring(xml)
        assert root.attrib["track"] == "3"
        assert root.attrib["clip_index"] == "5"
