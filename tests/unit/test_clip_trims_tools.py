"""clip_slip / clip_slide / clip_replace / clip_ripple_insert shells (prompt 20)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, sequence_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_versioned
from workshop_video_brain.edit_mcp.server.bundles.clip_trims import (
    clip_replace,
    clip_ripple_insert,
    clip_slide,
    clip_slip,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project
from workshop_video_brain.workspace.manager import WorkspaceManager
from workshop_video_brain.workspace.manifest import read_manifest

R, G, B = "0xff0000ff", "0x00ff00ff", "0x0000ffff"


@pytest.fixture
def ws(tmp_path) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Trims", tmp_path, workspace_root=root)
    serialize_versioned(sequence_project([R, B, G]), root, read_manifest(root).slug)
    return root


def _latest(root):
    return parse_project(latest_project((root / "projects" / "working_copies").glob("*.kdenlive")))


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def _spans(project, index):
    return [(e.producer_id, e.in_point, e.out_point) for e in project.playlists[index].entries]


def test_registered():
    assert_registered("clip_slip", "clip_slide", "clip_replace", "clip_ripple_insert")


def test_slip(ws):
    data = _ok(call_tool(clip_slip, str(ws), 1, 0.4))  # 25 fps: 10 frames
    assert data["delta_frames"] == 10
    assert (data["after"]["in_frame"], data["after"]["out_frame"]) == (10, 34)
    assert data["after"]["start_frame"] == data["before"]["start_frame"]
    assert data["after"]["track_frames"] == data["before"]["track_frames"]
    assert data["after"]["audio_synced"] is True
    project = _latest(ws)
    assert _spans(project, 0) == _spans(project, 1)


def test_slip_past_source_end_is_refused(ws):
    result = call_tool(clip_slip, str(ws), 1, 1.0)  # 25 frames > the 10 spare
    assert result["error_type"] == "invalid_input"
    assert "past the end of the source" in result["message"]


def test_slide(ws):
    _ok(call_tool(clip_slip, str(ws), 2, 0.2))  # give the next clip a 5-frame head handle
    data = _ok(call_tool(clip_slide, str(ws), 1, 0.2))
    assert data["after"]["start_frame"] == data["before"]["start_frame"] + 5
    assert data["after"]["track_frames"] == data["before"]["track_frames"]
    assert data["after"]["audio_synced"] is True


def test_slide_first_clip_back_is_refused(ws):
    result = call_tool(clip_slide, str(ws), 0, -0.2)
    assert result["error_type"] == "invalid_input" and "nothing before" in result["message"]


def test_replace_with_existing_producer(ws):
    data = _ok(call_tool(clip_replace, str(ws), 1, "producer_2", 0.12))
    assert (data["after"]["producer_id"], data["after"]["in_frame"]) == ("producer_2", 3)
    assert data["after"]["track_frames"] == data["before"]["track_frames"]


def test_replace_missing_media(ws):
    assert call_tool(clip_replace, str(ws), 1, str(ws / "nope.mp4"))["error_type"] == "missing_file"


def test_ripple_insert(ws):
    data = _ok(call_tool(clip_ripple_insert, str(ws), "producer_0", 1, 0.0, 0.4))
    assert data["length_frames"] == 10
    assert data["track_frames_after"] == data["track_frames_before"] + 10
    assert data["inserted"]["start_frame"] == 25
    project = _latest(ws)
    assert [p for p, _i, _o in _spans(project, 0)] == ["producer_0", "producer_0", "producer_1", "producer_2"]


@pytest.mark.parametrize("call", [
    lambda ws: call_tool(clip_slip, str(ws), 7, 0.2),
    lambda ws: call_tool(clip_slide, str(ws), 1, 0.2, track=4),
    lambda ws: call_tool(clip_ripple_insert, str(ws), "producer_0", 9),
])
def test_bad_indices(ws, call):
    assert call(ws)["error_type"] == "invalid_index"


def test_zero_offset(ws):
    assert call_tool(clip_slip, str(ws), 1, 0.001)["error_type"] == "invalid_input"
