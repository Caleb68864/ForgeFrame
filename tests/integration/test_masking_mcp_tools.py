"""Integration tests for masking MCP tools (spec 2026-04-13-masking sub-spec 3).

Covers SR-19..SR-37, SR-40, SR-41 -- 21 scenarios exercising the six new
MCP tools via the real workspace + snapshot pipeline.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

fastmcp = pytest.importorskip("fastmcp", reason="fastmcp not installed")

from workshop_video_brain.edit_mcp.server import tools
from workshop_video_brain.edit_mcp.server.tools import (
    effect_add,
    effect_chroma_key,
    effect_chroma_key_advanced,
    effect_object_mask,
    mask_apply,
    mask_set,
    mask_set_shape,
    workspace_create,
)

FIXTURE = Path(__file__).parent / "fixtures" / "keyframe_project.kdenlive"

TRACK = 2
CLIP = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ws(tmp_path: Path, project_name: str = "test.kdenlive") -> tuple[Path, str]:
    media_root = tmp_path / "media"
    media_root.mkdir(parents=True, exist_ok=True)
    result = workspace_create(title="Masking Test", media_root=str(media_root))
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


# ---------------------------------------------------------------------------
# SR-19: All six tools importable and callable
# ---------------------------------------------------------------------------

def test_sr19_all_six_tools_importable():
    for name in (
        "mask_set",
        "mask_set_shape",
        "mask_apply",
        "effect_chroma_key",
        "effect_chroma_key_advanced",
        "effect_object_mask",
    ):
        assert callable(getattr(tools, name)), f"{name} missing from tools module"


# ---------------------------------------------------------------------------
# SR-20: mask_set_shape rect end-to-end
# ---------------------------------------------------------------------------

def test_sr20_mask_set_shape_rect_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.2, 0.2, 0.6, 0.6]",
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index"] == 0
    assert out["data"]["type"] == "rotoscoping"
    assert out["data"]["shape"] == "rect"
    assert "snapshot_id" in out["data"]

    stack = _effects(ws, pf)
    assert stack[0]["mlt_service"] == "rotoscoping"
    spline = json.loads(stack[0]["properties"]["spline"])
    assert len(spline["0"]) == 4


# ---------------------------------------------------------------------------
# SR-21: ellipse produces 32 spline points
# ---------------------------------------------------------------------------

def test_sr21_mask_set_shape_ellipse_32_points(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="ellipse",
        bounds="[0.1, 0.1, 0.8, 0.8]",
    )
    assert out["status"] == "success", out
    stack = _effects(ws, pf)
    spline = json.loads(stack[0]["properties"]["spline"])
    assert len(spline["0"]) == 32


# ---------------------------------------------------------------------------
# SR-22: polygon passthrough preserves 3 points
# ---------------------------------------------------------------------------

def test_sr22_mask_set_shape_polygon_passthrough(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="polygon",
        points="[[0.1, 0.1], [0.5, 0.1], [0.3, 0.5]]",
    )
    assert out["status"] == "success", out
    stack = _effects(ws, pf)
    spline = json.loads(stack[0]["properties"]["spline"])
    kf = spline["0"]
    assert len(kf) == 3
    xs_ys = [(p[1][0], p[1][1]) for p in kf]
    assert xs_ys == [(0.1, 0.1), (0.5, 0.1), (0.3, 0.5)]


# ---------------------------------------------------------------------------
# SR-23: end-to-end sandwich via mask_set_shape + effect_add + mask_apply
# ---------------------------------------------------------------------------

def test_sr23_mask_apply_sandwich_end_to_end(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Start: [transform]; add mask at index 0 -> [mask, transform]
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.2, 0.2, 0.6, 0.6]",
    )
    assert out["status"] == "success", out

    # Add brightness effect -> [mask, transform, brightness]
    out2 = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, effect_name="brightness",
    )
    assert out2["status"] == "success", out2

    stack = _effects(ws, pf)
    # brightness appended at end
    brightness_idx = len(stack) - 1
    assert stack[0]["mlt_service"] == "rotoscoping"

    out3 = mask_apply(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        mask_effect_index=0,
        target_effect_index=brightness_idx,
    )
    assert out3["status"] == "success", out3
    assert "snapshot_id" in out3["data"]

    final = _effects(ws, pf)
    services = [f["mlt_service"] for f in final]
    # mask_start must appear before a mask_apply somewhere
    assert "mask_start" in services
    assert "mask_apply" in services
    ms_i = services.index("mask_start")
    ma_i = services.index("mask_apply")
    assert ms_i < ma_i
    # inner between them includes the original (non-mask) filters
    inner = services[ms_i + 1:ma_i]
    assert any(s not in ("mask_start", "mask_apply") for s in inner)


# ---------------------------------------------------------------------------
# SR-24: mask_apply reorders when mask index > target index
# ---------------------------------------------------------------------------

def test_sr24_mask_apply_reorders(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Start: [transform]. Add brightness -> [transform, brightness]
    out = effect_add(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, effect_name="brightness",
    )
    assert out["status"] == "success", out
    # Insert mask at top -> [mask, transform, brightness]... but we want mask
    # AFTER target. So target = transform at idx 0, mask inserted then moved.
    # Simpler: put mask at TOP (idx 0) and target at idx 0 is transform;
    # mask_effect_index (0) > target_effect_index (0)? equal triggers reorder.
    out2 = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.2, 0.2, 0.6, 0.6]",
    )
    assert out2["status"] == "success", out2
    # Now [mask(0), transform(1), brightness(2)]. Use mask=0, target=0?
    # That's not >=, it's equal. apply_mask_to_effect treats >= as reorder.
    # Wait -- mask=0, target=0 means mask_index >= target_index triggers
    # reorder. Good.
    out3 = mask_apply(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        mask_effect_index=0, target_effect_index=0,
    )
    assert out3["status"] == "success", out3
    assert out3["data"]["reordered"] is True


# ---------------------------------------------------------------------------
# SR-25: effect_chroma_key emits canonical hex 0x00ff00ff for #00FF00
# ---------------------------------------------------------------------------

def test_sr25_effect_chroma_key_canonical_hex(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_chroma_key(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, color="#00FF00",
    )
    assert out["status"] == "success", out
    stack = _effects(ws, pf)
    chroma = [f for f in stack if f["mlt_service"] == "chroma"]
    assert chroma, stack
    assert chroma[0]["properties"]["key"] == "0x00ff00ff"


# ---------------------------------------------------------------------------
# SR-26: invalid color returns _err listing format
# ---------------------------------------------------------------------------

def test_sr26_effect_chroma_key_invalid_color(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_chroma_key(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, color="notcolor",
    )
    assert out["status"] == "error"
    assert "#RRGGBB" in out["message"]


# ---------------------------------------------------------------------------
# SR-27: advanced chroma key tolerance ordering error
# ---------------------------------------------------------------------------

def test_sr27_effect_chroma_key_advanced_tolerance_ordering(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_chroma_key_advanced(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        color="#00FF00",
        tolerance_near=0.5,
        tolerance_far=0.3,
    )
    assert out["status"] == "error"
    assert "tolerance_far must be >= tolerance_near" in out["message"]


# ---------------------------------------------------------------------------
# SR-28: snapshot_id exists on disk after mutating call
# ---------------------------------------------------------------------------

def test_sr28_snapshot_id_exists_on_disk(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.2, 0.2, 0.6, 0.6]",
    )
    assert out["status"] == "success", out
    snap_id = out["data"]["snapshot_id"]
    snap_dir = ws / "projects" / "snapshots" / snap_id
    assert snap_dir.is_dir(), f"snapshot dir missing: {snap_dir}"


# ---------------------------------------------------------------------------
# SR-29: mask_set unknown type
# ---------------------------------------------------------------------------

def test_sr29_mask_set_unknown_type(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        type="garbage", params="{}",
    )
    assert out["status"] == "error"
    for name in ("rotoscoping", "object_mask", "image_alpha"):
        assert name in out["message"]


# ---------------------------------------------------------------------------
# SR-30: mask_set_shape unknown shape
# ---------------------------------------------------------------------------

def test_sr30_mask_set_shape_unknown_shape(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="star",
    )
    assert out["status"] == "error"
    for name in ("rect", "ellipse", "polygon"):
        assert name in out["message"]


# ---------------------------------------------------------------------------
# SR-31: mask_set image_alpha not implemented
# ---------------------------------------------------------------------------

def test_sr31_mask_set_image_alpha_not_implemented(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        type="image_alpha", params="{}",
    )
    assert out["status"] == "error"
    assert "not yet implemented" in out["message"]


# ---------------------------------------------------------------------------
# SR-32: mask_apply target is itself a mask filter
# ---------------------------------------------------------------------------

def test_sr32_mask_apply_cannot_mask_a_mask(tmp_path):
    ws, pf = _make_ws(tmp_path)
    # Insert two masks: [m1, m2, transform]
    r1 = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.1, 0.1, 0.5, 0.5]",
    )
    assert r1["status"] == "success"
    r2 = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.2, 0.2, 0.5, 0.5]",
    )
    assert r2["status"] == "success"
    # Convert m2 to mask_start via mask_apply against transform at idx 2
    r3 = mask_apply(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        mask_effect_index=1, target_effect_index=2,
    )
    assert r3["status"] == "success", r3
    # Now stack has a mask_start filter. Try to use that mask_start as target.
    stack = _effects(ws, pf)
    mask_start_idx = next(
        i for i, f in enumerate(stack) if f["mlt_service"] == "mask_start"
    )
    # Use m1 (still plain rotoscoping) at idx 0 as mask, mask_start as target.
    r4 = mask_apply(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        mask_effect_index=0,
        target_effect_index=mask_start_idx,
    )
    assert r4["status"] == "error", r4
    assert "cannot mask a mask" in r4["message"]


# ---------------------------------------------------------------------------
# SR-33: mask_set rotoscoping with valid params dict succeeds
# ---------------------------------------------------------------------------

def test_sr33_mask_set_rotoscoping_with_params(tmp_path):
    ws, pf = _make_ws(tmp_path)
    params = json.dumps({
        "points": [[0.1, 0.1], [0.5, 0.1], [0.3, 0.5]],
        "feather": 5,
        "feather_passes": 2,
        "alpha_operation": "add",
    })
    out = mask_set(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        type="rotoscoping", params=params,
    )
    assert out["status"] == "success", out
    assert out["data"]["effect_index"] == 0
    assert out["data"]["type"] == "rotoscoping"
    stack = _effects(ws, pf)
    assert stack[0]["mlt_service"] == "rotoscoping"
    assert stack[0]["properties"]["feather"] == "5"
    assert stack[0]["properties"]["feather_passes"] == "2"


# ---------------------------------------------------------------------------
# SR-34: mask_set object_mask with params dict
# ---------------------------------------------------------------------------

def test_sr34_mask_set_object_mask_with_params(tmp_path):
    ws, pf = _make_ws(tmp_path)
    params = json.dumps({"enabled": True, "threshold": 0.7})
    out = mask_set(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        type="object_mask", params=params,
    )
    assert out["status"] == "success", out
    stack = _effects(ws, pf)
    assert stack[0]["mlt_service"] == "frei0r.alpha0ps_alphaspot"


# ---------------------------------------------------------------------------
# SR-35: effect_chroma_key_advanced success path
# ---------------------------------------------------------------------------

def test_sr35_effect_chroma_key_advanced_success(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_chroma_key_advanced(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        color="#00FF00",
        tolerance_near=0.1,
        tolerance_far=0.3,
        edge_smooth=0.05,
    )
    assert out["status"] == "success", out
    assert "snapshot_id" in out["data"]
    stack = _effects(ws, pf)
    assert any(f["mlt_service"] == "avfilter.hsvkey" for f in stack)


# ---------------------------------------------------------------------------
# SR-36: effect_object_mask appends to stack
# ---------------------------------------------------------------------------

def test_sr36_effect_object_mask_appends(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = effect_object_mask(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        enabled=True, threshold=0.5,
    )
    assert out["status"] == "success", out
    stack = _effects(ws, pf)
    assert stack[-1]["mlt_service"] == "frei0r.alpha0ps_alphaspot"
    assert out["data"]["effect_index"] == len(stack) - 1


# ---------------------------------------------------------------------------
# SR-37: mask_set invalid params JSON
# ---------------------------------------------------------------------------

def test_sr37_mask_set_invalid_params_json(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP,
        type="rotoscoping", params="{not json",
    )
    assert out["status"] == "error"
    assert "params" in out["message"].lower() or "json" in out["message"].lower()


# ---------------------------------------------------------------------------
# SR-40: mask_set_shape polygon with <3 points returns error
# ---------------------------------------------------------------------------

def test_sr40_mask_set_shape_polygon_min_points(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="polygon",
        points="[[0.1, 0.1], [0.5, 0.1]]",
    )
    assert out["status"] == "error"
    assert "at least 3" in out["message"]


# ---------------------------------------------------------------------------
# SR-41: mask_set_shape out-of-range normalized coord returns error
# ---------------------------------------------------------------------------

def test_sr41_mask_set_shape_bounds_out_of_range(tmp_path):
    ws, pf = _make_ws(tmp_path)
    out = mask_set_shape(
        workspace_path=str(ws), project_file=pf,
        track=TRACK, clip=CLIP, shape="rect",
        bounds="[0.5, 0.5, 0.8, 0.8]",  # x+w = 1.3 -> out of [0,1]
    )
    assert out["status"] == "error"
    assert "out of" in out["message"].lower() or "[0" in out["message"]
