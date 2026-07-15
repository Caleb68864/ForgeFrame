"""Render-proof for ``effect_pan_zoom`` (item 6 verification).

Establishes, with real ``melt``, that:

* a **bare ``rect`` on the ``affine``/``transform`` filter is a NO-OP** (output
  byte-for-byte the same framing as no filter) -- the latent bug the pan/zoom
  bundle used to ship; and
* the shipped fix (``affine`` ``transition.rect`` fed the destination rect from
  ``pan_zoom.build_pan_zoom_transform_keyframes``) **actually moves pixels** --
  a centred zoom-in grows a centred marker's on-screen area.

The framing is measured by the fraction of red pixels covering a blue frame that
carries a centred red square: zooming into the centre must increase it.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
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
from workshop_video_brain.edit_mcp.pipelines import pan_zoom as pz

from ._oracle import render_frame

pytestmark = pytest.mark.external

PIL = pytest.importorskip("PIL.Image")

W, H, FR = 320, 180, 30
FRAME = 10


def _red_fraction(im) -> float:
    data = im.tobytes()
    n = len(data) // 3
    hits = 0
    for i in range(0, len(data), 3):
        r, g, b = data[i], data[i + 1], data[i + 2]
        if r > 140 and g < 90 and b < 90:
            hits += 1
    return hits / n


def _centered_marker_png(render_dir: Path) -> str:
    img = PIL.new("RGB", (W, H), (0, 0, 255))
    img.paste(PIL.new("RGB", (80, 80), (255, 0, 0)), ((W - 80) // 2, (H - 80) // 2))
    path = render_dir / "marker.png"
    img.save(path)
    return str(path)


def _build(png_resource: str, rect_property: str | None, rect_value: str | None) -> KdenliveProject:
    p = KdenliveProject(
        version="7", title="pz_render",
        profile=ProjectProfile(width=W, height=H, fps=25.0, colorspace="709"),
    )
    p.producers = [
        Producer(id="img", resource=png_resource,
                 properties=io.image_producer_properties(png_resource, FR + 10)),
    ]
    p.tracks = [
        Track(id="pv", track_type="video", name="V1"),
        Track(id="pa", track_type="audio", name="A"),
    ]
    p.playlists = [
        Playlist(id="pv", entries=[PlaylistEntry(producer_id="img", in_point=0, out_point=FR - 1)]),
        Playlist(id="pa", entries=[PlaylistEntry(producer_id="img", in_point=0, out_point=FR - 1)]),
    ]
    if rect_property is not None:
        root = ET.Element("filter", {"mlt_service": "affine", "track": "0", "clip_index": "0"})
        ET.SubElement(root, "property", {"name": "mlt_service"}).text = "affine"
        ET.SubElement(root, "property", {"name": "kdenlive_id"}).text = "transform"
        ET.SubElement(root, "property", {"name": rect_property}).text = rect_value
        p.opaque_elements = [OpaqueElement(tag="filter", xml_string=ET.tostring(root, encoding="unicode"))]
    p.tractor = {"id": "tractor0", "in": "0", "out": str(FR - 1)}
    return p


def _render_fraction(proj, name, render_dir, melt_bin) -> float:
    path = render_dir / f"{name}.kdenlive"
    serialize_project(proj, path)
    png = render_frame(path, FRAME, render_dir, melt_bin=melt_bin, name=f"{name}.png")
    return _red_fraction(PIL.open(png).convert("RGB"))


def test_bare_rect_on_affine_is_a_noop(melt_bin, render_dir: Path):
    png = _centered_marker_png(render_dir)
    baseline = _render_fraction(_build(png, None, None), "base", render_dir, melt_bin)
    # Bare `rect` naming a centred zoom-in source region -- the pre-fix output.
    _s, end = pz.preset_rects("zoom_in", W, H)
    bare = " ".join(str(int(round(v))) for v in end) + " 1"
    bare_frac = _render_fraction(
        _build(png, "rect", bare), "bare", render_dir, melt_bin
    )
    assert abs(bare_frac - baseline) < 0.01, (
        f"bare `rect` on affine unexpectedly changed framing "
        f"(baseline={baseline:.3f} bare={bare_frac:.3f}) -- if this fails the "
        "MLT build now honours a bare rect and the no-op premise changed"
    )


def test_transition_rect_zoom_moves_pixels(melt_bin, render_dir: Path):
    png = _centered_marker_png(render_dir)
    # Sample near the end of the clip. The move spans the whole clip (as the
    # real tool defaults duration to the clip length) so the sampled frame is
    # inside the keyframe range -- affine does not hold a value past its last
    # keyframe, so covering the clip is what the bundle relies on.
    sample = FR - 2
    base_path = render_dir / "base2.kdenlive"
    serialize_project(_build(png, None, None), base_path)
    baseline = _red_fraction(
        PIL.open(render_frame(base_path, sample, render_dir, melt_bin=melt_bin,
                              name="base2.png")).convert("RGB")
    )
    # The shipped fix: destination rect keyframes on `transition.rect`.
    start, end = pz.preset_rects("zoom_in", W, H)
    kf = pz.build_pan_zoom_transform_keyframes(start, end, W, H, FR, 25.0, easing="linear")
    zoom_path = render_dir / "zoom.kdenlive"
    serialize_project(_build(png, "transition.rect", kf), zoom_path)
    zoomed = _red_fraction(
        PIL.open(render_frame(zoom_path, sample, render_dir, melt_bin=melt_bin,
                              name="zoom.png")).convert("RGB")
    )
    assert zoomed > baseline + 0.05, (
        f"zoom-in did not enlarge the centred marker (baseline={baseline:.3f} "
        f"zoomed={zoomed:.3f}) -- transform is not moving pixels"
    )
