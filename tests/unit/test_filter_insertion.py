"""Tests for Kdenlive filter and composition insertion via patcher."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.core.models.timeline import AddEffect, AddComposition
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _minimal_project() -> KdenliveProject:
    """Create a minimal KdenliveProject with one video track and two clips."""
    return KdenliveProject(
        profile=ProjectProfile(width=1920, height=1080, fps=25.0),
        producers=[
            Producer(id="producer0", resource="/media/clip_a.mp4"),
            Producer(id="producer1", resource="/media/clip_b.mp4"),
        ],
        tracks=[
            Track(id="playlist0", track_type="video", name="V1"),
            Track(id="playlist1", track_type="video", name="V2"),
        ],
        playlists=[
            Playlist(
                id="playlist0",
                entries=[
                    PlaylistEntry(producer_id="producer0", in_point=0, out_point=100),
                    PlaylistEntry(producer_id="producer1", in_point=0, out_point=200),
                ],
            ),
            Playlist(
                id="playlist1",
                entries=[
                    PlaylistEntry(producer_id="producer0", in_point=50, out_point=150),
                ],
            ),
        ],
        guides=[],
        opaque_elements=[],
    )


# ---------------------------------------------------------------------------
# AddEffect tests
# ---------------------------------------------------------------------------

class TestAddEffect:
    def test_effect_appended_as_opaque_element(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=0,
            effect_name="brightness",
            params={"av.brightness": "0.1"},
        )

        result = patch_project(project, [intent])

        # Should have one new opaque element
        assert len(result.opaque_elements) == 1
        elem = result.opaque_elements[0]
        assert elem.tag == "filter"

        # Parse the XML and verify structure
        xml_elem = ET.fromstring(elem.xml_string)
        assert xml_elem.get("mlt_service") == "brightness"

        # Verify params are present as <property> children
        props = {p.get("name"): p.text for p in xml_elem.findall("property")}
        assert props["av.brightness"] == "0.1"

    def test_multiple_effects_appended_not_replaced(self):
        project = _minimal_project()
        intents = [
            AddEffect(
                track_index=0,
                clip_index=0,
                effect_name="brightness",
                params={"av.brightness": "0.1"},
            ),
            AddEffect(
                track_index=0,
                clip_index=0,
                effect_name="volume",
                params={"level": "0.8"},
            ),
        ]

        result = patch_project(project, intents)

        assert len(result.opaque_elements) == 2
        services = []
        for elem in result.opaque_elements:
            xml_elem = ET.fromstring(elem.xml_string)
            services.append(xml_elem.get("mlt_service"))
        assert "brightness" in services
        assert "volume" in services

    def test_effect_references_correct_clip(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=1,
            effect_name="charcoal",
            params={},
        )

        result = patch_project(project, [intent])

        elem = result.opaque_elements[0]
        xml_elem = ET.fromstring(elem.xml_string)
        # Should reference the correct track and clip index
        assert xml_elem.get("track") == "0"
        assert xml_elem.get("clip_index") == "1"

    def test_effect_invalid_track_index_skipped(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=99,
            clip_index=0,
            effect_name="brightness",
            params={},
        )

        result = patch_project(project, [intent])

        # No opaque elements should be added
        assert len(result.opaque_elements) == 0

    def test_effect_invalid_clip_index_skipped(self):
        project = _minimal_project()
        intent = AddEffect(
            track_index=0,
            clip_index=99,
            effect_name="brightness",
            params={},
        )

        result = patch_project(project, [intent])

        assert len(result.opaque_elements) == 0

    def test_original_project_not_mutated(self):
        project = _minimal_project()
        original_count = len(project.opaque_elements)
        intent = AddEffect(
            track_index=0,
            clip_index=0,
            effect_name="brightness",
            params={"av.brightness": "0.5"},
        )

        result = patch_project(project, [intent])

        assert len(project.opaque_elements) == original_count
        assert len(result.opaque_elements) == 1


# ---------------------------------------------------------------------------
# AddComposition tests
# ---------------------------------------------------------------------------

class TestAddComposition:
    def test_composition_appended_as_transition(self):
        project = _minimal_project()
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=50,
            end_frame=100,
            composition_type="luma",
            params={"softness": "0.5"},
        )

        result = patch_project(project, [intent])

        assert len(result.opaque_elements) == 1
        elem = result.opaque_elements[0]
        assert elem.tag == "transition"

        xml_elem = ET.fromstring(elem.xml_string)
        assert xml_elem.get("mlt_service") == "luma"

        # Verify track routing
        props = {p.get("name"): p.text for p in xml_elem.findall("property")}
        assert props["a_track"] == "0"
        assert props["b_track"] == "1"
        assert props["in"] == "50"
        assert props["out"] == "100"
        assert props["softness"] == "0.5"

    def test_composition_preserves_existing_transitions(self):
        project = _minimal_project()
        # Add a pre-existing opaque transition
        existing = OpaqueElement(
            tag="transition",
            xml_string='<transition mlt_service="mix"><property name="a_track">0</property></transition>',
            position_hint="after_tractor",
        )
        project.opaque_elements.append(existing)

        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=25,
            composition_type="composite",
            params={},
        )

        result = patch_project(project, [intent])

        # Both old and new should be present
        assert len(result.opaque_elements) == 2
        tags = [e.tag for e in result.opaque_elements]
        assert tags.count("transition") == 2

    def test_composition_with_no_params(self):
        project = _minimal_project()
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=50,
            composition_type="dissolve",
            params={},
        )

        result = patch_project(project, [intent])

        elem = result.opaque_elements[0]
        xml_elem = ET.fromstring(elem.xml_string)
        # Should have only the core properties (a_track, b_track, in, out), no extra params
        prop_names = {p.get("name") for p in xml_elem.findall("property")}
        assert "a_track" in prop_names
        assert "b_track" in prop_names
        assert "in" in prop_names
        assert "out" in prop_names

    def test_original_project_not_mutated_composition(self):
        project = _minimal_project()
        original_count = len(project.opaque_elements)
        intent = AddComposition(
            track_a=0,
            track_b=1,
            start_frame=0,
            end_frame=50,
            composition_type="luma",
            params={},
        )

        result = patch_project(project, [intent])

        assert len(project.opaque_elements) == original_count
        assert len(result.opaque_elements) == 1
