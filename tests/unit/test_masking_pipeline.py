"""Unit tests for ``edit_mcp/pipelines/masking.py`` (Sub-Spec 1).

Covers SR-01..SR-12 and SR-38 from
``docs/tests/2026-04-13-masking/``.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.edit_mcp.pipelines import masking


# ---------------------------------------------------------------------------
# SR-01: Module exports
# ---------------------------------------------------------------------------

def test_exports_present():
    for name in (
        "MaskShape",
        "MaskParams",
        "shape_to_points",
        "build_rotoscoping_xml",
        "build_object_mask_xml",
        "build_chroma_key_xml",
        "build_chroma_key_advanced_xml",
        "color_to_mlt_hex",
        "ALPHA_OPERATION_TO_MLT",
    ):
        assert hasattr(masking, name), f"missing export: {name}"


# ---------------------------------------------------------------------------
# SR-02 / SR-03: Model defaults
# ---------------------------------------------------------------------------

def test_maskparams_defaults():
    p = masking.MaskParams(points=((0, 0), (1, 0), (1, 1), (0, 1)))
    assert p.feather == 0
    assert p.feather_passes == 1
    assert p.alpha_operation == "add"
    assert p.points == ((0, 0), (1, 0), (1, 1), (0, 1))


def test_maskshape_defaults():
    s = masking.MaskShape(kind="rect")
    assert s.bounds == (0.0, 0.0, 1.0, 1.0)
    assert s.points == ()
    assert s.sample_count == 32


# ---------------------------------------------------------------------------
# SR-04..SR-07: shape_to_points
# ---------------------------------------------------------------------------

def test_shape_to_points_rect():
    s = masking.MaskShape(kind="rect", bounds=(0.1, 0.1, 0.5, 0.5))
    pts = masking.shape_to_points(s)
    assert pts == (
        (0.1, 0.1),
        (0.6, 0.1),
        (0.6, 0.6),
        (0.1, 0.6),
    )


def test_shape_to_points_ellipse():
    s = masking.MaskShape(kind="ellipse", bounds=(0.0, 0.0, 1.0, 1.0), sample_count=32)
    pts = masking.shape_to_points(s)
    assert len(pts) == 32
    # First point at angle 0 is (cx+rx, cy) = (1.0, 0.5)
    assert pts[0] == pytest.approx((1.0, 0.5))


def test_shape_to_points_polygon_passthrough():
    src = ((0.1, 0.1), (0.9, 0.1), (0.5, 0.9))
    s = masking.MaskShape(kind="polygon", points=src)
    assert masking.shape_to_points(s) == src


def test_shape_to_points_polygon_too_few():
    s = masking.MaskShape(kind="polygon", points=((0.0, 0.0), (1.0, 1.0)))
    with pytest.raises(ValueError, match="at least 3"):
        masking.shape_to_points(s)


def test_shape_to_points_out_of_range():
    s = masking.MaskShape(kind="rect", bounds=(-0.1, 0.0, 1.0, 1.0))
    with pytest.raises(ValueError, match="-0.1"):
        masking.shape_to_points(s)


def test_shape_to_points_ellipse_degenerate():
    with pytest.raises(Exception):
        # sample_count=3 fails pydantic validation (ge=4)
        masking.MaskShape(kind="ellipse", sample_count=3)


# ---------------------------------------------------------------------------
# SR-08: Rotoscoping XML
# ---------------------------------------------------------------------------

def test_build_rotoscoping_xml_structure():
    params = masking.MaskParams(
        points=((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)),
        feather=5,
        feather_passes=1,
        alpha_operation="sub",
    )
    xml = masking.build_rotoscoping_xml((2, 0), params)
    root = ET.fromstring(xml)
    assert root.tag == "filter"
    assert root.get("mlt_service") == "rotoscoping"
    assert root.get("track") == "2"
    assert root.get("clip_index") == "0"

    props = {p.get("name"): p.text for p in root.findall("property")}
    assert props["feather"] == "5"
    assert props["feather_passes"] == "1"
    assert props["alpha_operation"] == "sub"
    assert props["mode"] == "alpha"
    assert props["kdenlive_id"] == "rotoscoping"
    # Spline is JSON with a single keyframe at frame 0
    spline = json.loads(props["spline"])
    assert "0" in spline
    assert len(spline["0"]) == 4
    # Each entry is [[x,y],[x,y],[x,y]] -- linear (handles == point)
    first = spline["0"][0]
    assert first[0] == [0.1, 0.1]
    assert first[1] == [0.1, 0.1]
    assert first[2] == [0.1, 0.1]


def test_rotoscoping_alpha_operation_alias_normalized():
    params = masking.MaskParams(
        points=((0.0, 0.0), (1.0, 0.0), (1.0, 1.0)),
        alpha_operation="sub",
    )
    xml = masking.build_rotoscoping_xml((1, 2), params)
    root = ET.fromstring(xml)
    props = {p.get("name"): p.text for p in root.findall("property")}
    assert props["alpha_operation"] == "sub"


# ---------------------------------------------------------------------------
# SR-09: Object mask
# ---------------------------------------------------------------------------

def test_build_object_mask_xml():
    xml = masking.build_object_mask_xml(
        (0, 0),
        {"shape": 0, "threshold": 0.4},
    )
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "frei0r.alpha0ps_alphaspot"
    props = {p.get("name"): p.text for p in root.findall("property")}
    assert props["kdenlive_id"] == "frei0r_alpha0ps_alphaspot"
    assert props["0"] == "0"
    assert props["7"] == "0.4"


# ---------------------------------------------------------------------------
# SR-10: Basic chroma
# ---------------------------------------------------------------------------

def test_build_chroma_key_xml():
    xml = masking.build_chroma_key_xml((0, 0), "#00ff00", 0.15)
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "chroma"
    props = {p.get("name"): p.text for p in root.findall("property")}
    assert props["key"] == "0x00ff00ff"
    assert props["variance"] == "0.15"
    # No blend property emitted
    assert "blend" not in props


def test_build_chroma_key_xml_blend_warning(caplog):
    import logging
    with caplog.at_level(logging.WARNING, logger="workshop_video_brain.edit_mcp.pipelines.masking"):
        masking.build_chroma_key_xml((0, 0), "#00ff00", 0.15, blend=0.5)
    assert any("blend" in rec.getMessage() for rec in caplog.records)


# ---------------------------------------------------------------------------
# SR-11: Advanced chroma
# ---------------------------------------------------------------------------

def test_build_chroma_key_advanced_xml():
    xml = masking.build_chroma_key_advanced_xml(
        (0, 0),
        "#00ff00",
        tolerance_near=0.1,
        tolerance_far=0.3,
        edge_smooth=0.2,
        spill_suppression=0.0,
    )
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "avfilter.hsvkey"
    props = {p.get("name"): p.text for p in root.findall("property")}
    for name in ("av.hue", "av.sat", "av.val", "av.similarity", "av.blend"):
        assert name in props, f"missing property {name}"
    assert props["kdenlive_id"] == "avfilter_hsvkey"


def test_advanced_chroma_tolerance_order():
    with pytest.raises(ValueError, match="tolerance_far"):
        masking.build_chroma_key_advanced_xml(
            (0, 0), "#00ff00",
            tolerance_near=0.5, tolerance_far=0.2,
        )


# ---------------------------------------------------------------------------
# SR-12: color_to_mlt_hex
# ---------------------------------------------------------------------------

def test_color_to_mlt_hex_cases():
    assert masking.color_to_mlt_hex("#00ff00") == "0x00ff00ff"
    assert masking.color_to_mlt_hex("#00FF0080") == "0x00ff0080"
    assert masking.color_to_mlt_hex(0x00ff00ff) == "0x00ff00ff"
    with pytest.raises(ValueError):
        masking.color_to_mlt_hex("not a color")


# ---------------------------------------------------------------------------
# SR-38: ALPHA_OPERATION_TO_MLT normalization table
# ---------------------------------------------------------------------------

def test_alpha_operation_normalization_table():
    t = masking.ALPHA_OPERATION_TO_MLT
    assert t["write_on_clear"] == "clear"
    assert t["subtract"] == "sub"
    assert t["maximum"] == "max"
    assert t["minimum"] == "min"
    # Identity for canonical tokens
    for k in ("clear", "max", "min", "add", "sub"):
        assert t[k] == k
