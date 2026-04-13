"""Integration tests for the ``composite_set`` MCP tool (Sub-Spec 2).

End-to-end coverage of the new blend-mode composite surface: workspace
boundary, snapshot capture, apply_composite routing, serializer round-trip,
and the error contract (unknown mode, bad tracks, bad frames).

The fixture ``keyframe_project.kdenlive`` exposes tracks 0/1/2 only -- per
Escalation Trigger 2 of the phase spec, we use smaller track indices that
exist in the fixture rather than ``track_b=4``.
"""
from __future__ import annotations

import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    composite_pip,
    composite_set,
    composite_wipe,
    workspace_create,
)
from workshop_video_brain.edit_mcp.pipelines.compositing import BLEND_MODES


FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK_A = 1
TRACK_B = 2


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Composite Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def _transitions(project_path: Path) -> list[ET.Element]:
    xml_text = project_path.read_text(encoding="utf-8")
    root = ET.fromstring(xml_text)
    return list(root.iter("transition"))


def _props(transition: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: (p.text or "") for p in transition.findall("property")}


# ---------------------------------------------------------------------------
# Tool registration / shape
# ---------------------------------------------------------------------------

def test_composite_set_importable():
    for name in ("composite_set", "composite_pip", "composite_wipe"):
        assert callable(getattr(tools, name)), f"{name} missing"


def test_composite_set_signature():
    sig = inspect.signature(composite_set)
    params = sig.parameters
    expected = [
        "workspace_path", "project_file",
        "track_a", "track_b", "start_frame", "end_frame",
        "blend_mode", "geometry",
    ]
    assert list(params) == expected
    assert params["blend_mode"].default == "cairoblend"
    assert params["geometry"].default == ""


# ---------------------------------------------------------------------------
# Behavioral: success paths
# ---------------------------------------------------------------------------

def test_composite_set_screen_writes_cairoblend_transition(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, end_frame=120,
        blend_mode="screen",
    )
    assert out["status"] == "success", out
    data = out["data"]
    assert data == {
        "composition_added": True,
        "blend_mode": "screen",
        "track_a": TRACK_A,
        "track_b": TRACK_B,
        "snapshot_id": data["snapshot_id"],
    }
    assert isinstance(data["snapshot_id"], str) and data["snapshot_id"]

    matches = [t for t in _transitions(ws / pf)
               if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    assert matches, "No frei0r.cairoblend transition written"
    props = _props(matches[-1])
    assert props["1"] == "screen"
    assert props["a_track"] == str(TRACK_A)
    assert props["b_track"] == str(TRACK_B)
    assert props["in"] == "0"
    assert props["out"] == "120"


def test_composite_set_destination_in_writes_qtblend(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=10, end_frame=90,
        blend_mode="destination_in",
    )
    assert out["status"] == "success", out

    matches = [t for t in _transitions(ws / pf)
               if t.attrib.get("mlt_service") == "qtblend"]
    assert matches, "No qtblend transition written"
    props = _props(matches[-1])
    assert props["compositing"] == "6"
    assert props["a_track"] == str(TRACK_A)
    assert props["b_track"] == str(TRACK_B)


def test_composite_set_custom_geometry(tmp_path):
    ws, pf = _make_ws(tmp_path)
    custom = "100/50:1920x1080:75"
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, end_frame=60,
        blend_mode="multiply", geometry=custom,
    )
    assert out["status"] == "success", out

    matches = [t for t in _transitions(ws / pf)
               if t.attrib.get("mlt_service") == "frei0r.cairoblend"]
    assert matches
    props = _props(matches[-1])
    assert props["geometry"] == custom
    assert props["1"] == "multiply"


def test_composite_set_creates_snapshot_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, end_frame=60,
        blend_mode="overlay",
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    snap_dir = ws / "projects" / "snapshots" / snap_id
    assert snap_dir.is_dir(), f"snapshot dir missing: {snap_dir}"
    # The snapshot directory should contain the pre-edit project copy.
    snap_files = [f for f in snap_dir.iterdir() if f.name != "metadata.yaml"]
    assert snap_files, "snapshot dir is empty"


# ---------------------------------------------------------------------------
# Behavioral: error paths
# ---------------------------------------------------------------------------

def test_composite_set_unknown_mode_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, end_frame=60,
        blend_mode="bogus",
    )
    assert out["status"] == "error"
    msg = out["message"]
    # Error message must list every valid blend mode.
    for mode in BLEND_MODES:
        assert mode in msg, f"mode {mode!r} missing from error message"


def test_composite_set_same_track_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_A,
        start_frame=0, end_frame=60,
        blend_mode="screen",
    )
    assert out["status"] == "error"
    assert "track" in out["message"].lower()


def test_composite_set_bad_frames_returns_err(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file=pf,
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=120, end_frame=120,
        blend_mode="screen",
    )
    assert out["status"] == "error"
    assert "frame" in out["message"].lower()


def test_composite_set_missing_project_returns_err(tmp_path):
    ws, _pf = _make_ws(tmp_path)
    out = composite_set(
        workspace_path=str(ws), project_file="nope.kdenlive",
        track_a=TRACK_A, track_b=TRACK_B,
        start_frame=0, end_frame=60,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]
