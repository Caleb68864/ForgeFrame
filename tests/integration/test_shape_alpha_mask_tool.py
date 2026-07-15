"""Integration test for the ``mask_set_from_file`` bundle tool.

Exercises the file-based Shape Alpha mask (SAM2-export consumer) through the
real workspace + snapshot + parse/serialize pipeline.

Depending on the resolved FastMCP version, ``@mcp.tool()`` may return either
the plain function or a wrapping ``FunctionTool`` object. ``_callable``
normalizes both so the test drives the real implementation either way.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.bundles import shape_alpha_mask
from workshop_video_brain.edit_mcp.server import tools as _tools

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK = 2
CLIP = 0


def _callable(obj):
    """Return the underlying function whether ``obj`` is a plain function or a
    FastMCP ``FunctionTool`` wrapper."""
    if callable(obj) and not obj.__class__.__name__.endswith("Tool"):
        return obj
    for attr in ("fn", "func", "__wrapped__", "callable", "handler"):
        candidate = getattr(obj, attr, None)
        if callable(candidate):
            return candidate
    if callable(obj):
        return obj
    raise TypeError(f"cannot resolve callable from {obj!r}")


mask_set_from_file = _callable(shape_alpha_mask.mask_set_from_file)
workspace_create = _callable(_tools.workspace_create)


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Shape Alpha Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    shutil.copy(FIXTURE, ws_root / project_name)
    return ws_root, project_name


def _effects(ws: Path, pf: str) -> list[dict]:
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)
    return patcher.list_effects(project, (TRACK, CLIP))


def test_mask_set_from_file_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_from_file(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        mask_file="/masks/sam2_subject.mov",
        use_luminance=True,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index"] == 0
    assert out["data"]["type"] == "image_alpha"
    assert out["data"]["mlt_service"] == "shape"
    assert "snapshot_id" in out["data"]

    stack = _effects(ws, pf)
    assert stack[0]["mlt_service"] == "shape"
    props = stack[0]["properties"]
    assert props["resource"] == "/masks/sam2_subject.mov"
    assert props["use_luminance"] == "1"


def test_missing_project_errors(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = mask_set_from_file(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=TRACK, clip=CLIP, mask_file="/m.mov",
    )
    assert out["status"] == "error"


def test_empty_mask_file_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_from_file(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, mask_file="   ",
    )
    assert out["status"] == "error"


def test_tool_symbol_registered():
    """The bundle module exposes the tool symbol (auto-discovered on import)."""
    assert hasattr(shape_alpha_mask, "mask_set_from_file")
