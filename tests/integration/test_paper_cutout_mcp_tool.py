"""Integration tests for the ``transition_paper_cutout`` MCP tool.

End-to-end coverage of the paper-cutout bundle: workspace boundary, single
snapshot capture, filter-stack insertion onto a clip, serializer round-trip,
and the error contract. Style mirrors ``test_composite_set_mcp_tool.py`` and
``test_masking_mcp_tools.py``.

The fixture ``keyframe_project.kdenlive`` exposes tracks 0/1/2; track 2 clip 0
is used (same as the masking integration tests).
"""
from __future__ import annotations

import inspect
import json
import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools


def _fn(name: str):
    """Return the raw callable for an MCP tool.

    Depending on the installed ``fastmcp`` version, ``@mcp.tool()`` either
    leaves the function in place or wraps it in a ``FunctionTool`` (which is
    not directly callable but exposes the original via ``.fn``). Unwrap so the
    tests call the tool the same way across versions.
    """
    obj = getattr(tools, name)
    return getattr(obj, "fn", obj)


transition_paper_cutout = _fn("transition_paper_cutout")
workspace_create = _fn("workspace_create")


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK = 2
CLIP = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Paper Cutout Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _effects(ws: Path, pf: str) -> list[dict]:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)
    return patcher.list_effects(project, (TRACK, CLIP))


def _services(effects: list[dict]) -> list[str]:
    return [e["mlt_service"] for e in effects]


# ---------------------------------------------------------------------------
# Registration / shape
# ---------------------------------------------------------------------------

def test_tool_importable():
    assert callable(transition_paper_cutout)


def test_tool_signature():
    sig = inspect.signature(transition_paper_cutout)
    params = sig.parameters
    expected = [
        "workspace_path", "project_file", "track", "clip",
        "points", "feather", "feather_passes", "alpha_operation",
        "edge_scale", "distort_amplitude", "distort_frequency",
        "drop_shadow", "shadow_offset", "shadow_blur", "shadow_color",
    ]
    assert list(params) == expected
    assert params["feather"].default == 2
    assert params["feather_passes"].default == 2
    assert params["drop_shadow"].default is True


# ---------------------------------------------------------------------------
# Success paths
# ---------------------------------------------------------------------------

def test_default_stack_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["filter_count"] == 2
    assert data["used_procedural_polygon"] is True
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    services = _services(_effects(ws, pf))
    assert services[-2:] == ["rotoscoping", "dropshadow"]


def test_full_stack_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        edge_scale=1.05, distort_amplitude=0.5, drop_shadow=True,
    )
    assert out["status"] == "success", out
    assert out["data"]["filter_count"] == 4

    services = _services(_effects(ws, pf))
    assert services[-4:] == [
        "affine", "rotoscoping", "frei0r.distort0r", "dropshadow",
    ]


def test_custom_points_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    pts = [[0.1, 0.1], [0.9, 0.1], [0.9, 0.9], [0.1, 0.9]]
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        points=json.dumps(pts),
    )
    assert out["status"] == "success", out
    assert out["data"]["used_procedural_polygon"] is False

    roto = next(e for e in _effects(ws, pf) if e["mlt_service"] == "rotoscoping")
    props = dict(roto["properties"])
    assert "0.9" in props["spline"]


def test_creates_snapshot_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    snap_dir = ws / "projects" / "snapshots" / snap_id
    assert snap_dir.is_dir(), f"snapshot dir missing: {snap_dir}"
    snap_files = [f for f in snap_dir.iterdir() if f.name != "metadata.yaml"]
    assert snap_files, "snapshot dir is empty"


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------

def test_missing_project_returns_err(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file="nope.kdenlive", track=TRACK, clip=CLIP,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_bad_points_json_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        points="{not json",
    )
    assert out["status"] == "error"
    assert "points" in out["message"].lower()


def test_too_few_points_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        points=json.dumps([[0.1, 0.1], [0.9, 0.9]]),
    )
    assert out["status"] == "error"
    assert "3" in out["message"]


def test_bad_alpha_operation_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        alpha_operation="bogus",
    )
    assert out["status"] == "error"


def test_bad_edge_scale_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_paper_cutout(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        edge_scale=-1.0,
    )
    assert out["status"] == "error"
    assert "scale" in out["message"].lower()
