"""Integration tests for keyframe MCP tools.

Exercises the four new MCP tools (effect_find, effect_keyframe_set_scalar,
effect_keyframe_set_rect, effect_keyframe_set_color) against a minimal
Kdenlive fixture.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_find,
    effect_keyframe_set_scalar,
    effect_keyframe_set_rect,
    effect_keyframe_set_color,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    """Create a workspace and copy the fixture into it. Returns (ws_root, project_file)."""
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Keyframe Test", media_root=str(media_root))
    assert result["status"] == "success", result
    ws_root = Path(result["data"]["workspace_root"])
    dest = ws_root / project_name
    shutil.copy(FIXTURE, dest)
    return ws_root, project_name


def test_four_tools_are_registered_on_mcp():
    for name in (
        "effect_keyframe_set_scalar",
        "effect_keyframe_set_rect",
        "effect_keyframe_set_color",
        "effect_find",
    ):
        assert callable(getattr(tools, name)), f"{name} missing from tools module"


def test_effect_find_returns_index_for_transform(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_find(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, name="transform",
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index"] == 0


def test_effect_keyframe_set_rect_writes_animation_string_and_roundtrips(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([
        {"frame": 0, "value": [0, 0, 1920, 1080, 1], "easing": "linear"},
        {"frame": 30, "value": [100, 100, 1000, 800, 1], "easing": "linear"},
    ])
    out = effect_keyframe_set_rect(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="rect",
        keyframes=kfs, mode="replace",
    )
    assert out["status"] == "success", out
    written = out["data"]["keyframes_written"]
    assert "00:00:00.000" in written
    assert "00:00:01.000" in written  # 30 frames at 30fps

    # Roundtrip: read back via parser and assert content
    from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    project = parse_project(ws / pf)
    val = patcher.get_effect_property(project, (2, 0), 0, "rect")
    assert val == written

    from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string
    parsed = parse_keyframe_string("rect", written, fps=30.0)
    assert len(parsed) == 2
    assert parsed[0].frame == 0
    assert parsed[1].frame == 30


def test_effect_keyframe_set_scalar_basic(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([
        {"frame": 0, "value": 0.0, "easing": "linear"},
        {"frame": 60, "value": 1.0, "easing": "linear"},
    ])
    out = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=kfs,
    )
    assert out["status"] == "success", out
    assert "=" in out["data"]["keyframes_written"]


def test_effect_keyframe_set_color_basic(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([
        {"frame": 0, "value": "#ff0000", "easing": "linear"},
    ])
    out = effect_keyframe_set_color(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="color",
        keyframes=kfs,
    )
    assert out["status"] == "success", out


def test_mode_merge_preserves_non_overlapping_frames(tmp_path):
    ws, pf = _make_ws(tmp_path)
    first = json.dumps([
        {"frame": 0, "value": 0.0, "easing": "linear"},
        {"frame": 30, "value": 1.0, "easing": "linear"},
    ])
    r1 = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=first, mode="replace",
    )
    assert r1["status"] == "success"

    second = json.dumps([
        {"frame": 60, "value": 0.5, "easing": "linear"},
    ])
    r2 = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=second, mode="merge",
    )
    assert r2["status"] == "success", r2
    from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string
    parsed = parse_keyframe_string("scalar", r2["data"]["keyframes_written"], fps=30.0)
    frames = sorted(k.frame for k in parsed)
    assert frames == [0, 30, 60]


def test_mode_merge_overwrites_same_frame(tmp_path):
    ws, pf = _make_ws(tmp_path)
    first = json.dumps([
        {"frame": 0, "value": 0.0, "easing": "linear"},
        {"frame": 30, "value": 1.0, "easing": "linear"},
    ])
    effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=first, mode="replace",
    )
    second = json.dumps([
        {"frame": 30, "value": 0.25, "easing": "linear"},
    ])
    r2 = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=second, mode="merge",
    )
    assert r2["status"] == "success"
    from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string
    parsed = parse_keyframe_string("scalar", r2["data"]["keyframes_written"], fps=30.0)
    by_frame = {k.frame: k.value for k in parsed}
    assert by_frame[30] == 0.25
    assert by_frame[0] == 0.0


def test_invalid_effect_index_error_lists_available_effects(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([{"frame": 0, "value": 0.0, "easing": "linear"}])
    out = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=99, property="opacity",
        keyframes=kfs,
    )
    assert out["status"] == "error"
    msg = out["message"]
    # Error message must include available effects (the transform/affine filter)
    assert "transform" in msg or "affine" in msg


def test_each_call_produces_snapshot_id_in_response(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([{"frame": 0, "value": 0.0}])
    out = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=kfs,
    )
    assert out["status"] == "success"
    snap_id = out["data"]["snapshot_id"]
    assert isinstance(snap_id, str) and snap_id
    # Snapshot directory must exist
    assert (ws / "projects" / "snapshots" / snap_id).exists()


def test_fps_read_per_call_not_cached(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([{"frame": 30, "value": 1.0}])
    r1 = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=kfs,
    )
    assert r1["status"] == "success"
    # frame=30 at 30fps == 1.000s
    assert "00:00:01.000" in r1["data"]["keyframes_written"]

    # Mutate project file fps to 60fps
    text = (ws / pf).read_text(encoding="utf-8")
    text = text.replace('frame_rate_num="30"', 'frame_rate_num="60"')
    (ws / pf).write_text(text, encoding="utf-8")

    r2 = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=kfs, mode="replace",
    )
    assert r2["status"] == "success"
    # frame=30 at 60fps == 0.500s
    assert "00:00:00.500" in r2["data"]["keyframes_written"]


def test_ease_family_workspace_config_flows_through(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Update manifest to set ease_family="expo"
    from workshop_video_brain.workspace.manifest import read_manifest, write_manifest
    from workshop_video_brain.core.models.workspace import KeyframeDefaults
    manifest = read_manifest(ws)
    manifest.keyframe_defaults = KeyframeDefaults(ease_family="expo")
    write_manifest(ws, manifest)

    kfs = json.dumps([
        {"frame": 0, "value": 0.0, "easing": "ease_in"},
        {"frame": 30, "value": 1.0, "easing": "linear"},
    ])
    out = effect_keyframe_set_scalar(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="opacity",
        keyframes=kfs,
    )
    assert out["status"] == "success", out
    written = out["data"]["keyframes_written"]
    # ease_in composed with expo family -> operator 'p'
    # expo_in operator is 'p'; cubic_in is 'g'.
    assert "p=" in written, f"expected expo_in operator 'p' in {written!r}"
    assert "g=" not in written, f"cubic_in operator 'g' leaked in {written!r}"


def test_color_keyframe_emits_mlt_hex_format(tmp_path):
    ws, pf = _make_ws(tmp_path)
    kfs = json.dumps([{"frame": 0, "value": "#ff0000", "easing": "linear"}])
    out = effect_keyframe_set_color(
        workspace_path=str(ws), project_file=pf,
        track=2, clip=0, effect_index=0, property="color",
        keyframes=kfs,
    )
    assert out["status"] == "success", out
    assert "0xff0000ff" in out["data"]["keyframes_written"]
