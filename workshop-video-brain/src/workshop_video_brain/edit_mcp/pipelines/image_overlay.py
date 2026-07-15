"""Pure logic for single-image / PNG timeline overlays and watermarks.

A still image (instruction diagram, logo/watermark, step-number card) is placed
on a video track *above* the footage so it composites over it.  This mirrors the
title-card model-level pattern in ``pipelines/titles.py`` +
``server/bundles/titles.py``: register an image **producer** on the project model
(no serializer/parser edits) and drop a blank-padded ``PlaylistEntry`` on a top
video track.  The serializer's per-track always-active ``frei0r.cairoblend``
compositor then makes the upper track visible over the lower ones **and honours
the image's own alpha channel** -- exactly how titles composite.

Empirical grounding (verified headless with real ``melt`` on this build):

* Producer -- **``qimage``** (Qt ``QImage``).  ``melt -query producer=qimage``
  advertises ``image_formats: rgb, rgba`` so alpha is honoured; the serializer
  already classifies ``qimage``/``pixbuf`` as Kdenlive Image clips
  (``serializer._clip_type`` -> ``"5"``).  ``pixbuf`` renders identically here;
  ``qimage`` is chosen because it is Kdenlive's native still producer and shares
  Qt with the rest of the toolchain.
* **SVG is supported** -- both ``qimage`` and ``pixbuf`` rasterise an ``.svg``
  resource (green-circle SVG rendered correctly over a colour background in the
  render proof).
* Geometry / corner placement -- a **``qtblend``** clip filter carrying a
  ``rect`` = ``"x y w h opacity"`` positions + scales the still and preserves the
  source alpha; its ``rect`` accepts a keyframe-animation string, so opacity
  fades animate through the same filter.  ``affine`` with a bare ``rect`` prop is
  a no-op on this build (the known §1.1 ``effect_fade`` mismatch) -- ``qtblend``
  is used instead.
* A still holds for N frames purely via the producer ``length`` (>= the entry
  out-point) and the entry ``[0, N-1]``; ``ttl`` only matters for image
  *sequences* and is set equal to ``length`` for good measure.

This module is pure: it builds property dicts / geometry / filter XML strings and
does no filesystem or MCP work.  The bundle in
``edit_mcp/server/bundles/image_overlay.py`` wires it into a project.
"""
from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.effect_presets import build_fade_keyframes
from workshop_video_brain.edit_mcp.pipelines.keyframes import (
    Keyframe,
    _format_scalar,
    build_keyframe_string,
)

# Chosen MLT still producer (see module docstring for the empirical verdict).
IMAGE_PRODUCER_SERVICE = "qimage"

# Raster + vector still formats the qimage/pixbuf producer loads.  SVG is
# included: it rasterises on this build (render-proof verified).
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".svg"}
)
SVG_EXTENSIONS: frozenset[str] = frozenset({".svg"})

# Corner / anchor placement presets for the overlay geometry.
POSITION_PRESETS: frozenset[str] = frozenset(
    {"top_left", "top_right", "bottom_left", "bottom_right", "center", "full"}
)

# qtblend is the compositing transform that both positions the still and honours
# its alpha (render-proof verified). ``kdenlive_id`` keeps the filter
# Kdenlive-consistent; melt ignores the unknown property.
TRANSFORM_SERVICE = "qtblend"
TRANSFORM_KDENLIVE_ID = "qtblend"


def is_supported_image(image_path: str | Path) -> bool:
    """True when *image_path*'s extension is a still the producer can load."""
    return Path(image_path).suffix.lower() in IMAGE_EXTENSIONS


def is_svg(image_path: str | Path) -> bool:
    """True when *image_path* is an SVG (rasterised by qimage/pixbuf)."""
    return Path(image_path).suffix.lower() in SVG_EXTENSIONS


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:24] or "image"


def image_producer_id(image_path: str | Path) -> str:
    """Deterministic producer id from a media path (``image_<stem>_<hash>``)."""
    stem = _slug(Path(image_path).stem)
    digest = hashlib.md5(str(image_path).encode()).hexdigest()[:6]
    return f"image_{stem}_{digest}"


def image_producer_properties(
    image_path: str | Path,
    length_frames: int,
    clipname: str | None = None,
) -> dict[str, str]:
    """Assemble the MLT ``<producer>`` property dict for a still image.

    ``length`` must be >= the entry out-point so the still holds for the whole
    placement; ``ttl`` (frames-per-image) only matters for image *sequences* but
    is set equal to ``length`` so a single still never advances.
    """
    if length_frames <= 0:
        raise ValueError(f"length_frames must be > 0; got {length_frames}")
    resource = str(image_path)
    props = {
        "mlt_service": IMAGE_PRODUCER_SERVICE,
        "resource": resource,
        "length": str(length_frames),
        "ttl": str(length_frames),
    }
    props["kdenlive:clipname"] = (clipname or Path(resource).name)[:60]
    return props


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------

def position_rect(
    preset: str,
    width: int,
    height: int,
    scale: float = 0.15,
    margin: float = 0.05,
    aspect: float | None = None,
) -> tuple[int, int, int, int]:
    """Return the ``(x, y, w, h)`` pixel rectangle for a placement *preset*.

    * ``full`` -> the whole frame.
    * corner / ``center`` -> a box ``scale`` of the frame width, inset by
      ``margin`` (fraction of each edge).  When *aspect* (w/h) is given the box
      height is derived from it so the still keeps its proportions; otherwise the
      box height is ``scale`` of the frame height.
    """
    w, h = int(width), int(height)
    if preset == "full":
        return (0, 0, w, h)
    if preset not in POSITION_PRESETS:
        raise ValueError(
            f"unknown position preset {preset!r}; valid: {sorted(POSITION_PRESETS)}"
        )
    if not 0.0 < scale <= 1.0:
        raise ValueError(f"scale must be in (0.0, 1.0]; got {scale}")
    if not 0.0 <= margin < 0.5:
        raise ValueError(f"margin must be in [0.0, 0.5); got {margin}")

    box_w = max(1, round(w * scale))
    if aspect and aspect > 0:
        box_h = max(1, round(box_w / aspect))
    else:
        box_h = max(1, round(h * scale))
    mx = round(w * margin)
    my = round(h * margin)

    coords = {
        "top_left": (mx, my),
        "top_right": (w - box_w - mx, my),
        "bottom_left": (mx, h - box_h - my),
        "bottom_right": (w - box_w - mx, h - box_h - my),
        "center": ((w - box_w) // 2, (h - box_h) // 2),
    }
    x, y = coords[preset]
    return (int(x), int(y), int(box_w), int(box_h))


def rect_to_string(
    rect: tuple[int, int, int, int], opacity: float = 1.0
) -> str:
    """Format a rect + opacity as the qtblend ``"x y w h opacity"`` string."""
    x, y, w, h = rect
    return (
        f"{int(x)} {int(y)} {int(w)} {int(h)} {_format_scalar(opacity)}"
    )


def resolve_rect(
    rect_arg: str,
    width: int,
    height: int,
    scale: float = 0.15,
    margin: float = 0.05,
    aspect: float | None = None,
) -> tuple[int, int, int, int] | None:
    """Resolve the ``rect`` tool argument to a pixel rectangle, or ``None``.

    ``rect_arg`` may be:

    * empty -> ``None`` (no geometry; the producer fills the frame).
    * a placement preset (``top_left`` / ``bottom_right`` / ``center`` /
      ``full`` / ...) -> computed from the profile via :func:`position_rect`.
    * an explicit ``"x y w h"`` (or comma-separated) rectangle -> parsed as-is.
    """
    s = (rect_arg or "").strip()
    if not s:
        return None
    if s in POSITION_PRESETS:
        return position_rect(s, width, height, scale=scale, margin=margin, aspect=aspect)
    parts = [p for p in re.split(r"[,\s]+", s) if p]
    if len(parts) == 4:
        try:
            x, y, w, h = (int(round(float(p))) for p in parts)
        except ValueError as exc:
            raise ValueError(f"invalid rect {rect_arg!r}: {exc}") from exc
        return (x, y, w, h)
    raise ValueError(
        f"rect {rect_arg!r} must be empty, a preset "
        f"({sorted(POSITION_PRESETS)}), or 'x y w h'"
    )


# ---------------------------------------------------------------------------
# Transform filter (position / scale / opacity / fades) as a qtblend clip filter
# ---------------------------------------------------------------------------

def overlay_rect_value(
    rect: tuple[int, int, int, int],
    opacity: float,
    fade_in_frames: int,
    fade_out_frames: int,
    duration_frames: int,
    fps: float,
) -> str:
    """Return the qtblend ``rect`` value: static string, or a keyframe ramp.

    With no fades the rect is a single ``"x y w h opacity"`` string.  With
    fade-in and/or fade-out the geometry is held constant and only the opacity
    ramps (0 -> ``opacity`` on the way in, ``opacity`` -> 0 on the way out),
    baked into a keyframed rect animation string.
    """
    if not 0.0 <= opacity <= 1.0:
        raise ValueError(f"opacity must be in [0.0, 1.0]; got {opacity}")
    if fade_in_frames < 0 or fade_out_frames < 0:
        raise ValueError("fade frames must be >= 0")
    x, y, w, h = rect
    if fade_in_frames == 0 and fade_out_frames == 0:
        return rect_to_string(rect, opacity)

    raw = build_fade_keyframes(
        fade_in_frames=fade_in_frames,
        fade_out_frames=fade_out_frames,
        clip_duration_frames=duration_frames,
        fps=fps,
    )
    rekeyed = [
        Keyframe(
            frame=kf.frame,
            value=(x, y, w, h, float(kf.value[4]) * opacity),
            easing=kf.easing,
        )
        for kf in raw
    ]
    return build_keyframe_string("rect", rekeyed, fps=fps)


def build_transform_filter_xml(
    track: int,
    clip: int,
    rect_value: str,
    kdenlive_id: str = TRANSFORM_KDENLIVE_ID,
) -> str:
    """Build the qtblend ``<filter>`` XML that positions the overlay still.

    The ``track``/``clip_index`` association attributes are the ones the
    serializer reads to relocate the filter *inside* the target clip ``<entry>``
    (§1.1 placement); they are stripped before MLT sees the element.
    """
    root = ET.Element(
        "filter",
        {"mlt_service": TRANSFORM_SERVICE, "track": str(track), "clip_index": str(clip)},
    )
    ET.SubElement(root, "property", {"name": "mlt_service"}).text = TRANSFORM_SERVICE
    if kdenlive_id:
        ET.SubElement(root, "property", {"name": "kdenlive_id"}).text = kdenlive_id
    ET.SubElement(root, "property", {"name": "rect"}).text = rect_value
    # compositing 0 == source-over: the still paints over the layers below while
    # its own alpha is preserved.
    ET.SubElement(root, "property", {"name": "compositing"}).text = "0"
    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Timeline helpers
# ---------------------------------------------------------------------------

def _entry_len(entry) -> int:
    return max(0, entry.out_point - entry.in_point + 1)


def video_playlists(project) -> list:
    """Return the project's video playlists (mirrors the titles/overlay tools)."""
    audio_ids = {t.id for t in project.tracks if t.track_type == "audio"}
    return [p for p in project.playlists if p.id not in audio_ids]


def timeline_duration_frames(project) -> int:
    """Longest video-track length in frames (for full-duration watermarks)."""
    vps = video_playlists(project)
    return max(
        (sum(_entry_len(e) for e in pl.entries) for pl in vps),
        default=0,
    )


def image_aspect(image_path: str | Path) -> float | None:
    """Best-effort intrinsic aspect ratio (w/h) of *image_path*, or ``None``.

    Uses Pillow when available (an optional dep) so the watermark keeps the
    logo's proportions; returns ``None`` when Pillow is absent or the file
    cannot be read (callers fall back to a square box).
    """
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(image_path) as im:
            w, h = im.size
        if w > 0 and h > 0:
            return float(w) / float(h)
    except Exception:
        return None
    return None
