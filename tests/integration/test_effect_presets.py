"""Integration tests for effect preset MCP tools (Sub-Spec 2).

Covers SR-13..SR-23 of the Effect Wrappers test plan.
"""
from __future__ import annotations

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_fade,
    effect_glitch_stack,
    flash_cut_montage,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"
TRACK = 2
CLIP = 0


def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    res = workspace_create(title="Presets Test", media_root=str(media_root))
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
# SR-13: effect_glitch_stack inserts 5 filters in order
# ---------------------------------------------------------------------------

def test_sr13_glitch_stack_inserts_five_filters_in_order(tmp_path):
    ws, pf = _make_ws(tmp_path)
    before = _count_snapshots(ws)
    out = effect_glitch_stack(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, intensity=0.5,
    )
    assert out["status"] == "success", out
    assert out["data"]["filter_count"] == 5
    assert out["data"]["first_effect_index"] >= 0
    assert "snapshot_id" in out["data"]

    filters = _list_filters(ws, pf, TRACK, CLIP)
    services = [f["mlt_service"] for f in filters]
    # Fixture ships with an existing affine filter; the 5 glitch filters are
    # appended at the end of the stack in canonical order.
    assert services[-5:] == [
        "frei0r.pixeliz0r",
        "frei0r.glitch0r",
        "frei0r.rgbsplit0r",
        "frei0r.scanline0r",
        "avfilter.exposure",
    ], services

    # The preset takes one explicit snapshot; `serialize_project` takes
    # one additional pre-write snapshot. The critical invariant is that the
    # preset itself only calls `create_snapshot` once (not 5 times, once per
    # filter), so the delta is exactly 2.
    assert _count_snapshots(ws) - before == 2
    snap_dir = ws / "projects" / "snapshots" / out["data"]["snapshot_id"]
    assert snap_dir.is_dir()


# ---------------------------------------------------------------------------
# SR-14: intensity scales per-filter params
# ---------------------------------------------------------------------------

def test_sr14_glitch_stack_intensity_scales_params(tmp_path):
    ws_low, pf_low = _make_ws(tmp_path / "low")
    ws_high, pf_high = _make_ws(tmp_path / "high")

    out_low = effect_glitch_stack(
        workspace_path=str(ws_low), project_file=pf_low,
        track=TRACK, clip=CLIP, intensity=0.0,
    )
    out_high = effect_glitch_stack(
        workspace_path=str(ws_high), project_file=pf_high,
        track=TRACK, clip=CLIP, intensity=1.0,
    )
    assert out_low["status"] == "success"
    assert out_high["status"] == "success"

    low_filters = _list_filters(ws_low, pf_low, TRACK, CLIP)
    high_filters = _list_filters(ws_high, pf_high, TRACK, CLIP)

    # pixeliz0r block width (property "0") must differ
    low_block = next(
        f["properties"]["0"] for f in low_filters
        if f["mlt_service"] == "frei0r.pixeliz0r"
    )
    high_block = next(
        f["properties"]["0"] for f in high_filters
        if f["mlt_service"] == "frei0r.pixeliz0r"
    )
    assert low_block != high_block


# ---------------------------------------------------------------------------
# SR-15: missing catalog service returns _err
# ---------------------------------------------------------------------------

def test_sr15_glitch_stack_reports_missing_service(tmp_path, monkeypatch):
    ws, pf = _make_ws(tmp_path)
    # Remove `avfilter.exposure` from the catalog clone.
    from workshop_video_brain.edit_mcp.pipelines import effect_catalog
    patched = {
        k: v for k, v in effect_catalog.CATALOG.items()
        if v.mlt_service != "avfilter.exposure"
    }
    monkeypatch.setattr(effect_catalog, "CATALOG", patched)

    out = effect_glitch_stack(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
    )
    assert out["status"] == "error", out
    assert "avfilter.exposure" in out["message"]


# ---------------------------------------------------------------------------
# SR-16: effect_glitch_stack intensity out of range
# ---------------------------------------------------------------------------

def test_sr16_glitch_stack_intensity_out_of_range(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_glitch_stack(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, intensity=1.5,
    )
    assert out["status"] == "error"
    assert "intensity" in out["message"]


# ---------------------------------------------------------------------------
# SR-17: effect_fade inserts transform with keyframed rect
# ---------------------------------------------------------------------------

def test_sr17_fade_writes_opacity_keyframes_on_transform(tmp_path):
    ws, pf = _make_ws(tmp_path)
    before = _count_snapshots(ws)

    out = effect_fade(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        fade_in_frames=30, fade_out_frames=30,
        easing="ease_in_out",
    )
    assert out["status"] == "success", out
    assert 2 <= out["data"]["keyframe_count"] <= 4

    filters = _list_filters(ws, pf, TRACK, CLIP)
    # Find the newly-added affine+transform filter at end of stack.
    last = filters[-1]
    assert last["mlt_service"] == "affine"
    assert last["kdenlive_id"] == "transform"
    rect = last["properties"].get("rect", "")
    # Should contain keyframe separators (';') with operator-encoded opacity.
    assert ";" in rect, rect
    # Contains an opacity term '0' and '1'.
    assert " 0" in rect or "=0" in rect
    assert " 1" in rect or "=1" in rect

    # One explicit + one serializer-level pre-write snapshot.
    assert _count_snapshots(ws) - before == 2


# ---------------------------------------------------------------------------
# SR-18: fade zero/zero errors
# ---------------------------------------------------------------------------

def test_sr18_fade_zero_zero_errors(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_fade(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        fade_in_frames=0, fade_out_frames=0,
    )
    assert out["status"] == "error"
    assert "non-zero" in out["message"] or "at least one" in out["message"]


# ---------------------------------------------------------------------------
# SR-19: fade honors easing -- MLT operator char in keyframe string
# ---------------------------------------------------------------------------

def test_sr19_fade_easing_mlt_operator_matches(tmp_path):
    from workshop_video_brain.edit_mcp.pipelines.keyframes import resolve_easing

    ws, pf = _make_ws(tmp_path)
    op = resolve_easing("ease_in_out")
    out = effect_fade(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        fade_in_frames=30, fade_out_frames=30,
        easing="ease_in_out",
    )
    assert out["status"] == "success", out

    filters = _list_filters(ws, pf, TRACK, CLIP)
    rect = filters[-1]["properties"].get("rect", "")
    # resolve_easing("ease_in_out") -> cubic_in_out family default operator 'i'.
    # We look for the op char before '=' at least once.
    assert f"{op}=" in rect, f"expected op {op!r} in {rect!r}"


# ---------------------------------------------------------------------------
# SR-20: flash_cut_montage splits and adds blur
# ---------------------------------------------------------------------------

def test_sr20_montage_splits_clip_and_adds_blur_to_each_piece(tmp_path):
    ws, pf = _make_ws(tmp_path)
    before = _count_snapshots(ws)

    out = flash_cut_montage(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        n_cuts=4, blur_amount=30.0, invert_alt=False,
    )
    assert out["status"] == "success", out
    assert len(out["data"]["split_clip_indices"]) == 4

    # Inspect filters on each resulting piece.
    project = _reparse(ws, pf)
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    for piece in out["data"]["split_clip_indices"]:
        filters = patcher.list_effects(project, (TRACK, piece))
        services = [f["mlt_service"] for f in filters]
        assert "avfilter.dblur" in services, (piece, services)

    # One explicit + one serializer-level pre-write snapshot.
    assert _count_snapshots(ws) - before == 2


# ---------------------------------------------------------------------------
# SR-21: montage alternating pieces get negate
# ---------------------------------------------------------------------------

def test_sr21_montage_alternating_pieces_get_negate(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = flash_cut_montage(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        n_cuts=4, blur_amount=30.0, invert_alt=True,
    )
    assert out["status"] == "success", out
    pieces = out["data"]["split_clip_indices"]
    project = _reparse(ws, pf)
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    for i, piece in enumerate(pieces):
        filters = patcher.list_effects(project, (TRACK, piece))
        services = [f["mlt_service"] for f in filters]
        if i % 2 == 1:
            assert "avfilter.negate" in services, (i, piece, services)
        else:
            assert "avfilter.negate" not in services, (i, piece, services)


# ---------------------------------------------------------------------------
# SR-22: montage n_cuts < 2 errors
# ---------------------------------------------------------------------------

def test_sr22_montage_n_cuts_too_small(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = flash_cut_montage(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, n_cuts=1,
    )
    assert out["status"] == "error"
    assert "n_cuts" in out["message"]


# ---------------------------------------------------------------------------
# SR-23: montage n_cuts exceeds clip duration errors with hint
# ---------------------------------------------------------------------------

def test_sr23_montage_n_cuts_exceeds_duration_errors_with_hint(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # fixture clip duration is 300 frames
    out = flash_cut_montage(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, n_cuts=5000,
    )
    assert out["status"] == "error"
    assert "300" in out["message"] or "duration" in out["message"].lower()
