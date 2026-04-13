"""Structural-equivalence regression test for apply_pip after its rewire to
delegate through ``apply_composite``.

Byte-identity with the pre-rewire serializer output is NOT achievable because
the emitted ``mlt_service`` changes from ``"composite"`` (no blend-mode prop)
to ``"frei0r.cairoblend"`` (blend-mode-aware). See Sub-Spec 2 Escalation
Trigger 1. This test locks the NEW externally observable contract: same
geometry, same frame range, same track ordering, no extra/lost params beyond
the expected blend-mode property.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.compositing import PipLayout
from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.pipelines.compositing import apply_pip


def _make_project() -> KdenliveProject:
    return KdenliveProject.model_validate({
        "profile": {"width": 1920, "height": 1080, "colorspace": "709"},
        "tracks": [{"id": "0"}, {"id": "1"}, {"id": "2"}],
    })


def test_apply_pip_emits_expected_transition_structure() -> None:
    project = _make_project()
    before = len(project.opaque_elements)

    layout = PipLayout(x=1440, y=780, width=480, height=270)
    result = apply_pip(
        project,
        overlay_track=2,
        base_track=1,
        start_frame=0,
        end_frame=120,
        layout=layout,
    )

    # Exactly one transition added.
    assert len(result.opaque_elements) == before + 1
    element = result.opaque_elements[-1]
    assert element.tag == "transition"

    root = ET.fromstring(element.xml_string)
    assert root.tag == "transition"
    assert root.attrib.get("mlt_service") == "frei0r.cairoblend"

    props = {p.attrib["name"]: (p.text or "") for p in root.findall("property")}

    # Core properties -- track ordering preserved (base=1 -> a_track, overlay=2 -> b_track).
    assert props["a_track"] == "1"
    assert props["b_track"] == "2"
    assert props["in"] == "0"
    assert props["out"] == "120"

    # Geometry string is unchanged from pre-rewire format.
    assert props["geometry"] == "1440/780:480x270:100"

    # Blend-mode property from BLEND_MODE_TO_MLT["cairoblend"].
    assert props["1"] == "normal"

    # No other params leaked in.
    expected_keys = {"a_track", "b_track", "in", "out", "geometry", "1"}
    assert set(props.keys()) == expected_keys, (
        f"Unexpected transition properties: {set(props.keys()) - expected_keys}"
    )


def test_apply_pip_deep_copies_input_project() -> None:
    project = _make_project()
    layout = PipLayout(x=0, y=0, width=480, height=270)
    result = apply_pip(
        project,
        overlay_track=1,
        base_track=0,
        start_frame=0,
        end_frame=60,
        layout=layout,
    )
    assert result is not project
    assert len(project.opaque_elements) == 0
