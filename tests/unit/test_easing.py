"""Easing maths and keyframe baking (prompt 21)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests._testkit import call_tool, solid_color_project
from workshop_video_brain.edit_mcp.pipelines.easing import bake_keyframes, ease
from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    VALID_EASING_NAMES,
    Keyframe,
    build_keyframe_string,
)

FAMILY_NAMES = sorted(n for n in VALID_EASING_NAMES
                      if not n.startswith("smooth") and n not in ("linear",))


@pytest.mark.parametrize("name", FAMILY_NAMES + ["linear", "cubic_bezier", "spring", "g", "g="])
def test_endpoints(name):
    assert ease(name, 0.0) == pytest.approx(0.0, abs=1e-9)
    assert ease(name, 1.0) == pytest.approx(1.0, abs=1e-9)


@pytest.mark.parametrize("name, mid", [
    ("ease_in_cubic", 0.125), ("ease_out_cubic", 0.875), ("ease_in_out_cubic", 0.5),
    ("ease_in_quad", 0.25), ("ease_out_quad", 0.75), ("ease_in_quart", 0.0625),
    ("ease_in_quint", 0.03125), ("ease_in_out_sine", 0.5), ("ease_in_sine", 1 - 0.7071067811865476),
    ("ease_in_expo", 2 ** -5), ("ease_out_bounce", 0.765625), ("linear", 0.5),
    ("ease_out_back", 1 + 2.70158 * -0.125 + 1.70158 * 0.25),
])
def test_midpoints(name, mid):
    assert ease(name, 0.5) == pytest.approx(mid, abs=1e-6)


def test_cubic_bezier():
    for t in (0.1, 0.37, 0.8):
        assert ease("cubic_bezier", t, x1=0, y1=0, x2=1, y2=1) == pytest.approx(t, abs=1e-6)
        assert ease("cubic_bezier(0,0,1,1)", t) == pytest.approx(t, abs=1e-6)
    assert ease("cubic_bezier", 0.5) == pytest.approx(0.5, abs=1e-6)  # default handles are symmetric
    assert ease("cubic_bezier(0.42,0,1,1)", 0.5) < 0.5  # an ease-in


def test_parameters():
    assert ease("back_out(2.5)", 0.5) > ease("back_out", 0.5)  # more overshoot
    assert ease("spring", 0.4) > 0.9
    with pytest.raises(ValueError, match="at most"):
        ease("spring(1,2,3)", 0.5)


def test_smooth_cannot_be_baked():
    with pytest.raises(ValueError, match="spline"):
        ease("smooth", 0.5)
    with pytest.raises(ValueError, match="spline"):
        bake_keyframes([Keyframe(0, 0.0, "smooth"), Keyframe(10, 1.0, "linear")])


def test_bake_keeps_originals_and_is_linear():
    kfs = [Keyframe(0, 0.0, "ease_in_cubic"), Keyframe(10, 100.0, "linear"), Keyframe(20, 50.0, "linear")]
    baked = bake_keyframes(kfs)
    assert all(k.easing == "linear" for k in baked)
    by_frame = {k.frame: k.value for k in baked}
    assert (by_frame[0], by_frame[10], by_frame[20]) == (0.0, 100.0, 50.0)
    assert by_frame[5] == pytest.approx(12.5)  # 100 * 0.5^3
    assert sorted(by_frame) == list(range(0, 11)) + [20]  # linear segment untouched


def test_bake_rect_color_step_and_limit():
    rect = bake_keyframes([Keyframe(0, [0, 0, 100, 100], "ease_out_quad"),
                           Keyframe(4, [40, 0, 100, 100, 0.5], "linear")], step=2)
    assert [k.frame for k in rect] == [0, 2, 4]
    assert rect[1].value == pytest.approx([30.0, 0, 100, 100, 0.625])  # y = 0.75
    colour = bake_keyframes([Keyframe(0, "#000000", "ease_in_out_sine"), Keyframe(2, "#ffffff", "linear")])
    assert colour[1].value == "0x7f7f7fff"  # 127.5 rounds half-even
    with pytest.raises(ValueError, match="more than"):
        bake_keyframes([Keyframe(0, 0.0, "ease_in_cubic"), Keyframe(5000, 1.0, "linear")])


def test_bake_hold_stays_flat_until_the_next_keyframe():
    baked = bake_keyframes([Keyframe(0, 1.0, "hold"), Keyframe(10, 2.0, "linear")], step=4)
    assert {k.frame: k.value for k in baked}[9] == 1.0


def test_baked_string_is_operator_free():
    baked = bake_keyframes([Keyframe(0, 0.0, "cubic_bezier"), Keyframe(5, 1.0, "linear")])
    out = build_keyframe_string("scalar", baked, 25.0)
    assert out.count(";") == 5 and all(seg.split("=")[0][-1].isdigit() for seg in out.split(";"))


# ---------------------------------------------------------------------------
# Keyframe tools: bake / bake-only names
# ---------------------------------------------------------------------------

@pytest.fixture
def ws(tmp_path) -> Path:
    from workshop_video_brain.core.models.timeline import AddEffect
    from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import patch_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.workspace.manager import WorkspaceManager

    root = tmp_path / "ws"
    WorkspaceManager.create("KF", tmp_path, workspace_root=root)
    project = patch_project(solid_color_project(), [AddEffect(track_index=0, clip_index=0,
                                                              effect_name="brightness")])
    serialize_project(project, root / "p.kdenlive")
    return root


def _set(ws, keyframes, **kw):
    from workshop_video_brain.edit_mcp.server.tools.keyframes import effect_keyframe_set_scalar
    return call_tool(effect_keyframe_set_scalar, str(ws), "p.kdenlive", 0, 0, 0, "level",
                     json.dumps(keyframes), **kw)


def test_tool_native_unchanged_and_bake(ws):
    kfs = [{"frame": 0, "value": 0, "easing": "ease_in_cubic"}, {"frame": 10, "value": 1}]
    native = _set(ws, kfs)
    assert native["status"] == "success", native
    assert native["data"]["keyframes_written"] == "00:00:00.000g=0;00:00:00.400=1"
    baked = _set(ws, kfs, bake=True, bake_step=5)
    assert baked["data"]["keyframes_written"] == "00:00:00.000=0;00:00:00.200=0.125;00:00:00.400=1"


def test_tool_refuses_bake_only_names_without_bake(ws):
    kfs = [{"frame": 0, "value": 0, "easing": "cubic_bezier(0.2,0,0.2,1)"}, {"frame": 10, "value": 1}]
    refused = _set(ws, kfs)
    assert refused["error_type"] == "invalid_input" and "bake=true" in refused["suggestion"]
    assert _set(ws, kfs, bake=True)["status"] == "success"
