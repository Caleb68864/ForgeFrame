"""Integration tests for the ``transition_zoom_whip`` bundle MCP tool.

Exercises the tool against a two-clip Kdenlive fixture, following the style of
tests/integration/test_keyframe_mcp_tools.py.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.bundles import zoom_whip as _zw_mod
from workshop_video_brain.edit_mcp.server import tools as _tools_mod

from tests._testkit import registered_tool_names, tool_fn as _callable

transition_zoom_whip = _callable(_zw_mod, "transition_zoom_whip")
workspace_create = _callable(_tools_mod, "workspace_create")

FIXTURE = Path(__file__).parent / "fixtures" / "zoom_whip_project.kdenlive"


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Zoom Whip Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def test_tool_is_registered_via_list_tools():
    assert "transition_zoom_whip" in registered_tool_names()


def test_applies_four_effects_across_the_cut(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=1,
        direction="left", duration_frames=12,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["outgoing"]["transform_effect_index"] == 0
    assert data["outgoing"]["blur_effect_index"] == 1
    assert data["incoming"]["transform_effect_index"] == 0
    assert data["incoming"]["blur_effect_index"] == 1

    # Effects round-trip through the patcher, keyed to the right clips.
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)

    out_effects = patcher.list_effects(project, (2, 0))
    assert [e["mlt_service"] for e in out_effects] == ["affine", "avfilter.dblur"]
    in_effects = patcher.list_effects(project, (2, 1))
    assert [e["mlt_service"] for e in in_effects] == ["affine", "avfilter.dblur"]


def test_keyframe_strings_written_to_project(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=1, easing="cubic",
    )
    assert out["status"] == "success", out
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)

    rect = patcher.get_effect_property(project, (2, 0), 0, "rect")
    assert rect == out["data"]["outgoing"]["transform_rect"]
    assert "g=" in rect  # cubic_in
    radius = patcher.get_effect_property(project, (2, 0), 1, "av.radius")
    assert radius == out["data"]["outgoing"]["blur_radius"]
    angle = patcher.get_effect_property(project, (2, 0), 1, "av.angle")
    assert angle == "0.0"


def test_snapshot_created_before_write(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=1,
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    assert isinstance(snap_id, str) and snap_id
    assert (ws / "projects" / "snapshots" / snap_id).exists()


def test_up_direction_writes_vertical_blur_angle(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=1, direction="up",
    )
    assert out["status"] == "success", out
    assert out["data"]["outgoing"]["blur_angle"] == 90.0


def test_bad_direction_returns_error_dict(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=1, direction="diagonal",
    )
    assert out["status"] == "error"
    assert "direction" in out["message"]


def test_out_of_range_clip_returns_error_dict(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file=pf,
        track=2, out_clip_index=0, in_clip_index=9,
    )
    assert out["status"] == "error"
    assert "in_clip_index" in out["message"]


def test_missing_project_returns_error_dict(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = transition_zoom_whip(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=2, out_clip_index=0, in_clip_index=1,
    )
    assert out["status"] == "error"
    assert "not found" in out["message"]
