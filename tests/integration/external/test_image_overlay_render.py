"""image-overlay render proof: a still on a top track composites over the
footage, and its alpha is honoured, in real ``melt``.

Three external-truth probes (PIL builds the fixtures; melt renders; pixels are
decoded and asserted):

* ``test_transparent_png_alpha_honoured`` -- a red PNG with a fully-transparent
  border, laid full-frame over a blue colour clip, renders **red in the centre**
  and **blue in the corner** (the footage shows through the transparent region).
* ``test_svg_overlay_renders`` -- an SVG (green disc on transparent) laid over
  blue renders **green in the centre**, **blue in the corner** (SVG verdict:
  supported).
* ``test_watermark_corner_quadrant`` -- an opaque red logo positioned in the
  bottom-right via the qtblend transform lands in the **bottom-right quadrant**
  (red there, blue in the top-left) -- corner placement math is honoured.

The projects are assembled exactly the way ``bundles/image_overlay.py`` does
(``image_overlay`` producer props + qtblend transform filter), so this exercises
the real load-bearing path without importing the workspace/MCP layer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
    Playlist,
    PlaylistEntry,
    Producer,
    ProjectProfile,
    Track,
)
from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
from workshop_video_brain.edit_mcp.pipelines import image_overlay as io

from ._oracle import render_frame

pytestmark = pytest.mark.external

PIL = pytest.importorskip("PIL.Image")

W, H, FR = 320, 180, 50
FRAME = 10
BLUE = "0x0000ffff"

# Downscale-robust colour classifiers (melt/codec rounding-tolerant).
def _is_red(px):
    r, g, b = px
    return r > 140 and g < 90 and b < 90


def _is_blue(px):
    r, g, b = px
    return b > 140 and r < 90 and g < 90


def _is_green(px):
    r, g, b = px
    return g > 120 and r < 110 and b < 110


def _mean_quadrant(im, box):
    """Mean RGB over a pixel box (l, t, r, b)."""
    crop = im.crop(box)
    data = crop.tobytes()  # RGB, 3 bytes/pixel
    n = len(data) // 3
    return (
        sum(data[0::3]) / n,
        sum(data[1::3]) / n,
        sum(data[2::3]) / n,
    )


def _build(png_resource: str, transform_rect: str | None) -> KdenliveProject:
    """Blue base (track 0) + image overlay (track 1), titles-style.

    When ``transform_rect`` is given, a qtblend transform filter is attached to
    the overlay clip (playlist index 1, clip 0) -- exactly what the bundle emits.
    """
    p = KdenliveProject(
        version="7",
        title="ovl_render",
        profile=ProjectProfile(width=W, height=H, fps=25.0, colorspace="709"),
    )
    p.producers = [
        Producer(id="bg", resource=BLUE,
                 properties={"resource": BLUE, "mlt_service": "color", "length": str(FR + 10)}),
        Producer(id="img", resource=png_resource,
                 properties=io.image_producer_properties(png_resource, FR + 10)),
    ]
    p.tracks = [
        Track(id="pv", track_type="video", name="V1"),
        Track(id="pv2", track_type="video", name="V2"),
        Track(id="pa", track_type="audio", name="A"),
    ]
    p.playlists = [
        Playlist(id="pv", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=FR - 1)]),
        Playlist(id="pv2", entries=[PlaylistEntry(producer_id="img", in_point=0, out_point=FR - 1)]),
        Playlist(id="pa", entries=[PlaylistEntry(producer_id="bg", in_point=0, out_point=FR - 1)]),
    ]
    if transform_rect is not None:
        xml = io.build_transform_filter_xml(1, 0, transform_rect)
        p.opaque_elements = [OpaqueElement(tag="filter", xml_string=xml)]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(FR - 1)}
    return p


def _render(proj, name, render_dir, melt_bin):
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    png = render_frame(path, FRAME, render_dir, melt_bin=melt_bin, name=f"{name}.png")
    return PIL.open(png).convert("RGB")


def _red_transparent_border_png(render_dir: Path) -> str:
    """Red centre (opaque) with a fully-transparent border."""
    img = PIL.new("RGBA", (200, 200), (0, 0, 0, 0))
    red = PIL.new("RGBA", (120, 120), (255, 0, 0, 255))
    img.paste(red, (40, 40))
    path = render_dir / "red_border.png"
    img.save(path)
    return str(path)


def test_transparent_png_alpha_honoured(melt_bin, render_dir: Path):
    png = _red_transparent_border_png(render_dir)
    im = _render(_build(png, transform_rect=None), "png_alpha", render_dir, melt_bin)
    center = im.getpixel((W // 2, H // 2))
    corner = im.getpixel((3, 3))
    assert _is_red(center), f"overlay centre not red: {center}"
    assert _is_blue(corner), (
        f"footage not visible through transparent border (corner={corner}) -- "
        "alpha not honoured"
    )


def test_svg_overlay_renders(melt_bin, render_dir: Path):
    svg = render_dir / "disc.svg"
    svg.write_text(
        '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" '
        'width="200" height="200"><circle cx="100" cy="100" r="80" '
        'fill="#00ff00"/></svg>'
    )
    im = _render(_build(str(svg), transform_rect=None), "svg_ovl", render_dir, melt_bin)
    center = im.getpixel((W // 2, H // 2))
    corner = im.getpixel((3, 3))
    assert _is_green(center), f"SVG disc not rendered green at centre: {center}"
    assert _is_blue(corner), f"SVG background not transparent (corner={corner})"


def test_watermark_corner_quadrant(melt_bin, render_dir: Path):
    # Opaque red logo positioned in the bottom-right via the qtblend transform.
    logo = PIL.new("RGBA", (100, 100), (255, 0, 0, 255))
    logo_path = render_dir / "logo.png"
    logo.save(logo_path)

    rect = io.position_rect("bottom_right", W, H, scale=0.35, margin=0.03)
    x, y, w, h = rect
    rect_value = io.rect_to_string(rect, opacity=1.0)
    im = _render(_build(str(logo_path), transform_rect=rect_value),
                 "wm_corner", render_dir, melt_bin)

    # The watermark centre (inside the bottom-right quadrant) is red; the
    # opposite top-left corner is untouched footage (blue).
    wm_center = im.getpixel((x + w // 2, y + h // 2))
    top_left = im.getpixel((10, 10))
    assert x + w // 2 > W // 2 and y + h // 2 > H // 2, "rect not in bottom-right quadrant"
    assert _is_red(wm_center), f"watermark not placed at bottom-right (px={wm_center})"
    assert _is_blue(top_left), f"top-left corner not clean footage (px={top_left})"

    # And the bottom-right quadrant carries materially more red than the top-left.
    br_mean = _mean_quadrant(im, (W // 2, H // 2, W, H))
    tl_mean = _mean_quadrant(im, (0, 0, W // 2, H // 2))
    assert br_mean[0] > tl_mean[0] + 30, (
        f"bottom-right quadrant not redder than top-left (br={br_mean} tl={tl_mean})"
    )
