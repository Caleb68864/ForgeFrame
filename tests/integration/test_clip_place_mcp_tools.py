"""Integration tests for the clip-placement patcher path and the bundle tools.

Exercises the real patch -> serialize -> re-parse round trip (no melt) plus the
three MCP bundle tools end-to-end against a workspace, and the registration /
``.fn``-unwrap of each tool. Also proves clip-filter ``clip_index`` associations
are remapped through a placement.
"""
from __future__ import annotations

from pathlib import Path

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
from workshop_video_brain.core.models.timeline import MoveClipToTrack, PlaceClip
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import clip_place as cp
from workshop_video_brain.edit_mcp.server.bundles import clip_place as _bundle
from workshop_video_brain.workspace.manager import WorkspaceManager

# @mcp.tool() returns the raw function here; .fn fallback matches other bundles.
clip_place = getattr(_bundle.clip_place, "fn", _bundle.clip_place)
clip_move_to = getattr(_bundle.clip_move_to, "fn", _bundle.clip_move_to)
clip_place_matched = getattr(_bundle.clip_place_matched, "fn", _bundle.clip_place_matched)

FPS = 25.0


def _color_prod(pid: str, resource: str, length: int) -> Producer:
    return Producer(
        id=pid,
        resource=resource,
        properties={"resource": resource, "mlt_service": "color", "length": str(length)},
    )


def _two_track_project() -> KdenliveProject:
    """v1 (100-frame red), v2 (empty), audio -- indices 0,1,2 in playlists."""
    p = KdenliveProject(
        title="place",
        profile=ProjectProfile(width=320, height=180, fps=FPS),
    )
    p.producers = [_color_prod("red", "0xff0000ff", 200)]
    p.tracks = [
        Track(id="v1", track_type="video"),
        Track(id="v2", track_type="video"),
        Track(id="a1", track_type="audio"),
    ]
    p.playlists = [
        Playlist(id="v1", entries=[PlaylistEntry(producer_id="red", in_point=0, out_point=99)]),
        Playlist(id="v2", entries=[]),
        Playlist(id="a1", entries=[]),
    ]
    p.tractor = {"id": "tractor0", "in": "0", "out": "99"}
    return p


def _real(entries):
    return [e for e in entries if e.producer_id]


# ---------------------------------------------------------------------------
# registration / .fn-unwrap
# ---------------------------------------------------------------------------

def test_tools_registered_and_unwrappable():
    for tool in (_bundle.clip_place, _bundle.clip_move_to, _bundle.clip_place_matched):
        fn = getattr(tool, "fn", tool)
        assert callable(fn)


# ---------------------------------------------------------------------------
# patcher round trips
# ---------------------------------------------------------------------------

def test_place_overwrite_survives_serialize_reparse(tmp_path):
    project = _two_track_project()
    patched = patcher.patch_project(
        project,
        [PlaceClip(track_ref="v2", producer_id="blue", source_path="0x0000ffff",
                   in_point=0, out_point=24, at_frame=50, mode="overwrite")],
    )
    out = tmp_path / "place.kdenlive"
    serialize_project(patched, out)
    reparsed = parse_project(out)
    v2 = next(pl for pl in reparsed.playlists if pl.id == "v2")
    spans = [(e.producer_id or "B", cp.entry_length(e)) for e in v2.entries]
    assert spans == [("B", 50), ("blue", 25)]
    assert any(pp.id == "blue" for pp in reparsed.producers)


def test_place_insert_grows_timeline(tmp_path):
    project = _two_track_project()
    patched = patcher.patch_project(
        project,
        [PlaceClip(track_ref="v1", producer_id="blue", source_path="0x0000ffff",
                   in_point=0, out_point=24, at_frame=50, mode="insert")],
    )
    v1 = next(pl for pl in patched.playlists if pl.id == "v1")
    assert cp.playlist_length(v1.entries) == 125
    assert patched.tractor["out"] == "124"


def test_ripple_all_tracks_shifts_guides_and_tracks():
    project = _two_track_project()
    # give v2 content so the ripple is observable
    project.playlists[1].entries = [PlaylistEntry(producer_id="red", in_point=0, out_point=99)]
    project.guides = [__import__(
        "workshop_video_brain.core.models.kdenlive", fromlist=["Guide"]
    ).Guide(position=80, label="g")]
    patched = patcher.patch_project(
        project,
        [PlaceClip(track_ref="v1", producer_id="blue", source_path="0x0000ffff",
                   in_point=0, out_point=24, at_frame=50, mode="insert",
                   ripple_all_tracks=True)],
    )
    v2 = next(pl for pl in patched.playlists if pl.id == "v2")
    # v2 got a 25-frame blank at frame 50
    assert [(e.producer_id or "B", cp.entry_length(e)) for e in v2.entries] == [
        ("red", 50), ("B", 25), ("red", 50),
    ]
    assert patched.guides[0].position == 105  # 80 + 25


def test_clip_filter_index_remapped_through_placement(tmp_path):
    """A filter on v1 clip 0 should follow it when a placement renumbers clips."""
    project = _two_track_project()
    # Put a second clip after red on v1, and a filter on clip index 0 (red).
    project.producers.append(_color_prod("green", "0x00ff00ff", 200))
    project.playlists[0].entries.append(
        PlaylistEntry(producer_id="green", in_point=0, out_point=49)
    )
    filt = (
        '<filter id="f0" mlt_service="grain" track="0" clip_index="0">'
        '<property name="mlt_service">grain</property></filter>'
    )
    project.opaque_elements.append(
        OpaqueElement(tag="filter", xml_string=filt, position_hint="after_tractor")
    )
    # Insert blue at frame 0 on v1 -> red becomes clip index 1, green index 2.
    patched = patcher.patch_project(
        project,
        [PlaceClip(track_ref="v1", producer_id="blue", source_path="0x0000ffff",
                   in_point=0, out_point=9, at_frame=0, mode="insert")],
    )
    # Filter's clip_index should now be 1 (was 0), still targeting red.
    filters = patcher.list_effects(patched, (0, 1))
    assert any(f["mlt_service"] == "grain" for f in filters)
    assert patcher.list_effects(patched, (0, 0)) == []  # blue has no filter


def test_cross_track_move_leaves_blank(tmp_path):
    project = _two_track_project()
    patched = patcher.patch_project(
        project,
        [MoveClipToTrack(from_track_ref="v1", clip_index=0, to_track_ref="v2",
                         at_frame=-1, close_gap=False)],
    )
    v1 = next(pl for pl in patched.playlists if pl.id == "v1")
    v2 = next(pl for pl in patched.playlists if pl.id == "v2")
    assert _real(v1.entries) == []                      # source now blank
    assert cp.entry_length(v1.entries[0]) == 100
    assert [(e.producer_id, cp.entry_length(e)) for e in _real(v2.entries)] == [("red", 100)]


def test_cross_track_move_close_gap():
    project = _two_track_project()
    project.playlists[0].entries.append(
        PlaylistEntry(producer_id="red", in_point=0, out_point=49)
    )  # a second clip after the first
    patched = patcher.patch_project(
        project,
        [MoveClipToTrack(from_track_ref="v1", clip_index=0, to_track_ref="v2",
                         at_frame=0, close_gap=True)],
    )
    v1 = next(pl for pl in patched.playlists if pl.id == "v1")
    # gap closed: the second clip is now first, no leading blank
    assert cp.entry_length(v1.entries[0]) == 50
    assert v1.entries[0].producer_id == "red"


# ---------------------------------------------------------------------------
# bundle tools end-to-end
# ---------------------------------------------------------------------------

@pytest.fixture()
def project_ws(tmp_path):
    ws = WorkspaceManager.create(
        title="Place Test",
        media_root=str(tmp_path / "raw_media"),
        workspace_root=tmp_path / "workspace",
    )
    ws_root = Path(ws.workspace_root)
    proj_rel = "projects/working_copies/place.kdenlive"
    proj_path = ws_root / proj_rel
    proj_path.parent.mkdir(parents=True, exist_ok=True)
    serialize_project(_two_track_project(), proj_path)
    return ws_root, proj_rel


def test_clip_place_tool_by_producer_id(project_ws):
    ws_root, proj_rel = project_ws
    res = clip_place(
        str(ws_root), proj_rel, source_or_producer="red", track=1,
        at_seconds=2.0, in_seconds=0.0, out_seconds=1.0, mode="overwrite",
    )
    assert res["status"] == "success", res
    data = res["data"]
    assert data["at_frame"] == 50           # 2.0s * 25fps
    assert data["clip_length_frames"] == 25  # out_seconds 1.0 -> 25 frames
    assert data["snapshot_id"]
    reparsed = parse_project(ws_root / proj_rel)
    v2 = next(pl for pl in reparsed.playlists if pl.id == "v2")
    assert [(e.producer_id or "B", cp.entry_length(e)) for e in v2.entries] == [
        ("B", 50), ("red", 25),
    ]


def test_clip_place_tool_missing_media_errors(project_ws):
    ws_root, proj_rel = project_ws
    # A media path that does not exist must fail loudly, naming the missing file
    # (not silently placing a broken clip nor bailing with a confusing
    # "duration unknown" message). Regression: composed-workflow propagation.
    res = clip_place(
        str(ws_root), proj_rel, source_or_producer="/nope/missing.mp4", track=1,
        at_seconds=1.0,
    )
    assert res["status"] == "error"
    assert res["error_type"] == "missing_file"
    assert "/nope/missing.mp4" in res["message"]


def test_clip_place_tool_bad_track(project_ws):
    ws_root, proj_rel = project_ws
    res = clip_place(str(ws_root), proj_rel, "red", track=99, at_seconds=1.0, out_seconds=1.0)
    assert res["status"] == "error"


def test_clip_move_to_tool(project_ws):
    ws_root, proj_rel = project_ws
    res = clip_move_to(str(ws_root), proj_rel, from_track=0, clip_index=0, to_track=1)
    assert res["status"] == "success", res
    reparsed = parse_project(ws_root / proj_rel)
    v1 = next(pl for pl in reparsed.playlists if pl.id == "v1")
    v2 = next(pl for pl in reparsed.playlists if pl.id == "v2")
    assert _real(v1.entries) == []
    assert [e.producer_id for e in _real(v2.entries)] == ["red"]


def test_clip_move_to_same_track_rejected(project_ws):
    ws_root, proj_rel = project_ws
    res = clip_move_to(str(ws_root), proj_rel, from_track=0, clip_index=0, to_track=0)
    assert res["status"] == "error"


def test_clip_place_matched_tool(project_ws):
    ws_root, proj_rel = project_ws
    # reference = red clip on track 0 (100 frames); cover it with 'red' on track 1
    res = clip_place_matched(
        str(ws_root), proj_rel, source="red", track=1,
        match_track=0, match_clip_index=0,
    )
    assert res["status"] == "success", res
    data = res["data"]
    assert data["matched_length_frames"] == 100
    assert data["placed_length_frames"] == 100
    assert data["at_frame"] == 0
    reparsed = parse_project(ws_root / proj_rel)
    v2 = next(pl for pl in reparsed.playlists if pl.id == "v2")
    placed = _real(v2.entries)[0]
    assert cp.entry_length(placed) == 100  # exactly the reference duration
