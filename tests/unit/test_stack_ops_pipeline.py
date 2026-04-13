"""Tests for stack-ops pipeline (Sub-Spec 2 of Stack Ops)."""
from __future__ import annotations

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.pipelines import stack_ops


# --- helpers --------------------------------------------------------------


def _filter_xml(
    track: int,
    clip: int,
    mlt_service: str,
    kdenlive_id: str = "",
    extra_properties: dict[str, str] | None = None,
    filter_id: str | None = None,
) -> str:
    """Build a filter XML string by hand to preserve byte-exactness."""
    fid = f' id="{filter_id}"' if filter_id else ""
    attrs = f'{fid} mlt_service="{mlt_service}" track="{track}" clip_index="{clip}"'
    inner = ""
    if kdenlive_id:
        inner += f'<property name="kdenlive_id">{kdenlive_id}</property>'
    for name, value in (extra_properties or {}).items():
        inner += f'<property name="{name}">{value}</property>'
    return f"<filter{attrs}>{inner}</filter>"


def _make_project(
    filters_per_clip: dict[tuple[int, int], list[tuple[str, str, dict[str, str] | None]]]
    | None = None,
) -> KdenliveProject:
    """Build a project with tracks 0,1,2 where track 2 has 2 clips, track 0 has 1.

    filters_per_clip: mapping (track, clip) -> list of (mlt_service, kdenlive_id, extras).
    """
    pl0 = Playlist(
        id="pl0",
        entries=[PlaylistEntry(producer_id="pa", in_point=0, out_point=100)],
    )
    pl1 = Playlist(id="pl1", entries=[])
    pl2 = Playlist(
        id="pl2",
        entries=[
            PlaylistEntry(producer_id="pb", in_point=0, out_point=100),
            PlaylistEntry(producer_id="pc", in_point=0, out_point=100),
        ],
    )
    project = KdenliveProject(playlists=[pl0, pl1, pl2])
    if filters_per_clip:
        for (t, c), flist in filters_per_clip.items():
            for svc, kid, extras in flist:
                project.opaque_elements.append(
                    OpaqueElement(
                        tag="filter",
                        xml_string=_filter_xml(t, c, svc, kid, extras),
                        position_hint="after_tractor",
                    )
                )
    return project


def _svc_order(project, clip_ref):
    return [e["mlt_service"] for e in patcher.list_effects(project, clip_ref)]


# --- serialize ------------------------------------------------------------


def test_serialize_stack_three_filters():
    project = _make_project(
        {
            (2, 0): [
                ("affine", "transform", None),
                ("avfilter.eq", "eq", None),
                ("volume", "volume", None),
            ]
        }
    )
    out = stack_ops.serialize_stack(project, (2, 0))
    assert out["source_clip"] == [2, 0]
    assert len(out["effects"]) == 3
    for entry in out["effects"]:
        assert set(entry.keys()) >= {"xml", "kdenlive_id", "mlt_service"}
    assert [e["mlt_service"] for e in out["effects"]] == [
        "affine",
        "avfilter.eq",
        "volume",
    ]
    assert out["effects"][0]["kdenlive_id"] == "transform"


def test_serialize_stack_empty():
    project = _make_project()
    out = stack_ops.serialize_stack(project, (2, 0))
    assert out == {"source_clip": [2, 0], "effects": []}


# --- deserialize ----------------------------------------------------------


def test_deserialize_stack_missing_effects_key_raises():
    with pytest.raises(ValueError) as exc:
        stack_ops.deserialize_stack({"source_clip": [0, 0]})
    assert "effects_copy" in str(exc.value)


def test_deserialize_stack_not_a_dict():
    with pytest.raises(ValueError) as exc:
        stack_ops.deserialize_stack("not a dict")  # type: ignore[arg-type]
    assert "effects_copy" in str(exc.value)


def test_deserialize_stack_effects_not_list():
    with pytest.raises(ValueError):
        stack_ops.deserialize_stack({"effects": "nope"})


def test_deserialize_stack_entry_missing_xml():
    with pytest.raises(ValueError) as exc:
        stack_ops.deserialize_stack({"effects": [{"kdenlive_id": "x"}]})
    assert "[0]" in str(exc.value)


def test_deserialize_stack_returns_xml_list():
    project = _make_project(
        {
            (2, 0): [
                ("affine", "transform", None),
                ("volume", "volume", None),
            ]
        }
    )
    stack = stack_ops.serialize_stack(project, (2, 0))
    xmls = stack_ops.deserialize_stack(stack)
    assert isinstance(xmls, list)
    assert all(isinstance(x, str) for x in xmls)
    assert xmls == [e["xml"] for e in stack["effects"]]


# --- apply_paste ----------------------------------------------------------


def test_apply_paste_append():
    # source: (2,1) has 2 filters; target: (2,0) has 2 filters
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None), ("volume", "volume", None)],
            (2, 1): [("brightness", "brightness", None), ("avfilter.eq", "eq", None)],
        }
    )
    stack = stack_ops.serialize_stack(project, (2, 1))
    n = stack_ops.apply_paste(project, (2, 0), stack, mode="append")
    assert n == 2
    assert _svc_order(project, (2, 0)) == [
        "affine",
        "volume",
        "brightness",
        "avfilter.eq",
    ]


def test_apply_paste_prepend():
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None), ("volume", "volume", None)],
            (2, 1): [("brightness", "brightness", None), ("avfilter.eq", "eq", None)],
        }
    )
    stack = stack_ops.serialize_stack(project, (2, 1))
    stack_ops.apply_paste(project, (2, 0), stack, mode="prepend")
    assert _svc_order(project, (2, 0)) == [
        "brightness",
        "avfilter.eq",
        "affine",
        "volume",
    ]


def test_apply_paste_replace():
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None), ("volume", "volume", None)],
            (2, 1): [("brightness", "brightness", None), ("avfilter.eq", "eq", None)],
        }
    )
    stack = stack_ops.serialize_stack(project, (2, 1))
    stack_ops.apply_paste(project, (2, 0), stack, mode="replace")
    assert _svc_order(project, (2, 0)) == ["brightness", "avfilter.eq"]


def test_apply_paste_rewrites_track_clip_attrs():
    # Source is on (2, 0); paste to (0, 0) — should be scoped to (0, 0).
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None)],
        }
    )
    # Also ensure target (0, 0) exists with nothing
    stack = stack_ops.serialize_stack(project, (2, 0))
    stack_ops.apply_paste(project, (0, 0), stack, mode="append")

    # New filter should appear scoped to (0,0)
    filters_00 = patcher._iter_clip_filters(project, (0, 0))
    assert len(filters_00) == 1
    _idx, _elem, root = filters_00[0]
    assert root.get("track") == "0"
    assert root.get("clip_index") == "0"
    # Source untouched
    assert len(patcher._iter_clip_filters(project, (2, 0))) == 1


def test_apply_paste_empty_noop():
    project = _make_project(
        {
            (2, 0): [("affine", "transform", None), ("volume", "volume", None)],
        }
    )
    empty_stack = {"source_clip": [2, 1], "effects": []}
    n = stack_ops.apply_paste(project, (2, 0), empty_stack, mode="append")
    assert n == 0
    assert _svc_order(project, (2, 0)) == ["affine", "volume"]


def test_apply_paste_invalid_mode_raises():
    project = _make_project({(2, 0): [("affine", "transform", None)]})
    stack = stack_ops.serialize_stack(project, (2, 0))
    with pytest.raises(ValueError) as exc:
        stack_ops.apply_paste(project, (2, 1), stack, mode="merge")  # type: ignore[arg-type]
    msg = str(exc.value)
    assert "append" in msg and "prepend" in msg and "replace" in msg


def test_apply_paste_preserves_keyframe_strings_byte_exact():
    # Build a filter with a non-trivial keyframe animation string that ET
    # round-tripping would be apt to reformat.
    keyframe_str = (
        "00:00:00.000=100 100 200 200 1;"
        "00:00:01.000~=150 150 200 200 0.5;"
        "00:00:02.000|=200 200 300 300 1"
    )
    project = _make_project(
        {
            (2, 0): [
                (
                    "affine",
                    "transform",
                    {"rect": keyframe_str, "kdenlive:collapsed": "0"},
                )
            ]
        }
    )
    original_xml = project.opaque_elements[0].xml_string

    stack = stack_ops.serialize_stack(project, (2, 0))
    # Sanity: xml carried verbatim
    assert stack["effects"][0]["xml"] == original_xml
    assert keyframe_str in stack["effects"][0]["xml"]

    # Round-trip through deserialize + apply_paste to (0, 0)
    xmls = stack_ops.deserialize_stack(stack)
    assert keyframe_str in xmls[0]

    stack_ops.apply_paste(project, (0, 0), stack, mode="append")

    # Locate the pasted filter and extract rect property text.
    filters_00 = patcher._iter_clip_filters(project, (0, 0))
    assert len(filters_00) == 1
    _idx, elem, root = filters_00[0]
    rect_prop = None
    for child in root:
        if child.tag == "property" and child.get("name") == "rect":
            rect_prop = child.text
            break
    assert rect_prop == keyframe_str
    # And the raw xml_string of the pasted filter must still contain the
    # animation string byte-exact.
    assert keyframe_str in elem.xml_string


def test_apply_paste_rewrites_when_source_attrs_absent():
    """Filter XML without track/clip_index should get them injected."""
    # Manually craft a filter with no track/clip_index
    xml_no_scope = (
        '<filter id="f1" mlt_service="brightness">'
        '<property name="kdenlive_id">brightness</property>'
        "</filter>"
    )
    project = _make_project({(2, 0): [("affine", "transform", None)]})
    stack = {
        "source_clip": [-1, -1],
        "effects": [
            {"xml": xml_no_scope, "kdenlive_id": "brightness", "mlt_service": "brightness"}
        ],
    }
    stack_ops.apply_paste(project, (2, 0), stack, mode="append")
    filters = patcher._iter_clip_filters(project, (2, 0))
    assert len(filters) == 2
    # The newly appended filter should be the brightness one, scoped to (2,0)
    _idx, _elem, root = filters[1]
    assert root.get("track") == "2"
    assert root.get("clip_index") == "0"
    assert root.get("mlt_service") == "brightness"


# --- reorder_stack --------------------------------------------------------


def test_reorder_stack_passthrough():
    project_a = _make_project(
        {
            (2, 0): [
                ("affine", "transform", None),
                ("avfilter.eq", "eq", None),
                ("volume", "volume", None),
            ]
        }
    )
    project_b = _make_project(
        {
            (2, 0): [
                ("affine", "transform", None),
                ("avfilter.eq", "eq", None),
                ("volume", "volume", None),
            ]
        }
    )
    stack_ops.reorder_stack(project_a, (2, 0), 0, 2)
    patcher.reorder_effects(project_b, (2, 0), 0, 2)
    assert _svc_order(project_a, (2, 0)) == _svc_order(project_b, (2, 0))
    assert _svc_order(project_a, (2, 0)) == ["avfilter.eq", "volume", "affine"]
