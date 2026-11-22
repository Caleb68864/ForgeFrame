"""Real melt: baked easing matches MLT's operator; camera moves leave no black edges (prompt 21)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tests._testkit import call_tool, make_test_clip, requires_ffmpeg, solid_color_project
from workshop_video_brain.core.models.kdenlive import Producer
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines.easing import bake_keyframes
from workshop_video_brain.edit_mcp.pipelines.keyframes import Keyframe, build_keyframe_string
from workshop_video_brain.edit_mcp.server.bundles.camera_moves import effect_camera_move
from workshop_video_brain.workspace.manager import WorkspaceManager

from . import builders
from ._oracle import frames_differ, frames_similar, render_frame

pytestmark = pytest.mark.external

W, H, FPS = 320, 180, 25.0
FRAME = 10


def _red_x_centroid(png: Path) -> float | None:
    with Image.open(png) as image:
        rgb = image.convert("RGB")
        xs = [x for y in range(0, rgb.height, 2) for x in range(rgb.width)
              if (lambda p: p[0] > 150 and p[1] < 80 and p[2] < 80)(rgb.getpixel((x, y)))]
    return sum(xs) / len(xs) if xs else None


def _moving_box(render_dir: Path, name: str, rect: str, melt_bin: str) -> Path:
    project = solid_color_project(color=builders.RED)
    xml = builders.build_filter_xml("qtblend", track=0, clip=0, kdenlive_id="qtblend", props=[("rect", rect)])
    patcher.insert_effect_xml(project, (0, 0), xml, position=0)
    path = render_dir / f"{name}.kdenlive"
    serialize_project(project, path)
    return render_frame(path, FRAME, render_dir, melt_bin=melt_bin, name=f"{name}.png")


def _box_keyframes(easing: str):
    box_w, box_h = W // 4, H // 4
    return [Keyframe(0, [0, 0, box_w, box_h, 1], easing), Keyframe(20, [W - box_w, 0, box_w, box_h, 1], "linear")]


def test_baked_cubic_in_matches_mlt_operator(melt_bin, render_dir):
    native = _moving_box(render_dir, "native", build_keyframe_string("rect", _box_keyframes("ease_in_cubic"), FPS), melt_bin)
    with Image.open(native) as image:
        corner = image.convert("RGB").getpixel((W - 2, H - 2))
    assert max(corner) < 40, f"outside the qtblend rect is not black: {corner}"
    baked = _moving_box(render_dir, "baked", build_keyframe_string(
        "rect", bake_keyframes(_box_keyframes("ease_in_cubic")), FPS), melt_bin)
    linear = _moving_box(render_dir, "linear", build_keyframe_string("rect", _box_keyframes("linear"), FPS), melt_bin)
    cx_native, cx_baked, cx_linear = (_red_x_centroid(p) for p in (native, baked, linear))
    # At t = 0.5: linear centre 40 + 120 = 160 px, cubic-in 40 + 240 * 0.125 = 70 px.
    assert abs(cx_native - cx_baked) <= 2, (cx_native, cx_baked)
    assert cx_baked < cx_linear - 40, (cx_baked, cx_linear)


def _workspace(tmp_path: Path, project) -> Path:
    root = tmp_path / "ws"
    WorkspaceManager.create("Cam", tmp_path, workspace_root=root)
    serialize_project(project, root / "p.kdenlive")
    return root


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


@pytest.mark.parametrize("move, kwargs", [
    ("zoom_punch", {"at_frame": 12}),
    ("orbit", {"revolutions": 1.0}),
    ("handheld", {"intensity": "aggressive", "seed": 5}),
])
def test_moves_leave_no_black_edges(melt_bin, tmp_path, render_dir, move, kwargs):
    root = _workspace(tmp_path, solid_color_project(color=builders.GREEN, frames=50))
    _ok(call_tool(effect_camera_move, str(root), "p.kdenlive", 0, 0, move, **kwargs))
    for frame in (1, 12, 20, 33, 47):
        png = render_frame(root / "p.kdenlive", frame, render_dir, melt_bin=melt_bin, name=f"{move}_{frame}.png")
        with Image.open(png) as image:
            rgb = image.convert("RGB")
            for corner in ((0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1)):
                r, g, b = rgb.getpixel(corner)
                assert g > 150 and r < 90 and b < 90, f"{move} frame {frame} corner {corner}: {(r, g, b)}"


@requires_ffmpeg
def test_punch_and_orbit_move_pixels(melt_bin, tmp_path, render_dir):
    clip = make_test_clip(tmp_path / "bars.mp4", duration=4.0, size=(W, H))
    project = solid_color_project(frames=100)
    source = project.producers[0]
    project.producers[0] = Producer(id=source.id, resource=str(clip), properties={
        "resource": str(clip), "mlt_service": "avformat", "length": "100"})
    root = _workspace(tmp_path, project)
    plain_peak = render_frame(root / "p.kdenlive", 20, render_dir, melt_bin=melt_bin, name="plain20.png")
    plain_after = render_frame(root / "p.kdenlive", 45, render_dir, melt_bin=melt_bin, name="plain45.png")
    _ok(call_tool(effect_camera_move, str(root), "p.kdenlive", 0, 0, "zoom_punch", at_frame=20, intensity="0.3"))
    peak = render_frame(root / "p.kdenlive", 20, render_dir, melt_bin=melt_bin, name="punch20.png")
    after = render_frame(root / "p.kdenlive", 45, render_dir, melt_bin=melt_bin, name="punch45.png")
    assert frames_differ(plain_peak, peak), "zoom punch did not change the peak frame"
    assert frames_similar(plain_after, after), "zoom punch did not settle back"

    root2 = _workspace(tmp_path / "o", project)
    _ok(call_tool(effect_camera_move, str(root2), "p.kdenlive", 0, 0, "orbit", start_frame=0, end_frame=80,
                  radius_px=12.0))
    quarter = render_frame(root2 / "p.kdenlive", 20, render_dir, melt_bin=melt_bin, name="orbit20.png")
    three_q = render_frame(root2 / "p.kdenlive", 60, render_dir, melt_bin=melt_bin, name="orbit60.png")
    assert frames_differ(quarter, three_q, min_delta=3.0), "orbit at 1/4 and 3/4 rendered the same"
