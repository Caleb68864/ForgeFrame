"""Unit tests for ``edit_mcp/pipelines/masking.py`` alpha-routing (Sub-Spec 2).

Covers SR-13..SR-18 and SR-39 from
``docs/tests/2026-04-13-masking/``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import parser, patcher
from workshop_video_brain.edit_mcp.pipelines import masking


FIXTURE_PATH = (
    Path(__file__).parent / "fixtures" / "masking_reference.kdenlive"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_filter_xml(
    track: int,
    clip_index: int,
    mlt_service: str,
    properties: dict[str, str] | None = None,
) -> str:
    root = ET.Element(
        "filter",
        {
            "mlt_service": mlt_service,
            "track": str(track),
            "clip_index": str(clip_index),
        },
    )
    props = dict(properties or {})
    props.setdefault("mlt_service", mlt_service)
    for name, value in props.items():
        sub = ET.SubElement(root, "property", {"name": name})
        sub.text = value
    return ET.tostring(root, encoding="unicode")


def _make_project_with_roto_and_target() -> KdenliveProject:
    """Project with track 0 carrying one clip and two filters:
    plain ``rotoscoping`` (index 0) and ``brightness`` (index 1)."""
    pl0 = Playlist(
        id="playlist0",
        entries=[PlaylistEntry(
            producer_id="producer_a", in_point=0, out_point=100
        )],
    )
    project = KdenliveProject(playlists=[pl0])

    params = masking.MaskParams(points=((0.1, 0.1), (0.9, 0.1), (0.5, 0.9)))
    roto_xml = masking.build_rotoscoping_xml((0, 0), params)
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=roto_xml, position_hint="after_tractor",
    ))

    brightness_xml = _build_filter_xml(
        0, 0, "brightness", {"kdenlive_id": "brightness", "level": "0.5"},
    )
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=brightness_xml,
        position_hint="after_tractor",
    ))
    return project


# ---------------------------------------------------------------------------
# SR-13: Module exports
# ---------------------------------------------------------------------------

def test_exports_present():
    for name in (
        "apply_mask_to_effect",
        "build_mask_start_rotoscoping_xml",
        "build_mask_apply_xml",
        "MASK_START_SERVICES",
        "MASK_APPLY_SERVICE",
        "MASK_CAPABLE_INNER_SERVICES",
    ):
        assert hasattr(masking, name), f"missing export: {name}"


# ---------------------------------------------------------------------------
# Builder sanity
# ---------------------------------------------------------------------------

def test_mask_start_xml_matches_kdenlive_convention():
    params = masking.MaskParams(
        points=((0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)),
        feather=5, feather_passes=2, alpha_operation="clear",
    )
    xml = masking.build_mask_start_rotoscoping_xml((0, 0), params)
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "mask_start"
    props = {
        p.get("name"): p.text for p in root.findall("property")
    }
    for required in (
        "mlt_service", "kdenlive_id", "filter",
        "filter.spline", "filter.mode", "filter.alpha_operation",
        "filter.feather", "filter.feather_passes",
    ):
        assert required in props, f"missing {required}"
    assert props["kdenlive_id"] == "mask_start-rotoscoping"
    assert props["filter"] == "rotoscoping"
    assert props["filter.mode"] == "alpha"
    assert props["filter.alpha_operation"] == "clear"
    assert props["filter.feather"] == "5"
    assert props["filter.feather_passes"] == "2"


def test_mask_apply_xml_has_qtblend():
    xml = masking.build_mask_apply_xml((0, 0))
    root = ET.fromstring(xml)
    assert root.get("mlt_service") == "mask_apply"
    props = {
        p.get("name"): p.text for p in root.findall("property")
    }
    assert props.get("mlt_service") == "mask_apply"
    assert props.get("kdenlive_id") == "mask_apply"
    assert props.get("transition") == "qtblend"


def test_reference_fixture_parses():
    project = parser.parse_project(FIXTURE_PATH)
    filters = patcher.list_effects(project, (0, 0))
    services = [f["mlt_service"] for f in filters]
    assert services == ["mask_start", "brightness", "mask_apply"]
    # filter.* props carried on the mask_start filter
    assert "filter.spline" in filters[0]["properties"]
    assert filters[0]["properties"]["filter"] == "rotoscoping"
    # mask_apply carries qtblend transition
    assert filters[2]["properties"].get("transition") == "qtblend"


# ---------------------------------------------------------------------------
# SR-14: already ordered -> no reorder, but first invocation converts.
# ---------------------------------------------------------------------------

def test_apply_mask_already_ordered():
    project = _make_project_with_roto_and_target()
    result = masking.apply_mask_to_effect(
        project, (0, 0),
        mask_effect_index=0, target_effect_index=1,
    )
    assert result["reordered"] is False
    assert result["converted_to_sandwich"] is True
    assert result["mask_effect_index"] == 0
    assert result["target_effect_index"] == 1
    assert result["mask_apply_effect_index"] == 2

    filters = patcher.list_effects(project, (0, 0))
    services = [f["mlt_service"] for f in filters]
    assert services == ["mask_start", "brightness", "mask_apply"]
    # filter.* props promoted onto the mask_start filter
    props = filters[0]["properties"]
    assert props["filter"] == "rotoscoping"
    assert "filter.spline" in props
    assert "filter.alpha_operation" in props


# ---------------------------------------------------------------------------
# SR-15: reorder when out of order.
# ---------------------------------------------------------------------------

def test_apply_mask_needs_reorder():
    # Build project where mask is below target.
    pl0 = Playlist(
        id="playlist0",
        entries=[PlaylistEntry(
            producer_id="producer_a", in_point=0, out_point=100,
        )],
    )
    project = KdenliveProject(playlists=[pl0])

    brightness_xml = _build_filter_xml(
        0, 0, "brightness", {"kdenlive_id": "brightness", "level": "0.5"},
    )
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=brightness_xml,
        position_hint="after_tractor",
    ))
    # rotoscoping filters at indices 1 and 2 below target at index 0
    # to give us mask_index > target_index.
    filler_xml = _build_filter_xml(
        0, 0, "volume", {"kdenlive_id": "volume", "level": "1.0"},
    )
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=filler_xml,
        position_hint="after_tractor",
    ))
    params = masking.MaskParams(points=((0.1, 0.1), (0.9, 0.1), (0.5, 0.9)))
    roto_xml = masking.build_rotoscoping_xml((0, 0), params)
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=roto_xml, position_hint="after_tractor",
    ))

    # stack: [brightness, volume, rotoscoping]; target=0 (brightness), mask=2.
    result = masking.apply_mask_to_effect(
        project, (0, 0),
        mask_effect_index=2, target_effect_index=0,
    )
    assert result["reordered"] is True
    assert result["converted_to_sandwich"] is True
    filters = patcher.list_effects(project, (0, 0))
    services = [f["mlt_service"] for f in filters]
    # mask_start should now precede the target (brightness).
    assert services[0] == "mask_start"
    assert "mask_apply" in services
    mask_idx = services.index("mask_start")
    target_idx = services.index("brightness")
    apply_idx = services.index("mask_apply")
    assert mask_idx < target_idx < apply_idx


# ---------------------------------------------------------------------------
# SR-16: out-of-range indices -> IndexError naming stack length.
# ---------------------------------------------------------------------------

def test_apply_mask_out_of_range():
    project = _make_project_with_roto_and_target()
    with pytest.raises(IndexError, match="2 filters"):
        masking.apply_mask_to_effect(
            project, (0, 0),
            mask_effect_index=5, target_effect_index=1,
        )
    with pytest.raises(IndexError, match="2 filters"):
        masking.apply_mask_to_effect(
            project, (0, 0),
            mask_effect_index=0, target_effect_index=9,
        )


# ---------------------------------------------------------------------------
# SR-17: wrong service -> ValueError naming actual service.
# ---------------------------------------------------------------------------

def test_apply_mask_wrong_service():
    pl0 = Playlist(
        id="playlist0",
        entries=[PlaylistEntry(
            producer_id="producer_a", in_point=0, out_point=100,
        )],
    )
    project = KdenliveProject(playlists=[pl0])
    brightness_xml = _build_filter_xml(
        0, 0, "brightness", {"kdenlive_id": "brightness"},
    )
    target_xml = _build_filter_xml(
        0, 0, "volume", {"kdenlive_id": "volume"},
    )
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=brightness_xml,
        position_hint="after_tractor",
    ))
    project.opaque_elements.append(OpaqueElement(
        tag="filter", xml_string=target_xml,
        position_hint="after_tractor",
    ))

    with pytest.raises(ValueError, match="brightness"):
        masking.apply_mask_to_effect(
            project, (0, 0),
            mask_effect_index=0, target_effect_index=1,
        )


# ---------------------------------------------------------------------------
# SR-18 / idempotency: second invocation is a no-op.
# ---------------------------------------------------------------------------

def test_apply_mask_idempotent():
    project = _make_project_with_roto_and_target()
    first = masking.apply_mask_to_effect(
        project, (0, 0),
        mask_effect_index=0, target_effect_index=1,
    )
    assert first["converted_to_sandwich"] is True

    filters_after_first = patcher.list_effects(project, (0, 0))
    services_first = [f["mlt_service"] for f in filters_after_first]
    assert services_first == ["mask_start", "brightness", "mask_apply"]

    # Second invocation: mask is now at index 0 (already mask_start),
    # target still at index 1. Should NOT add another mask_apply and
    # should report converted=False.
    second = masking.apply_mask_to_effect(
        project, (0, 0),
        mask_effect_index=0, target_effect_index=1,
    )
    assert second["converted_to_sandwich"] is False
    assert second["reordered"] is False
    assert second["mask_apply_effect_index"] == 2

    filters_after_second = patcher.list_effects(project, (0, 0))
    services_second = [f["mlt_service"] for f in filters_after_second]
    assert services_second == ["mask_start", "brightness", "mask_apply"]
    # Exactly one mask_apply.
    assert services_second.count("mask_apply") == 1
