"""Tests for patcher effect-property accessors."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import (
    get_effect_property,
    list_effects,
    set_effect_property,
)


def _build_filter_xml(
    track: int,
    clip_index: int,
    mlt_service: str,
    properties: dict[str, str],
    filter_id: str | None = None,
) -> str:
    root = ET.Element("filter")
    if filter_id is not None:
        root.set("id", filter_id)
    root.set("mlt_service", mlt_service)
    root.set("track", str(track))
    root.set("clip_index", str(clip_index))
    for name, value in properties.items():
        sub = ET.SubElement(root, "property", {"name": name})
        sub.text = value
    return ET.tostring(root, encoding="unicode")


def _make_project_with_filters() -> KdenliveProject:
    # two playlists (tracks 0 and 1 are dummy, track 2 has one clip)
    pl0 = Playlist(id="playlist0", entries=[])
    pl1 = Playlist(id="playlist1", entries=[])
    pl2 = Playlist(
        id="playlist2",
        entries=[PlaylistEntry(producer_id="producer_a", in_point=0, out_point=100)],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])

    # Filter 0: affine transform with rect property and kdenlive_id=transform
    f0_xml = _build_filter_xml(
        track=2,
        clip_index=0,
        mlt_service="affine",
        properties={
            "kdenlive_id": "transform",
            "rect": "00:00:00.000=0 0 1920 1080 1",
        },
        filter_id="effect_2_0_affine",
    )
    # Filter 1: avfilter.eq without kdenlive_id
    f1_xml = _build_filter_xml(
        track=2,
        clip_index=0,
        mlt_service="avfilter.eq",
        properties={"av.brightness": "0.1"},
        filter_id="effect_2_0_avfilter.eq",
    )

    project.opaque_elements.append(
        OpaqueElement(tag="filter", xml_string=f0_xml, position_hint="after_tractor")
    )
    project.opaque_elements.append(
        OpaqueElement(tag="filter", xml_string=f1_xml, position_hint="after_tractor")
    )
    return project


def _make_empty_project() -> KdenliveProject:
    pl0 = Playlist(id="playlist0", entries=[])
    pl1 = Playlist(id="playlist1", entries=[])
    pl2 = Playlist(
        id="playlist2",
        entries=[PlaylistEntry(producer_id="producer_a", in_point=0, out_point=100)],
    )
    return KdenliveProject(playlists=[pl0, pl1, pl2])


def test_list_effects_returns_filter_stack_in_order():
    project = _make_project_with_filters()
    effects = list_effects(project, (2, 0))
    assert len(effects) == 2
    assert effects[0]["index"] == 0
    assert effects[0]["mlt_service"] == "affine"
    assert effects[0]["kdenlive_id"] == "transform"
    assert effects[0]["properties"]["rect"] == "00:00:00.000=0 0 1920 1080 1"
    assert effects[1]["index"] == 1
    assert effects[1]["mlt_service"] == "avfilter.eq"
    assert effects[1]["kdenlive_id"] == ""
    assert effects[1]["properties"]["av.brightness"] == "0.1"


def test_get_effect_property_returns_existing_value():
    project = _make_project_with_filters()
    value = get_effect_property(project, (2, 0), 0, "rect")
    assert value == "00:00:00.000=0 0 1920 1080 1"


def test_get_effect_property_missing_property_returns_none():
    project = _make_project_with_filters()
    assert get_effect_property(project, (2, 0), 0, "nonexistent") is None


def test_get_effect_property_bad_effect_index_raises_index_error():
    project = _make_project_with_filters()
    with pytest.raises(IndexError) as exc:
        get_effect_property(project, (2, 0), 99, "rect")
    assert "99" in str(exc.value)
    assert "2" in str(exc.value)


def test_get_effect_property_bad_clip_ref_raises_index_error():
    project = _make_project_with_filters()
    with pytest.raises(IndexError) as exc:
        get_effect_property(project, (99, 0), 0, "rect")
    assert "track_index" in str(exc.value)

    with pytest.raises(IndexError) as exc:
        get_effect_property(project, (2, 99), 0, "rect")
    assert "clip_index" in str(exc.value)


def test_set_effect_property_mutates_xml_string():
    project = _make_project_with_filters()
    new_rect = "00:00:01.000=100 50 1920 1080 0.5"
    set_effect_property(project, (2, 0), 0, "rect", new_rect)

    # Find the affine filter element and confirm xml contains new value
    affine_elem = project.opaque_elements[0]
    assert new_rect in affine_elem.xml_string


def test_set_effect_property_roundtrip_with_get():
    project = _make_project_with_filters()
    new_rect = "00:00:02.000=10 20 640 360 1"
    set_effect_property(project, (2, 0), 0, "rect", new_rect)
    assert get_effect_property(project, (2, 0), 0, "rect") == new_rect

    # Creating a new property via set should also round-trip
    set_effect_property(project, (2, 0), 1, "newprop", "hello")
    assert get_effect_property(project, (2, 0), 1, "newprop") == "hello"


def test_list_effects_empty_when_no_filters():
    project = _make_empty_project()
    assert list_effects(project, (2, 0)) == []
