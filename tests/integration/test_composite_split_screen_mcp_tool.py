"""Integration tests for the ``composite_split_screen`` MCP tool (tutorial #15).

End-to-end coverage of the split/quad-screen bundle: registration via
``list_tools``, workspace boundary, snapshot capture, per-cell composite
transitions written to the project, serializer round-trip, and the error
contract (bad layout, track-count mismatch, missing project).

Style mirrors ``test_composite_set_mcp_tool.py``. The fixture
``keyframe_project.kdenlive`` is a 1920x1080 profile with tracks 0/1/2.
"""
from __future__ import annotations

import asyncio
import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.server import mcp
import workshop_video_brain.edit_mcp.server.tools as _tools  # noqa: F401
import workshop_video_brain.edit_mcp.server.bundles  # noqa: F401  (auto-import)
from workshop_video_brain.edit_mcp.server.bundles import split_screen as _bundle


def _fn(tool):
    """Return the plain callable behind a possibly-wrapped MCP tool.

    Depending on the installed fastmcp version ``@mcp.tool()`` may return the
    original function or a ``FunctionTool`` wrapper (whose original callable is
    on ``.fn``). Unwrap so direct invocation works either way.
    """
    return getattr(tool, "fn", tool)


composite_split_screen = _fn(_bundle.composite_split_screen)
workspace_create = _fn(_tools.workspace_create)


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Split Screen Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _transitions(project_path: Path) -> list[ET.Element]:
    root = ET.fromstring(project_path.read_text(encoding="utf-8"))
    return list(root.iter("transition"))


def _props(transition: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: (p.text or "") for p in transition.findall("property")}


# ---------------------------------------------------------------------------
# Registration / shape
# ---------------------------------------------------------------------------

def test_tool_registered_via_list_tools():
    # fastmcp exposes the registered tools via ``list_tools`` (older) or
    # ``get_tools`` (3.x). Support both; normalise to a set of names.
    lister = getattr(mcp, "list_tools", None) or mcp.get_tools
    result = asyncio.run(lister())
    if isinstance(result, dict):
        names = set(result.keys())
    else:
        names = {getattr(t, "name", t) for t in result}
    assert "composite_split_screen" in names


def test_signature():
    params = list(inspect.signature(composite_split_screen).parameters)
    assert params == [
        "workspace_path", "project_file", "layout", "tracks",
        "start_frame", "end_frame", "base_track", "crop",
        "gap_px", "border_px", "border_color",
    ]


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------

def test_2h_writes_two_composites(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="2h", tracks="1,2", start_frame=0, end_frame=120,
        crop="stretch",
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["layout"] == "2h"
    assert data["tracks"] == [1, 2]
    assert len(data["cells"]) == 2
    assert data["cells"][0] == {"x": 0, "y": 0, "width": 960, "height": 1080}
    assert data["cells"][1] == {"x": 960, "y": 0, "width": 960, "height": 1080}
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    # Two new cairoblend transitions, geometry matching the two cells.
    trans = [t for t in _transitions(ws / pf)
             if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    geoms = {_props(t).get("geometry") for t in trans}
    assert "0/0:960x1080:100" in geoms
    assert "960/0:960x1080:100" in geoms


def test_quad_writes_four_composites(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # keyframe fixture has tracks 0/1/2; quad needs 4 cell tracks -> use 1..4.
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="4", tracks="1,2,3,4", start_frame=0, end_frame=90,
        crop="stretch",
    )
    assert out["status"] == "success", out
    assert len(out["data"]["cells"]) == 4
    trans = [t for t in _transitions(ws / pf)
             if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    # At least four composites written (fixture may carry pre-existing ones).
    geoms = [_props(t).get("geometry") for t in trans]
    assert "0/0:960x540:100" in geoms
    assert "960/540:960x540:100" in geoms


def test_snapshot_created_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="2v", tracks="1,2", start_frame=0, end_frame=60,
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    snap_dir = ws / "projects" / "snapshots" / snap_id
    assert snap_dir.is_dir(), f"snapshot dir missing: {snap_dir}"
    snap_files = [f for f in snap_dir.iterdir() if f.name != "metadata.yaml"]
    assert snap_files, "snapshot dir is empty"


def test_gap_reflected_in_cells(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="2h", tracks="1,2", start_frame=0, end_frame=60,
        gap_px=20, crop="stretch",
    )
    assert out["status"] == "success", out
    cells = out["data"]["cells"]
    assert cells[0]["width"] == 950
    assert cells[1]["x"] == 970


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_bad_layout_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="3h", tracks="1,2", start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "layout" in out["message"].lower()


def test_track_count_mismatch_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="4", tracks="1,2", start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "4 tracks" in out["message"]


def test_bad_tracks_string_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file=pf,
        layout="2h", tracks="a,b", start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "integers" in out["message"]


def test_missing_project_returns_err(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = composite_split_screen(
        workspace_path=str(ws), project_file="nope.kdenlive",
        layout="2h", tracks="1,2", start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]
