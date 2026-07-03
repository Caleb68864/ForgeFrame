"""Integration tests for the masked-wipe bundle MCP tools.

Exercises ``transition_masked_wipe`` and ``effect_luma_key`` end-to-end:
bundle auto-registration, workspace boundary, snapshot capture,
serializer round-trip (XML written to disk), and the error contract.

Style follows ``tests/integration/test_composite_set_mcp_tool.py``. The
fixture ``keyframe_project.kdenlive`` exposes tracks 0/1/2, with a clip on
track 2 (clip 0) -- used for the luma-key filter target.
"""
from __future__ import annotations

import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.bundles import masked_wipes as _bundle
from workshop_video_brain.edit_mcp.server import tools as _tools
from workshop_video_brain.edit_mcp.pipelines.masked_wipes import LUMA_DIR


def _unwrap(tool):
    """Return the raw callable for a tool.

    Under the project's pytest config, fastmcp's ``@mcp.tool()`` returns a
    ``FunctionTool`` wrapper (underlying function on ``.fn``); standalone it
    returns the plain function. This normalises both so the tool body can be
    called and introspected directly.
    """
    return getattr(tool, "fn", tool)


transition_masked_wipe = _unwrap(_bundle.transition_masked_wipe)
effect_luma_key = _unwrap(_bundle.effect_luma_key)
workspace_create = _unwrap(_tools.workspace_create)


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK_A = 1
TRACK_B = 2
CLIP_TRACK = 2  # playlist2 holds the single clip in the fixture
CLIP_INDEX = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Masked Wipe Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _transitions(project_path: Path) -> list[ET.Element]:
    root = ET.fromstring(project_path.read_text(encoding="utf-8"))
    return list(root.iter("transition"))


def _filters(project_path: Path) -> list[ET.Element]:
    root = ET.fromstring(project_path.read_text(encoding="utf-8"))
    return list(root.iter("filter"))


def _props(elem: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: (p.text or "") for p in elem.findall("property")}


# ---------------------------------------------------------------------------
# Registration / shape
# ---------------------------------------------------------------------------

def test_bundle_module_registers_tools():
    """Importing the server must expose both bundle tools via list_tools."""
    import asyncio

    import workshop_video_brain.server as server_mod

    mcp = server_mod.mcp
    # fastmcp exposes the registry as either ``get_tools`` (dict) or
    # ``list_tools`` (list) depending on the active compatibility mode.
    getter = getattr(mcp, "get_tools", None) or getattr(mcp, "list_tools")
    result = asyncio.run(getter())
    if isinstance(result, dict):
        names = set(result)
    else:
        names = {t.name for t in result}
    assert "transition_masked_wipe" in names
    assert "effect_luma_key" in names


def test_transition_masked_wipe_signature():
    params = list(inspect.signature(transition_masked_wipe).parameters)
    assert params == [
        "workspace_path", "project_file",
        "track_a", "track_b", "start_frame", "duration_frames",
        "luma_file", "invert", "softness",
    ]
    sig = inspect.signature(transition_masked_wipe)
    assert sig.parameters["invert"].default is False
    assert sig.parameters["softness"].default == 0.0


def test_effect_luma_key_signature():
    params = list(inspect.signature(effect_luma_key).parameters)
    assert params == [
        "workspace_path", "project_file",
        "track", "clip", "threshold", "tolerance", "softness",
    ]


# ---------------------------------------------------------------------------
# transition_masked_wipe -- success paths
# ---------------------------------------------------------------------------

def test_masked_wipe_builtin_name_writes_luma_transition(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=100, duration_frames=30,
        luma_file="luma05",
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data["composition_added"] is True
    assert data["frames"] == [100, 130]
    assert data["resource"].endswith("luma05.pgm")
    assert data["resource"].startswith(LUMA_DIR)
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    luma = [t for t in _transitions(ws / pf)
            if t.attrib.get("mlt_service") == "luma"]
    assert luma, "No luma transition written"
    props = _props(luma[-1])
    assert props["resource"].endswith("luma05.pgm")
    assert props["invert"] == "0"
    assert props["softness"] == "0.0"
    assert props["a_track"] == str(TRACK_A)
    assert props["b_track"] == str(TRACK_B)
    assert props["in"] == "100"
    assert props["out"] == "130"


def test_masked_wipe_custom_matte_invert_softness(tmp_path):
    ws, pf = _make_ws(tmp_path)
    matte = tmp_path / "heart.png"
    matte.write_text("fake")
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=48,
        luma_file=str(matte), invert=True, softness=0.4,
    )
    assert out["status"] == "success", out

    props = _props([t for t in _transitions(ws / pf)
                    if t.attrib.get("mlt_service") == "luma"][-1])
    assert props["resource"] == str(matte)
    assert props["invert"] == "1"
    assert props["softness"] == "0.4"


def test_masked_wipe_creates_snapshot_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=30, luma_file="luma01",
    )
    assert out["status"] == "success", out
    snap_dir = ws / "projects" / "snapshots" / out["data"]["snapshot_id"]
    assert snap_dir.is_dir(), f"snapshot dir missing: {snap_dir}"


# ---------------------------------------------------------------------------
# transition_masked_wipe -- error paths
# ---------------------------------------------------------------------------

def test_masked_wipe_missing_project(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=30, luma_file="luma01",
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_masked_wipe_bad_duration(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=0, luma_file="luma01",
    )
    assert out["status"] == "error"
    assert "duration" in out["message"].lower()


def test_masked_wipe_same_track(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_A,
        start_frame=0, duration_frames=30, luma_file="luma01",
    )
    assert out["status"] == "error"
    assert "track" in out["message"].lower()


def test_masked_wipe_softness_out_of_range(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=30, luma_file="luma01", softness=2.0,
    )
    assert out["status"] == "error"
    assert "softness" in out["message"].lower()


def test_masked_wipe_empty_luma(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = transition_masked_wipe(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=30, luma_file="",
    )
    assert out["status"] == "error"
    assert "luma_file" in out["message"]


def test_masked_wipe_bad_workspace(tmp_path):
    out = transition_masked_wipe(
        workspace_path=str(tmp_path / "does-not-exist"),
        project_file="test.kdenlive",
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, duration_frames=30, luma_file="luma01",
    )
    assert out["status"] == "error"


# ---------------------------------------------------------------------------
# effect_luma_key
# ---------------------------------------------------------------------------

def test_luma_key_writes_lumakey_filter(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_luma_key(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip=CLIP_INDEX,
        threshold=0.2, tolerance=0.1, softness=0.05,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_name"] == "avfilter.lumakey"
    assert isinstance(out["data"]["snapshot_id"], str) and out["data"]["snapshot_id"]

    lumakey = [f for f in _filters(ws / pf)
               if f.attrib.get("mlt_service") == "avfilter.lumakey"]
    assert lumakey, "No avfilter.lumakey filter written"
    props = _props(lumakey[-1])
    assert props["av.threshold"] == "0.2"
    assert props["av.tolerance"] == "0.1"
    assert props["av.softness"] == "0.05"


def test_luma_key_out_of_range_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_luma_key(
        workspace_path=str(ws), project_file=pf,
        track=CLIP_TRACK, clip=CLIP_INDEX, threshold=2.0,
    )
    assert out["status"] == "error"
    assert "threshold" in out["message"].lower()


def test_luma_key_missing_project(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = effect_luma_key(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track=CLIP_TRACK, clip=CLIP_INDEX,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]
