"""Unit tests for ``edit_mcp/pipelines/shape_alpha.py``.

Covers the file-based Shape Alpha builder that consumes an external matte
(e.g. a Kdenlive 25.04 SAM2 Object Mask export). Schema anchored to
``/usr/share/kdenlive/effects/shape.xml`` and ``mask_start_shape.xml``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.edit_mcp.pipelines import shape_alpha


def _props(xml: str) -> dict[str, str]:
    root = ET.fromstring(xml)
    return {p.get("name"): p.text for p in root.findall("property")}


def test_exports_present():
    for name in (
        "build_shape_alpha_xml",
        "build_mask_start_shape_xml",
        "SHAPE_INNER_PROPS",
    ):
        assert hasattr(shape_alpha, name), f"missing export: {name}"


def test_plain_shape_defaults():
    xml = shape_alpha.build_shape_alpha_xml((2, 0), "/tmp/mask.mov")
    root = ET.fromstring(xml)
    assert root.tag == "filter"
    assert root.get("mlt_service") == "shape"
    assert root.get("track") == "2"
    assert root.get("clip_index") == "0"
    p = _props(xml)
    assert p["mlt_service"] == "shape"
    assert p["kdenlive_id"] == "shape"
    assert p["resource"] == "/tmp/mask.mov"
    assert p["mix"] == "100"
    assert p["softness"] == "0.1"
    assert p["invert"] == "0"
    assert p["use_luminance"] == "0"
    assert p["use_mix"] == "1"
    assert p["in"] == "0"
    assert p["out"] == "-1"
    assert p["audio_match"] == "0"


def test_plain_shape_luma_matte_flags():
    xml = shape_alpha.build_shape_alpha_xml(
        (1, 3), "/tmp/luma.png",
        mix=50, softness=0.4, invert=True,
        use_luminance=True, use_mix=False, mask_in=5, mask_out=120,
    )
    p = _props(xml)
    assert p["resource"] == "/tmp/luma.png"
    assert p["mix"] == "50"
    assert p["softness"] == "0.4"
    assert p["invert"] == "1"
    assert p["use_luminance"] == "1"
    assert p["use_mix"] == "0"
    assert p["in"] == "5"
    assert p["out"] == "120"


def test_mask_start_shape_sandwich_form():
    xml = shape_alpha.build_mask_start_shape_xml((2, 0), "/tmp/mask.mov", mix=70)
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "mask_start"
    p = _props(xml)
    assert p["mlt_service"] == "mask_start"
    assert p["kdenlive_id"] == "mask_start-shape"
    assert p["filter"] == "shape"
    # inner props are filter.* prefixed ...
    assert p["filter.resource"] == "/tmp/mask.mov"
    assert p["filter.mix"] == "70"
    assert p["filter.softness"] == "0.1"
    assert p["filter.use_luminance"] == "0"
    # ... except in/out which sit on the outer mask_start filter
    assert p["in"] == "0"
    assert p["out"] == "-1"
    assert "filter.in" not in p
    assert "filter.out" not in p


@pytest.mark.parametrize("bad", ["", "   ", None])
def test_empty_resource_rejected(bad):
    with pytest.raises((ValueError, TypeError)):
        shape_alpha.build_shape_alpha_xml((0, 0), bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("mix", [-1, 101, 200])
def test_mix_out_of_range_rejected(mix):
    with pytest.raises(ValueError):
        shape_alpha.build_shape_alpha_xml((0, 0), "/m.mov", mix=mix)


def test_softness_out_of_range_rejected():
    with pytest.raises(ValueError):
        shape_alpha.build_shape_alpha_xml((0, 0), "/m.mov", softness=1.5)


def test_mask_out_below_minus_one_rejected():
    with pytest.raises(ValueError):
        shape_alpha.build_shape_alpha_xml((0, 0), "/m.mov", mask_out=-2)
