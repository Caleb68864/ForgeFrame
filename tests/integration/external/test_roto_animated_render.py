"""Animated rotoscoping: does a keyframed spline produce a *moving* matte?

The hard blocker for ``effect_clone_self`` (and three other tutorial bundles)
was that ``masking._spline_json`` emitted a frame-0-only spline, so a rotoscope
mask could never follow a subject. This proves the fix end-to-end against real
melt + frei0r:

* Build a two-video-track project -- solid RED on the bottom, solid GREEN on
  top. The top clip carries a ``rotoscoping`` alpha mask (built by the real
  ``masking.build_rotoscoping_xml`` pipeline). Inside the mask the GREEN is
  opaque and composites over RED; outside it is transparent (RED shows).
* With an **animated** spline (a box keyframed from the LEFT third at frame 0
  to the RIGHT third at the last frame) the GREEN patch must be on the LEFT at
  frame 0 and on the RIGHT at the last frame -- i.e. the masked region is
  provably at a different position at frame 0 vs frame N.
* Control: a **static** (frame-0-only) spline must NOT move -- GREEN stays on
  the LEFT at both frames. This isolates the animation as the cause.

Skips when the frei0r ``rotoscoping`` filter is not present on this melt build.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import (
    serialize_project,
)
from workshop_video_brain.edit_mcp.pipelines import masking

from . import builders
from ._oracle import render_frame

pytestmark = pytest.mark.external

FRAMES = 50
LAST = FRAMES - 1  # last content frame

# Box half-extents (normalized) and the two horizontal centres the matte
# travels between.
_HW, _HH = 0.14, 0.30
_LEFT_CX, _RIGHT_CX = 0.25, 0.75
_CY = 0.5


def _box(cx: float, cy: float) -> tuple[tuple[float, float], ...]:
    return (
        (cx - _HW, cy - _HH),
        (cx + _HW, cy - _HH),
        (cx + _HW, cy + _HH),
        (cx - _HW, cy + _HH),
    )


def _region_rgb(png: Path, cx: float, cy: float, half: int = 10) -> tuple[float, float, float]:
    """Mean (R, G, B) of a small square centred on the normalized (cx, cy)."""
    im = Image.open(png).convert("RGB")
    w, h = im.size
    px, py = int(cx * w), int(cy * h)
    crop = im.crop((px - half, py - half, px + half, py + half))
    data = crop.tobytes()
    n = max(1, len(data) // 3)
    return (
        sum(data[0::3]) / n,
        sum(data[1::3]) / n,
        sum(data[2::3]) / n,
    )


def _is_green(rgb: tuple[float, float, float]) -> bool:
    return rgb[1] > 110 and rgb[0] < 100


def _is_red(rgb: tuple[float, float, float]) -> bool:
    return rgb[0] > 110 and rgb[1] < 100


def _skip_without_roto(melt_bin: str) -> None:
    from .conftest import melt_has_service

    if not melt_has_service(melt_bin, "filters", "rotoscoping"):
        pytest.skip("frei0r rotoscoping filter not on this melt build")


def _roto_project(spline_keyframes=None, points=None):
    """GREEN-over-RED two-track project with a rotoscoping alpha mask on top."""
    proj = builders.two_video_track_project(
        top_color=builders.GREEN, bottom_color=builders.RED, frames=FRAMES
    )
    mask = masking.MaskParams(
        points=points or (),
        spline_keyframes=spline_keyframes,
        mode="alpha",
        alpha_operation="clear",
    )
    # Top track is playlist index 1, clip 0.
    xml = masking.build_rotoscoping_xml((1, 0), mask)
    patcher.insert_effect_xml(proj, (1, 0), xml, position=0)
    return proj


def _render(proj, name, render_dir, frame, melt_bin):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    return render_frame(path, frame, render_dir, melt_bin=melt_bin, name=f"{name}_f{frame}.png")


def test_animated_matte_moves(melt_bin, render_dir: Path):
    """A keyframed spline puts the GREEN patch LEFT at f0 and RIGHT at fN."""
    _skip_without_roto(melt_bin)
    proj = _roto_project(
        spline_keyframes={
            0: _box(_LEFT_CX, _CY),
            LAST: _box(_RIGHT_CX, _CY),
        }
    )
    f0 = _render(proj, "roto_anim", render_dir, 0, melt_bin)
    fN = _render(proj, "roto_anim", render_dir, LAST, melt_bin)

    left0 = _region_rgb(f0, _LEFT_CX, _CY)
    right0 = _region_rgb(f0, _RIGHT_CX, _CY)
    leftN = _region_rgb(fN, _LEFT_CX, _CY)
    rightN = _region_rgb(fN, _RIGHT_CX, _CY)

    assert _is_green(left0), f"frame 0 LEFT should be masked-in GREEN, got {left0}"
    assert _is_red(right0), f"frame 0 RIGHT should be RED, got {right0}"
    assert _is_red(leftN), f"frame {LAST} LEFT should have moved to RED, got {leftN}"
    assert _is_green(rightN), f"frame {LAST} RIGHT should be masked-in GREEN, got {rightN}"


def test_static_matte_does_not_move(melt_bin, render_dir: Path):
    """A frame-0-only spline keeps the GREEN patch on the LEFT at both frames."""
    _skip_without_roto(melt_bin)
    proj = _roto_project(points=_box(_LEFT_CX, _CY))
    f0 = _render(proj, "roto_static", render_dir, 0, melt_bin)
    fN = _render(proj, "roto_static", render_dir, LAST, melt_bin)

    assert _is_green(_region_rgb(f0, _LEFT_CX, _CY)), "static: LEFT green at f0"
    assert _is_green(_region_rgb(fN, _LEFT_CX, _CY)), (
        "static matte moved -- frame-0 spline should be stationary"
    )
