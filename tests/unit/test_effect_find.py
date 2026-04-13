"""Tests for effect_find.find()."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
)
from workshop_video_brain.edit_mcp.pipelines import effect_find


def _filter_xml(
    track: int,
    clip_index: int,
    mlt_service: str,
    properties: dict[str, str],
) -> str:
    root = ET.Element("filter")
    root.set("mlt_service", mlt_service)
    root.set("track", str(track))
    root.set("clip_index", str(clip_index))
    for name, value in properties.items():
        sub = ET.SubElement(root, "property", {"name": name})
        sub.text = value
    return ET.tostring(root, encoding="unicode")


def _make_project(filters: list[tuple[str, dict[str, str]]]) -> KdenliveProject:
    pl0 = Playlist(id="playlist0", entries=[])
    pl1 = Playlist(id="playlist1", entries=[])
    pl2 = Playlist(
        id="playlist2",
        entries=[PlaylistEntry(producer_id="producer_a", in_point=0, out_point=100)],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])
    for mlt_service, props in filters:
        xml = _filter_xml(2, 0, mlt_service, props)
        project.opaque_elements.append(
            OpaqueElement(tag="filter", xml_string=xml, position_hint="after_tractor")
        )
    return project


def test_find_by_kdenlive_id():
    project = _make_project(
        [
            ("affine", {"kdenlive_id": "transform", "rect": "00:00:00.000=0 0 1920 1080 1"}),
            ("avfilter.eq", {"kdenlive_id": "eq", "av.brightness": "0.1"}),
        ]
    )
    assert effect_find.find(project, (2, 0), "transform") == 0
    assert effect_find.find(project, (2, 0), "eq") == 1


def test_find_falls_back_to_mlt_service():
    project = _make_project(
        [
            ("affine", {"rect": "00:00:00.000=0 0 1920 1080 1"}),
        ]
    )
    assert effect_find.find(project, (2, 0), "affine") == 0


def test_find_raises_lookup_error_with_available_effects_listed():
    project = _make_project(
        [
            ("affine", {"kdenlive_id": "transform"}),
            ("avfilter.eq", {"kdenlive_id": "eq"}),
        ]
    )
    with pytest.raises(LookupError) as excinfo:
        effect_find.find(project, (2, 0), "nonexistent")
    msg = str(excinfo.value)
    assert "nonexistent" in msg
    assert "transform" in msg
    assert "affine" in msg
    assert "eq" in msg
    assert "avfilter.eq" in msg
    assert "index=0" in msg
    assert "index=1" in msg


def test_find_raises_value_error_when_ambiguous_with_indices_listed():
    project = _make_project(
        [
            ("avfilter.eq", {"kdenlive_id": "eq", "av.brightness": "0.1"}),
            ("avfilter.eq", {"kdenlive_id": "eq", "av.brightness": "0.2"}),
        ]
    )
    with pytest.raises(ValueError) as excinfo:
        effect_find.find(project, (2, 0), "eq")
    msg = str(excinfo.value)
    assert "0" in msg and "1" in msg
    assert "effect_index" in msg


def test_find_prefers_kdenlive_id_over_mlt_service():
    # Filter 0 has mlt_service="transform"; filter 1 has kdenlive_id="transform".
    # Resolving "transform" must prefer the kdenlive_id match (index 1), not
    # raise ambiguity with the mlt_service match.
    project = _make_project(
        [
            ("transform", {"kdenlive_id": "something_else"}),
            ("affine", {"kdenlive_id": "transform"}),
        ]
    )
    assert effect_find.find(project, (2, 0), "transform") == 1
