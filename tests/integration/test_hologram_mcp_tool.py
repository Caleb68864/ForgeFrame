"""Integration tests for the ``effect_hologram`` MCP bundle tool.

Exercises ``effect_hologram`` against the shared keyframe fixture project,
mirroring the style of ``test_effect_presets.py`` / ``test_stack_ops_mcp_tools.py``.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server import tools as _tools_mod

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"
TRACK = 2
CLIP = 0


def _callable(name: str):
    """Return the underlying function for an MCP tool.

    Depending on the installed fastmcp version, ``@mcp.tool()`` may return the
    original function or wrap it in a ``FunctionTool`` (which exposes the
    callable via ``.fn``). Unwrap so the test drives the real implementation.
    """
    obj = getattr(_tools_mod, name)
    return getattr(obj, "fn", obj)


effect_hologram = _callable("effect_hologram")
workspace_create = _callable("workspace_create")


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    res = workspace_create(title="Hologram Test", media_root=str(media_root))
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


def _count_snapshots(ws: Path) -> int:
    d = ws / "projects" / "snapshots"
    if not d.exists():
        return 0
    return sum(1 for p in d.iterdir() if p.is_dir())


@pytest.fixture(autouse=True)
def _isolate_vault(monkeypatch):
    monkeypatch.setattr(tools, "_resolve_vault_root_for_tools", lambda: None)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_tool_importable_and_callable():
    assert hasattr(tools, "effect_hologram")
    assert callable(effect_hologram)


# ---------------------------------------------------------------------------
# Happy path: full stack appended in canonical order
# ---------------------------------------------------------------------------


def test_default_appends_full_hologram_stack(tmp_path):
    ws, pf = _make_ws(tmp_path)
    before = _count_snapshots(ws)

    out = effect_hologram(workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP)
    assert out["status"] == "success", out
    assert out["data"]["filter_count"] == 6
    assert out["data"]["first_effect_index"] >= 0
    assert out["data"]["tint_color"] == "#33ccff"
    assert isinstance(out["data"]["snapshot_id"], str) and out["data"]["snapshot_id"]

    filters = _list_filters(ws, pf, TRACK, CLIP)
    services = [f["mlt_service"] for f in filters]
    # Fixture ships with an existing affine filter; hologram stack appended.
    assert services[-6:] == [
        "frei0r.colorize",
        "frei0r.scanline0r",
        "boxblur",
        "frei0r.glow",
        "frei0r.glitch0r",
        "frei0r.transparency",
    ], services

    # One explicit snapshot + one serialize pre-write snapshot = delta 2.
    assert _count_snapshots(ws) - before == 2
    assert (ws / "projects" / "snapshots" / out["data"]["snapshot_id"]).is_dir()


def test_colorize_hue_reflects_tint(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        tint_color="#ff0000",
    )
    assert out["status"] == "success", out
    filters = _list_filters(ws, pf, TRACK, CLIP)
    colorize = next(f for f in filters if f["mlt_service"] == "frei0r.colorize")
    assert abs(float(colorize["properties"]["hue"])) < 1.0


def test_flicker_window_writes_animated_keyframes(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        flicker=0.6, start_frame=0, end_frame=120,
    )
    assert out["status"] == "success", out
    assert out["data"]["end_frame"] == 120
    filters = _list_filters(ws, pf, TRACK, CLIP)
    glitch = next(f for f in filters if f["mlt_service"] == "frei0r.glitch0r")
    freq = glitch["properties"]["0"]
    assert ";" in freq and "=" in freq, freq


def test_end_frame_defaults_to_clip_length(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
    )
    assert out["status"] == "success", out
    # -1 sentinel resolves to a real end frame (clip duration - 1).
    assert out["data"]["end_frame"] >= 0


def test_disabling_layers_shrinks_stack(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        scanline_intensity=0.0, glow=0.0, flicker=0.0,
    )
    assert out["status"] == "success", out
    assert out["data"]["filter_count"] == 2
    assert out["data"]["services"] == ["frei0r.colorize", "frei0r.transparency"]


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_missing_project_errors(tmp_path):
    ws, _ = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file="nope.kdenlive", track=TRACK, clip=CLIP,
    )
    assert out["status"] == "error"
    assert "nope.kdenlive" in out["message"]


def test_bad_clip_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=99,
    )
    assert out["status"] == "error"


def test_out_of_range_intensity_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_hologram(
        workspace_path=str(ws), project_file=pf, track=TRACK, clip=CLIP,
        glow=5.0,
    )
    assert out["status"] == "error"
    assert "glow" in out["message"]
