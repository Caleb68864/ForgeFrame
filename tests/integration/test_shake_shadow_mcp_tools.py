"""Integration tests for the camera-shake / drop-shadow bundle MCP tools.

Exercises ``effect_camera_shake`` and ``effect_drop_shadow`` end-to-end:
bundle auto-registration, workspace boundary, snapshot capture, serializer
round-trip (XML written to disk), keyframe determinism, and the error contract.

Style follows ``tests/integration/test_masked_wipes_mcp_tools.py``. The fixture
``keyframe_project.kdenlive`` is 1920x1080 @ 30fps with a clip on track 2
(clip 0).
"""
from __future__ import annotations

import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.bundles import shake_shadow as _bundle
from workshop_video_brain.edit_mcp.server import tools as _tools


def _fn(tool):
    """Unwrap a FastMCP FunctionTool (3.x) to its plain callable; pass through
    a bare function (2.x)."""
    return getattr(tool, "fn", tool)


effect_camera_shake = _fn(_bundle.effect_camera_shake)
effect_drop_shadow = _fn(_bundle.effect_drop_shadow)
workspace_create = _fn(_tools.workspace_create)


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

CLIP_TRACK = 2
CLIP_INDEX = 0


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Shake Shadow Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _filters(project_path: Path) -> list[ET.Element]:
    root = ET.fromstring(project_path.read_text(encoding="utf-8"))
    return list(root.iter("filter"))


def _props(elem: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: (p.text or "") for p in elem.findall("property")}


def _filter_by_service(project_path: Path, service: str) -> ET.Element:
    matches = [f for f in _filters(project_path)
               if f.attrib.get("mlt_service") == service]
    assert matches, f"No {service} filter written"
    return matches[-1]


# ---------------------------------------------------------------------------
# Registration / signatures
# ---------------------------------------------------------------------------

def test_bundle_module_registers_tools():
    import asyncio

    import workshop_video_brain.server as server_mod
    import workshop_video_brain.edit_mcp.server  # noqa: F401

    mcp = server_mod.mcp
    if hasattr(mcp, "get_tools"):  # fastmcp 3.x
        tools = asyncio.run(mcp.get_tools())
        names = set(tools) if isinstance(tools, dict) else {t.name for t in tools}
    else:  # fastmcp 2.x
        tools = asyncio.run(mcp.list_tools())
        names = {t.name for t in tools}
    assert "effect_camera_shake" in names
    assert "effect_drop_shadow" in names


def test_camera_shake_signature():
    params = list(inspect.signature(effect_camera_shake).parameters)
    assert params == [
        "workspace_path", "project_file", "track", "clip_index",
        "start_frame", "end_frame", "intensity", "frequency_hz",
        "seed", "rotation",
    ]
    sig = inspect.signature(effect_camera_shake)
    assert sig.parameters["intensity"].default == 0.5
    assert sig.parameters["frequency_hz"].default == 8.0
    assert sig.parameters["seed"].default is None
    assert sig.parameters["rotation"].default is False


def test_drop_shadow_signature():
    params = list(inspect.signature(effect_drop_shadow).parameters)
    assert params == [
        "workspace_path", "project_file", "track", "clip_index",
        "blur_radius", "offset_x", "offset_y", "color",
    ]


# ---------------------------------------------------------------------------
# effect_camera_shake -- success
# ---------------------------------------------------------------------------

def test_camera_shake_writes_qtblend_with_rect_keyframes(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=60, intensity=0.5, frequency_hz=8.0, seed=7,
    )
    assert out["status"] == "success", out
    assert out["data"]["service"] == "qtblend"
    assert out["data"]["keyframe_count"] > 1
    assert isinstance(out["data"]["snapshot_id"], str) and out["data"]["snapshot_id"]

    filt = _filter_by_service(ws / pf, "qtblend")
    props = _props(filt)
    assert ";" in props["rect"]  # animated keyframe string
    assert "rotation" not in props  # rotation disabled by default


def test_camera_shake_end_frame_sentinel(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=-1, seed=1,
    )
    assert out["status"] == "success", out
    # -1 resolves to a real (positive) end frame within the clip.
    assert out["data"]["end_frame"] > 0


def test_camera_shake_rotation_adds_rotation_property(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=60, rotation=True, seed=7,
    )
    assert out["status"] == "success", out
    assert out["data"]["rotation"] is True
    props = _props(_filter_by_service(ws / pf, "qtblend"))
    assert "rotation" in props
    assert "=" in props["rotation"]


def test_camera_shake_deterministic_across_runs(tmp_path):
    ws1, pf1 = _make_ws(tmp_path / "a")
    ws2, pf2 = _make_ws(tmp_path / "b")
    common = dict(
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=60, intensity=0.7, frequency_hz=10.0, seed=99,
    )
    o1 = effect_camera_shake(workspace_path=str(ws1), project_file=pf1, **common)
    o2 = effect_camera_shake(workspace_path=str(ws2), project_file=pf2, **common)
    assert o1["status"] == "success" and o2["status"] == "success"
    rect1 = _props(_filter_by_service(ws1 / pf1, "qtblend"))["rect"]
    rect2 = _props(_filter_by_service(ws2 / pf2, "qtblend"))["rect"]
    assert rect1 == rect2


def test_camera_shake_snapshot_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=30,
    )
    assert out["status"] == "success", out
    snap_dir = ws / "projects" / "snapshots" / out["data"]["snapshot_id"]
    assert snap_dir.is_dir()


# ---------------------------------------------------------------------------
# effect_camera_shake -- errors
# ---------------------------------------------------------------------------

def test_camera_shake_intensity_out_of_range(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=60, intensity=5.0,
    )
    assert out["status"] == "error"
    assert "intensity" in out["message"].lower()


def test_camera_shake_bad_window(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=60, end_frame=30,
    )
    assert out["status"] == "error"
    assert "end_frame" in out["message"].lower()


def test_camera_shake_missing_project(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = effect_camera_shake(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_camera_shake_bad_workspace(tmp_path):
    out = effect_camera_shake(
        workspace_path=str(tmp_path / "does-not-exist"),
        project_file="test.kdenlive",
        track=CLIP_TRACK, clip_index=CLIP_INDEX, start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# effect_drop_shadow
# ---------------------------------------------------------------------------

def test_drop_shadow_writes_dropshadow_filter(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_drop_shadow(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
        blur_radius=12, offset_x=10, offset_y=6, color="#b4000000",
    )
    assert out["status"] == "success", out
    assert out["data"]["service"] == "dropshadow"
    assert isinstance(out["data"]["snapshot_id"], str) and out["data"]["snapshot_id"]

    props = _props(_filter_by_service(ws / pf, "dropshadow"))
    assert props["radius"] == "12"
    assert props["x"] == "10"
    assert props["y"] == "6"
    assert props["color"] == "#b4000000"


def test_drop_shadow_negative_radius_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_drop_shadow(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip_index=CLIP_INDEX, blur_radius=-3,
    )
    assert out["status"] == "error"
    assert "blur_radius" in out["message"].lower()


def test_drop_shadow_missing_project(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = effect_drop_shadow(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=CLIP_TRACK, clip_index=CLIP_INDEX,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]
