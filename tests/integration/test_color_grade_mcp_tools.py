"""Integration tests for the ``effect_color_grade`` bundle MCP tool.

Modeled on ``test_stack_ops_mcp_tools.py``. Exercises the one-call correction+
grade chain against a real fixture project through the MCP tool surface.
"""
from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools


def _fn(tool):
    """Resolve the underlying callable.

    Depending on the resolved fastmcp version, ``@mcp.tool()`` either returns the
    plain function (callable directly) or a ``FunctionTool`` wrapper exposing the
    original via ``.fn``.
    """
    return getattr(tool, "fn", tool)


effect_color_grade = _fn(tools.effect_color_grade)
workspace_create = _fn(tools.workspace_create)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

# (2, 0) is a real clip in the fixture (see test_stack_ops_mcp_tools.py).
TARGET = (2, 0)


def _make_ws(tmp_path: Path, project_name: str = "grade.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Color Grade Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _reparse(ws: Path, pf: str):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    return parse_project(ws / pf)


def _effect_services(project, clip_ref):
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    return [e["mlt_service"] for e in patcher.list_effects(project, clip_ref)]


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tool_importable_and_callable():
    assert callable(_fn(getattr(tools, "effect_color_grade", None)))


# ---------------------------------------------------------------------------
# Happy paths
# ---------------------------------------------------------------------------


def test_full_chain_inserts_all_stages(tmp_path):
    ws, pf = _make_ws(tmp_path)
    project = _reparse(ws, pf)
    before = len(_effect_services(project, TARGET))

    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        temperature=5000, exposure=0.3, contrast=1.1, saturation=1.2,
        lift=8, gamma=-4, gain=2, tint_amount=0.25,
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["filter_count"] == 5
    assert data["first_effect_index"] == before
    assert data["services"] == [
        "avfilter.colortemperature",
        "avfilter.exposure",
        "avfilter.eq",
        "lumaliftgaingamma",
        "frei0r.tint0r",
    ]
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    project2 = _reparse(ws, pf)
    services = _effect_services(project2, TARGET)
    assert services[before:] == data["services"]


def test_correction_only_subset(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        temperature=4200,
    )
    assert out["status"] == "success", out
    assert out["data"]["services"] == ["avfilter.colortemperature"]


def test_snapshot_dir_created(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        contrast=1.2,
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    assert (ws / "projects" / "snapshots" / snap_id).is_dir()


def test_grade_params_written_to_xml(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        lift=12, gamma=6, gain=-3,
    )
    assert out["status"] == "success", out
    text = (ws / pf).read_text()
    assert "lumaliftgaingamma" in text
    assert "12.0000" in text


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_all_neutral_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
    )
    assert out["status"] == "error"
    assert "no color grade parameters" in out["message"]


def test_missing_project(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=TARGET[0], clip=TARGET[1], contrast=1.2,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_bad_clip(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=99,
        contrast=1.2,
    )
    assert out["status"] == "error"


def test_out_of_range_param(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        temperature=50000,
    )
    assert out["status"] == "error"
    assert "temperature" in out["message"]


def test_missing_lut_path(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_color_grade(
        workspace_path=str(ws), project_file=pf, track=TARGET[0], clip=TARGET[1],
        lut_path="/does/not/exist.cube",
    )
    assert out["status"] == "error"
    assert "lut_path" in out["message"]
