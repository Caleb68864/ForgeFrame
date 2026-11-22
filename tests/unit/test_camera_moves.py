"""Named camera moves: zoom punch, orbit, handheld (prompt 21)."""
from __future__ import annotations

import math

import pytest

from tests._testkit import assert_registered, call_tool, solid_color_project
from workshop_video_brain.edit_mcp.pipelines import camera_moves
from workshop_video_brain.edit_mcp.pipelines.keyframes import parse_keyframe_string

W, H, FPS = 1920, 1080, 25.0


def _rects(result):
    return parse_keyframe_string("rect", result["rect"], fps=FPS)


def _covers(rect, angle_deg=0.0):
    x, y, w, h = rect[:4]
    if angle_deg == 0:
        return x <= 1e-6 and y <= 1e-6 and x + w >= W - 1e-6 and y + h >= H - 1e-6
    # Rotated about the rect centre: every viewport corner must be inside the rect.
    cx, cy, a = x + w / 2, y + h / 2, math.radians(angle_deg)
    for px, py in ((0, 0), (W, 0), (0, H), (W, H)):
        dx, dy = px - cx, py - cy
        u = dx * math.cos(a) + dy * math.sin(a)
        v = -dx * math.sin(a) + dy * math.cos(a)
        if abs(u) > w / 2 + 1e-6 or abs(v) > h / 2 + 1e-6:
            return False
    return True


def test_zoom_punch_peaks_at_frame_and_covers():
    result = camera_moves.zoom_punch(W, H, at_frame=20, fps=FPS, intensity=0.2)
    kfs = _rects(result)
    assert list(kfs[0].value[:4]) == [0, 0, W, H]  # rest
    peak = max(kfs, key=lambda k: k.value[2])
    assert peak.frame == 20 and peak.value[2] == pytest.approx(W * 1.2)
    assert all(_covers(k.value) for k in kfs)
    assert list(kfs[-1].value[:4]) == [0, 0, W, H] and kfs[-1].frame == 30


def test_zoom_punch_anchor_is_clamped():
    kfs = _rects(camera_moves.zoom_punch(W, H, at_frame=5, fps=FPS, anchor=(1.5, -0.5)))
    assert all(_covers(k.value) for k in kfs)


def test_orbit_covers_and_starts_at_rest():
    result = camera_moves.orbit(W, H, 0, 100, FPS, revolutions=2)
    kfs = _rects(result)
    assert all(_covers(k.value) for k in kfs)
    x, y, w, h = kfs[0].value[:4]
    assert (x, y) == pytest.approx((-(w - W) / 2, -(h - H) / 2), abs=0.01)  # centred overscan
    assert kfs[-1].frame == 100 and len(kfs) == 49


def test_handheld_is_deterministic_covers_and_rests():
    a = camera_moves.handheld(W, H, 0, 125, FPS, intensity="aggressive", seed=7)
    b = camera_moves.handheld(W, H, 0, 125, FPS, intensity="aggressive", seed=7)
    c = camera_moves.handheld(W, H, 0, 125, FPS, intensity="aggressive", seed=8)
    assert a == b and a["rect"] != c["rect"]
    rects = _rects(a)
    angles = parse_keyframe_string("scalar", a["rotation"], fps=FPS)
    assert [k.frame for k in rects] == [k.frame for k in angles]  # same timestamps
    assert all(_covers(r.value, ang.value) for r, ang in zip(rects, angles))
    assert angles[0].value == 0 and angles[-1].value == 0
    level = camera_moves.handheld(W, H, 0, 125, FPS, rotation=False)
    assert level["rotation"] is None


@pytest.mark.parametrize("call", [
    lambda: camera_moves.zoom_punch(W, H, at_frame=-1, fps=FPS),
    lambda: camera_moves.orbit(W, H, 10, 5, FPS),
    lambda: camera_moves.handheld(W, H, 0, 10, FPS, intensity="wild"),
])
def test_validation(call):
    with pytest.raises(ValueError):
        call()


def test_tool_registered_and_validates_move(tmp_path):
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.server.bundles.camera_moves import effect_camera_move
    from workshop_video_brain.workspace.manager import WorkspaceManager

    assert_registered("effect_camera_move")
    root = tmp_path / "ws"
    WorkspaceManager.create("Cam", tmp_path, workspace_root=root)
    serialize_project(solid_color_project(), root / "p.kdenlive")
    bad = call_tool(effect_camera_move, str(root), "p.kdenlive", 0, 0, "dolly")
    assert bad["error_type"] == "invalid_input" and "zoom_punch" in bad["message"]
    no_hit = call_tool(effect_camera_move, str(root), "p.kdenlive", 0, 0, "zoom_punch")
    assert no_hit["error_type"] == "invalid_input" and "at_frame" in no_hit["message"]
    ok = call_tool(effect_camera_move, str(root), "p.kdenlive", 0, 0, "handheld", seed=3)
    assert ok["status"] == "success", ok
    assert ok["data"]["rotation"] and ok["data"]["keyframe_count"] > 2
