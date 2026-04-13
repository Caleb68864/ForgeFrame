"""Tests for patcher stack-mutation extensions (Sub-Spec 1 of Stack Ops)."""
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
    insert_effect_xml,
    list_effects,
    remove_effect,
    reorder_effects,
)


def _build_filter_xml(
    track: int,
    clip_index: int,
    mlt_service: str,
    properties: dict[str, str] | None = None,
    filter_id: str | None = None,
) -> str:
    root = ET.Element("filter")
    if filter_id is not None:
        root.set("id", filter_id)
    root.set("mlt_service", mlt_service)
    root.set("track", str(track))
    root.set("clip_index", str(clip_index))
    for name, value in (properties or {}).items():
        sub = ET.SubElement(root, "property", {"name": name})
        sub.text = value
    return ET.tostring(root, encoding="unicode")


def _make_project() -> KdenliveProject:
    """Project with track 2 carrying 3 filters on clip 0, plus a filter on
    clip 1 of track 2 and a filter on track 0's clip 0 for isolation tests."""
    pl0 = Playlist(
        id="playlist0",
        entries=[PlaylistEntry(producer_id="producer_a", in_point=0, out_point=100)],
    )
    pl1 = Playlist(id="playlist1", entries=[])
    pl2 = Playlist(
        id="playlist2",
        entries=[
            PlaylistEntry(producer_id="producer_b", in_point=0, out_point=100),
            PlaylistEntry(producer_id="producer_c", in_point=0, out_point=100),
        ],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])

    def _filter(track, clip, svc, fid):
        return OpaqueElement(
            tag="filter",
            xml_string=_build_filter_xml(track, clip, svc, filter_id=fid),
            position_hint="after_tractor",
        )

    # three filters on (2, 0)
    project.opaque_elements.append(_filter(2, 0, "affine", "fa"))
    project.opaque_elements.append(_filter(2, 0, "avfilter.eq", "fb"))
    project.opaque_elements.append(_filter(2, 0, "volume", "fc"))
    # one filter on (2, 1)
    project.opaque_elements.append(_filter(2, 1, "affine", "other_21"))
    # one filter on (0, 0)
    project.opaque_elements.append(_filter(0, 0, "affine", "other_00"))
    return project


def _svc_order(project: KdenliveProject, clip_ref: tuple[int, int]) -> list[str]:
    return [e["mlt_service"] for e in list_effects(project, clip_ref)]


# --- insert tests ---------------------------------------------------------


def test_insert_effect_xml_at_top():
    project = _make_project()
    new_xml = _build_filter_xml(2, 0, "brightness", filter_id="new")
    insert_effect_xml(project, (2, 0), new_xml, 0)
    assert _svc_order(project, (2, 0)) == [
        "brightness",
        "affine",
        "avfilter.eq",
        "volume",
    ]


def test_insert_effect_xml_at_bottom():
    project = _make_project()
    new_xml = _build_filter_xml(2, 0, "brightness", filter_id="new")
    insert_effect_xml(project, (2, 0), new_xml, 3)
    assert _svc_order(project, (2, 0)) == [
        "affine",
        "avfilter.eq",
        "volume",
        "brightness",
    ]


def test_insert_effect_xml_middle():
    project = _make_project()
    new_xml = _build_filter_xml(2, 0, "brightness", filter_id="new")
    insert_effect_xml(project, (2, 0), new_xml, 1)
    assert _svc_order(project, (2, 0)) == [
        "affine",
        "brightness",
        "avfilter.eq",
        "volume",
    ]


def test_insert_into_empty_stack():
    """Inserting into a clip with no filters appends to opaque_elements."""
    pl0 = Playlist(id="p0", entries=[])
    pl1 = Playlist(id="p1", entries=[])
    pl2 = Playlist(
        id="p2",
        entries=[PlaylistEntry(producer_id="pa", in_point=0, out_point=100)],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])
    new_xml = _build_filter_xml(2, 0, "brightness", filter_id="new")
    insert_effect_xml(project, (2, 0), new_xml, 0)
    assert _svc_order(project, (2, 0)) == ["brightness"]


# --- remove tests ---------------------------------------------------------


def test_remove_effect_middle():
    project = _make_project()
    remove_effect(project, (2, 0), 1)
    assert _svc_order(project, (2, 0)) == ["affine", "volume"]


# --- reorder tests --------------------------------------------------------


def test_reorder_effects_to_top():
    project = _make_project()
    reorder_effects(project, (2, 0), 2, 0)
    assert _svc_order(project, (2, 0)) == ["volume", "affine", "avfilter.eq"]


def test_reorder_effects_noop():
    project = _make_project()
    before = list(project.opaque_elements)
    reorder_effects(project, (2, 0), 1, 1)
    # Same objects, same order
    assert project.opaque_elements == before
    assert all(
        a is b for a, b in zip(project.opaque_elements, before, strict=True)
    )


def test_reorder_effects_to_bottom():
    project = _make_project()
    reorder_effects(project, (2, 0), 0, 2)
    assert _svc_order(project, (2, 0)) == ["avfilter.eq", "volume", "affine"]


# --- error handling -------------------------------------------------------


def test_insert_invalid_position_raises():
    project = _make_project()
    new_xml = _build_filter_xml(2, 0, "brightness")
    with pytest.raises(IndexError) as exc:
        insert_effect_xml(project, (2, 0), new_xml, -1)
    assert "3" in str(exc.value)

    with pytest.raises(IndexError) as exc:
        insert_effect_xml(project, (2, 0), new_xml, 4)
    assert "3" in str(exc.value)


def test_remove_invalid_index_raises():
    project = _make_project()
    with pytest.raises(IndexError) as exc:
        remove_effect(project, (2, 0), 99)
    assert "3" in str(exc.value)


def test_reorder_invalid_index_raises():
    project = _make_project()
    with pytest.raises(IndexError):
        reorder_effects(project, (2, 0), 99, 0)
    with pytest.raises(IndexError):
        reorder_effects(project, (2, 0), 0, 99)


# --- isolation ------------------------------------------------------------


def test_other_clips_untouched():
    project = _make_project()
    assert len(list_effects(project, (2, 1))) == 1
    assert len(list_effects(project, (0, 0))) == 1

    new_xml = _build_filter_xml(2, 0, "brightness")
    insert_effect_xml(project, (2, 0), new_xml, 0)
    remove_effect(project, (2, 0), 3)
    reorder_effects(project, (2, 0), 0, 2)

    assert len(list_effects(project, (2, 1))) == 1
    assert list_effects(project, (2, 1))[0]["mlt_service"] == "affine"
    assert len(list_effects(project, (0, 0))) == 1
    assert list_effects(project, (0, 0))[0]["mlt_service"] == "affine"
