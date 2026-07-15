"""Integration tests for the ``effect_pan_zoom`` bundle MCP tool.

Exercises bundle auto-registration, the profile-computed presets, explicit
rects, frame-bound clamping, snapshot capture, serializer round-trip (XML
written to disk), and the error contract. Style follows
``tests/integration/test_keyframe_mcp_tools.py`` and
``tests/integration/test_masked_wipes_mcp_tools.py``.

The tool takes an *absolute* ``project_file`` path (no ``workspace_path``);
snapshots are written under the nearest ancestor holding ``workspace.yaml``.
"""
from __future__ import annotations

import inspect
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server.bundles.pan_zoom import effect_pan_zoom
from workshop_video_brain.edit_mcp.server.tools import workspace_create
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

CLIP_TRACK = 2  # playlist2 holds the single clip in the fixture
CLIP_INDEX = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, Path]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Pan Zoom Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, dest


def _filters(project_path: Path) -> list[ET.Element]:
    root = ET.fromstring(project_path.read_text(encoding="utf-8"))
    return list(root.iter("filter"))


def _props(elem: ET.Element) -> dict[str, str]:
    return {p.attrib["name"]: (p.text or "") for p in elem.findall("property")}


# ---------------------------------------------------------------------------
# Registration / shape
# ---------------------------------------------------------------------------

def test_bundle_registers_effect_pan_zoom_via_list_tools():
    import asyncio

    import workshop_video_brain.server as server_mod
    import workshop_video_brain.edit_mcp.server  # noqa: F401 - ensure bundles imported

    tools = asyncio.run(server_mod.mcp.list_tools())
    names = {t.name for t in tools}
    assert "effect_pan_zoom" in names


def test_effect_pan_zoom_signature():
    params = list(inspect.signature(effect_pan_zoom).parameters)
    assert params == [
        "project_file", "track", "clip_index",
        "start_rect", "end_rect", "preset",
        "duration_frames", "easing", "hold_frames",
    ]


# ---------------------------------------------------------------------------
# Preset path
# ---------------------------------------------------------------------------

def test_preset_zoom_in_writes_keyframed_transform_filter(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="zoom_in",
    )
    assert out["status"] == "success", out
    data = out["data"]
    # fixture: 1920x1080, clip length 300 frames (out=299,in=0).
    assert data["start_rect"] == [0.0, 0.0, 1920.0, 1080.0]
    assert data["end_rect"] == [384.0, 216.0, 1152.0, 648.0]
    assert data["duration_frames"] == 300
    assert data["mlt_service"] == "affine"
    assert data["kdenlive_id"] == "transform"
    # affine reads transition.rect (a bare `rect` is a no-op on this MLT build).
    assert data["property"] == "transition.rect"
    assert "i=" in data["keyframes_written"]  # cubic_in_out operator

    # Effects are now nested inside the clip <entry> (the §1.1 placement fix),
    # so the association track=/clip_index= attributes are gone -- the filter's
    # position in the tree is what binds it to the clip.
    root = ET.fromstring(pf.read_text(encoding="utf-8"))
    nested_transforms = [
        f
        for e in root.iter("entry")
        for f in e.findall("filter")
        if _props(f).get("kdenlive_id") == "transform"
    ]
    # fixture already had one transform filter; the tool adds a second.
    assert len(nested_transforms) == 2
    new = nested_transforms[-1]
    # The tool now writes the render-correct `transition.rect` property.
    parsed = parse_keyframe_string("rect", _props(new)["transition.rect"], fps=30.0)
    assert [k.frame for k in parsed] == [0, 300]


def test_snapshot_created_before_write(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="pan_left_to_right",
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    assert isinstance(snap_id, str) and snap_id
    assert (ws / "projects" / "snapshots" / snap_id).exists()


def test_duration_frames_override(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="kenburns_tl_br", duration_frames=60,
    )
    assert out["status"] == "success", out
    assert out["data"]["duration_frames"] == 60
    parsed = parse_keyframe_string(
        "rect", out["data"]["keyframes_written"], fps=30.0,
    )
    assert [k.frame for k in parsed] == [0, 60]


def test_hold_frames_emits_lead_in(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="zoom_in", duration_frames=60, hold_frames=15,
    )
    assert out["status"] == "success", out
    parsed = parse_keyframe_string(
        "rect", out["data"]["keyframes_written"], fps=30.0,
    )
    assert [k.frame for k in parsed] == [0, 15, 75]


# ---------------------------------------------------------------------------
# Explicit rects + clamping
# ---------------------------------------------------------------------------

def test_explicit_rects_are_clamped_to_frame_bounds(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        start_rect=[-500, -500, 9000, 9000],  # oversized/negative
        end_rect=[1900, 1000, 400, 400],       # overhangs right/bottom edge
        duration_frames=48,
    )
    assert out["status"] == "success", out
    assert out["data"]["start_rect"] == [0.0, 0.0, 1920.0, 1080.0]
    # end clamped so x+w<=1920 and y+h<=1080.
    assert out["data"]["end_rect"] == [1520.0, 680.0, 400.0, 400.0]


def test_preset_with_end_rect_override(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="zoom_in", end_rect=[100, 100, 500, 300], duration_frames=48,
    )
    assert out["status"] == "success", out
    assert out["data"]["start_rect"] == [0.0, 0.0, 1920.0, 1080.0]  # from preset
    assert out["data"]["end_rect"] == [100.0, 100.0, 500.0, 300.0]  # override


# ---------------------------------------------------------------------------
# Error contract
# ---------------------------------------------------------------------------

def test_missing_project_file_errors():
    out = effect_pan_zoom(
        project_file="/nonexistent/project.kdenlive", track=0, clip_index=0,
        preset="zoom_in",
    )
    assert out["status"] == "error"
    assert "not found" in out["message"]


def test_no_preset_and_no_rects_errors(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
    )
    assert out["status"] == "error"
    assert "preset" in out["message"]


def test_unknown_preset_errors(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=CLIP_INDEX,
        preset="do_a_barrel_roll",
    )
    assert out["status"] == "error"
    assert "unknown preset" in out["message"]


def test_bad_clip_index_errors(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=CLIP_TRACK, clip_index=99, preset="zoom_in",
    )
    assert out["status"] == "error"
    assert "clip_index" in out["message"]


def test_bad_track_errors(tmp_path):
    _ws, pf = _make_ws(tmp_path)
    out = effect_pan_zoom(
        project_file=str(pf), track=99, clip_index=0, preset="zoom_in",
    )
    assert out["status"] == "error"
    assert "track" in out["message"]
