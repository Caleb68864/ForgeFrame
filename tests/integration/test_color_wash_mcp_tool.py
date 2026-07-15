"""Integration tests for the ``effect_color_wash`` bundle MCP tool.

Mirrors the style of ``test_effect_presets.py`` / ``test_stack_ops_mcp_tools.py``:
build an isolated workspace from the shared fixture, drive the registered tool,
and re-parse the project to assert the filter stack.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_color_wash,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"
TRACK = 2
CLIP = 0

EXPECTED_SERVICES = [
    "frei0r.colorize",
    "frei0r.transparency",
    "frei0r.brightness",
    "frei0r.contrast0r",
]


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    res = workspace_create(title="Color Wash Test", media_root=str(media_root))
    assert res["status"] == "success", res
    ws_root = Path(res["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _reparse(ws: Path, pf: str):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    return parse_project(ws / pf)


def _list_filters(ws: Path, pf: str, track: int, clip: int):
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    return patcher.list_effects(_reparse(ws, pf), (track, clip))


@pytest.fixture(autouse=True)
def _isolate_vault(monkeypatch):
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: None)


def test_tool_registered_and_callable():
    assert callable(getattr(tools, "effect_color_wash"))


def test_color_wash_appends_four_filters_in_order(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, color="blue", intensity=0.5, opacity=0.6,
    )
    assert out["status"] == "success", out
    assert out["data"]["filter_count"] == 4
    assert out["data"]["color"] == "blue"
    assert out["data"]["first_effect_index"] >= 0
    assert isinstance(out["data"]["snapshot_id"], str) and out["data"]["snapshot_id"]

    services = [f["mlt_service"] for f in _list_filters(ws, pf, TRACK, CLIP)]
    assert services[-4:] == EXPECTED_SERVICES, services


def test_color_wash_writes_expected_properties(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, color="red", intensity=1.0, opacity=0.4,
    )
    assert out["status"] == "success", out

    filters = _list_filters(ws, pf, TRACK, CLIP)
    by_svc = {f["mlt_service"]: f for f in filters}
    colorize = by_svc["frei0r.colorize"]["properties"]
    assert colorize["hue"] == "0.0000"          # red
    assert colorize["saturation"] == "1.0000"   # intensity 1.0
    assert by_svc["frei0r.transparency"]["properties"]["0"] == "0.4000"


def test_color_wash_snapshot_dir_exists(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    assert (ws / "projects" / "snapshots" / snap_id).is_dir()


def test_color_wash_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file="nope.kdenlive", track=TRACK, clip=CLIP,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_color_wash_bad_clip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=99,
    )
    assert out["status"] == "error"


def test_color_wash_bad_intensity(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP, intensity=3.0,
    )
    assert out["status"] == "error"
    assert "intensity" in out["message"]


def test_color_wash_unknown_color(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_wash(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP, color="chartreuse",
    )
    assert out["status"] == "error"
    assert "chartreuse" in out["message"]
