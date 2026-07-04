"""Kdenlive title (``kdenlivetitle``) XML builder.

Pure functions that turn a :class:`TitleSpec` into a ``<kdenlivetitle>`` XML
document — the same payload Kdenlive stores in a producer's ``xmldata``
property.  Nothing here touches the filesystem or the project model; the bundle
tool in ``edit_mcp/server/bundles/titles.py`` wires the output into a project.

Geometry is **profile-aware**: every position, font size and safe-area margin is
derived from the target ``width``/``height``/``fps`` carried on the spec, so the
same template renders correctly at 1080p, 4K and 9:16 vertical without any
hardcoded pixel constants.

Colours are expressed the way the Kdenlive titler expects — ``"R,G,B,A"`` with
each channel 0-255.  :func:`normalize_color` accepts ``"#RRGGBB"``,
``"#RRGGBBAA"`` or an already-normalised ``"r,g,b,a"`` string.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from pydantic import BaseModel, Field

from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames

# Qt::Alignment flag ints as stored by the Kdenlive titler.
_ALIGN_FLAGS = {"left": "0", "center": "4", "right": "2"}

_IDENTITY_TRANSFORM = "1,0,0,0,1,0,0,0,1"


class TitleSpec(BaseModel):
    """Declarative description of a single on-screen title card."""

    text: str
    subtitle: str = ""

    # Target profile — drives all geometry.  Parametrised, never hardcoded.
    width: int = 1920
    height: int = 1080
    fps: float = 25.0

    duration_seconds: float = 4.0

    # Typography ---------------------------------------------------------
    font_family: str = "DejaVu Sans"
    # Absolute pixel sizes take priority; otherwise sizes scale with height.
    title_font_size: int | None = None
    subtitle_font_size: int | None = None
    title_font_scale: float = 0.06
    subtitle_font_scale: float = 0.033
    font_color: str = "#FFFFFF"
    subtitle_color: str = "#E6E6E6"
    outline_color: str = "#000000"
    outline_width: int = 0
    align: str = "left"  # left | center | right

    # Layout -------------------------------------------------------------
    anchor: str = "lower-third"  # lower-third | center | top | bottom
    safe_margin: float = 0.1  # title-safe fraction of each edge
    background: bool = True
    background_color: str = "#000000B4"  # rgba; B4 == 180 alpha
    background_padding: int | None = None

    model_config = {"extra": "ignore"}


def normalize_color(value: str) -> str:
    """Return an ``"R,G,B,A"`` colour string for the Kdenlive titler.

    Accepts ``#RRGGBB``, ``#RRGGBBAA`` or a pre-formatted ``r,g,b,a`` string.
    """
    value = value.strip()
    if value.startswith("#"):
        hexs = value[1:]
        if len(hexs) == 6:
            hexs += "FF"
        if len(hexs) != 8:
            raise ValueError(f"Invalid hex colour: {value!r}")
        r, g, b, a = (int(hexs[i : i + 2], 16) for i in (0, 2, 4, 6))
        return f"{r},{g},{b},{a}"
    parts = [p.strip() for p in value.split(",")]
    if len(parts) == 3:
        parts.append("255")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        raise ValueError(f"Invalid colour: {value!r}")
    return ",".join(parts)


def duration_frames(spec: TitleSpec) -> int:
    """Title length in frames (>= 1) at the spec's fps."""
    fps = spec.fps or 25.0
    return max(1, seconds_to_frames(spec.duration_seconds, fps))


def compute_layout(spec: TitleSpec) -> dict:
    """Compute all geometry for *spec* in profile pixels.

    Returns a dict with margins, font sizes, and the pixel rectangles for the
    title item, subtitle item and background rect.  Exposed separately from
    :func:`build_title_xml` so the safe-area math is directly unit-testable.
    """
    w, h = spec.width, spec.height
    margin = max(0.0, min(0.45, spec.safe_margin))
    mx = round(w * margin)
    my = round(h * margin)

    title_size = spec.title_font_size or max(12, round(h * spec.title_font_scale))
    sub_size = spec.subtitle_font_size or max(10, round(h * spec.subtitle_font_scale))

    has_sub = bool(spec.subtitle)
    content_w = max(1, w - 2 * mx)
    title_box_h = round(title_size * 1.35)
    sub_box_h = round(sub_size * 1.35) if has_sub else 0
    gap = round(title_size * 0.15) if has_sub else 0
    block_h = title_box_h + gap + sub_box_h

    # Highest legal top so the whole block stays inside the safe area.
    top_limit = max(my, h - my - block_h)
    if spec.anchor == "top":
        block_top = my
    elif spec.anchor == "center":
        block_top = round((h - block_h) / 2)
    elif spec.anchor == "bottom":
        block_top = top_limit
    else:  # lower-third: seated in the lower band but never past the safe line
        block_top = min(round(h * 0.72), top_limit)
    block_top = max(my, min(block_top, top_limit))

    pad = spec.background_padding if spec.background_padding is not None else round(title_size * 0.28)
    bg_x = max(0, mx - pad)
    bg_y = max(0, block_top - pad)
    bg_w = min(w - bg_x, content_w + 2 * pad)
    bg_h = min(h - bg_y, block_h + 2 * pad)

    return {
        "width": w,
        "height": h,
        "margin_x": mx,
        "margin_y": my,
        "content_width": content_w,
        "title_size": title_size,
        "subtitle_size": sub_size,
        "title_box": (mx, block_top, content_w, title_box_h),
        "subtitle_box": (
            (mx, block_top + title_box_h + gap, content_w, sub_box_h)
            if has_sub
            else None
        ),
        "background_rect": (bg_x, bg_y, bg_w, bg_h),
        "block": (mx, block_top, content_w, block_h),
    }


def _text_item(
    z: int,
    box: tuple[int, int, int, int],
    text: str,
    *,
    font: str,
    size: int,
    color: str,
    outline_color: str,
    outline_width: int,
    align: str,
) -> ET.Element:
    x, y, box_w, box_h = box
    item = ET.Element("item", {"type": "QGraphicsTextItem", "z-index": str(z)})
    pos = ET.SubElement(item, "position", {"x": str(x), "y": str(y)})
    ET.SubElement(pos, "transform").text = _IDENTITY_TRANSFORM
    content = ET.SubElement(
        item,
        "content",
        {
            "font": font,
            "font-pixel-size": str(size),
            "font-color": normalize_color(color),
            "font-outline": str(outline_width),
            "font-outline-color": normalize_color(outline_color),
            "alignment": _ALIGN_FLAGS.get(align, "0"),
            "box-width": str(box_w),
            "box-height": str(box_h),
        },
    )
    content.text = text
    return item


def _rect_item(z: int, rect: tuple[int, int, int, int], color: str) -> ET.Element:
    x, y, rw, rh = rect
    item = ET.Element("item", {"type": "QGraphicsRectItem", "z-index": str(z)})
    pos = ET.SubElement(item, "position", {"x": str(x), "y": str(y)})
    ET.SubElement(pos, "transform").text = _IDENTITY_TRANSFORM
    ET.SubElement(
        item,
        "content",
        {
            "rect": f"0,0,{rw},{rh}",
            "brushcolor": normalize_color(color),
            "pencolor": "0,0,0,0",
            "penwidth": "0",
        },
    )
    return item


def build_title_xml(spec: TitleSpec) -> str:
    """Build the ``<kdenlivetitle>`` XML document for *spec*.

    The returned string is a self-contained title document ready to be stored
    in a producer's ``xmldata`` property.  Item z-order is background rect (0),
    title (1), subtitle (2).  The document background is fully transparent so
    the card composites over whatever track sits beneath it.
    """
    layout = compute_layout(spec)
    frames = duration_frames(spec)

    root = ET.Element(
        "kdenlivetitle",
        {
            "duration": str(frames),
            "LC_NUMERIC": "C",
            "width": str(spec.width),
            "height": str(spec.height),
            "out": str(frames - 1),
        },
    )

    z = 0
    if spec.background:
        root.append(_rect_item(z, layout["background_rect"], spec.background_color))
        z += 1

    root.append(
        _text_item(
            z,
            layout["title_box"],
            spec.text,
            font=spec.font_family,
            size=layout["title_size"],
            color=spec.font_color,
            outline_color=spec.outline_color,
            outline_width=spec.outline_width,
            align=spec.align,
        )
    )
    z += 1

    if layout["subtitle_box"] is not None:
        root.append(
            _text_item(
                z,
                layout["subtitle_box"],
                spec.subtitle,
                font=spec.font_family,
                size=layout["subtitle_size"],
                color=spec.subtitle_color,
                outline_color=spec.outline_color,
                outline_width=spec.outline_width,
                align=spec.align,
            )
        )

    ET.SubElement(root, "startviewport", {"rect": f"0,0,{spec.width},{spec.height}"})
    ET.SubElement(root, "endviewport", {"rect": f"0,0,{spec.width},{spec.height}"})
    ET.SubElement(root, "background", {"color": "0,0,0,0"})

    return ET.tostring(root, encoding="unicode")
