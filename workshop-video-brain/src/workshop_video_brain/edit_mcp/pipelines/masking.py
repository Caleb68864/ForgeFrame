"""Mask pipeline: shapes, MLT XML builders, and data models.

Pure-logic module. No filesystem I/O, no MCP, no KdenliveProject mutation.
Follows the ``pipelines/stack_ops.py`` pattern: module-level regex/constants,
typed helpers, thorough docstrings, no side effects.

See ``docs/specs/2026-04-13-masking.md`` (master spec) and
``docs/specs/2026-04-13-masking/sub-spec-1-mask-pipeline.md`` (phase spec).

Kdenlive schema corrections (verified via ``/usr/share/kdenlive/effects/rotoscoping.xml``):

* Rotoscoping MLT service is ``rotoscoping``. Spline property is named
  ``spline`` (type ``roto-spline``). Feather passes property is
  ``feather_passes`` (NOT ``passes``). Valid ``alpha_operation`` values are
  ``clear | max | min | add | sub``.
* Basic chroma key uses MLT service ``chroma`` with properties ``key`` and
  ``variance``. No ``blend`` property on this filter.
* Advanced chroma key uses MLT service ``avfilter.hsvkey`` with properties
  ``av.hue``, ``av.sat``, ``av.val``, ``av.similarity``, ``av.blend``.
* Object mask wraps ``frei0r.alpha0ps_alphaspot`` (stock shape-into-alpha).

The rotoscoping filter produced here is the PLAIN form. Sub-Spec 2's
``apply_mask_to_effect`` converts it to ``mask_start-rotoscoping`` with
``filter.*`` prefixed properties when routing alpha onto another effect.

Alpha routing (Sub-Spec 2)
--------------------------

Kdenlive does NOT route mask alpha via a single property on the target
filter. Instead it uses a three-filter sandwich:

* ``mask_start-<variant>`` -- snapshots the incoming frame and embeds the
  inner mask filter's parameters via ``filter.*`` prefixed properties.
* one or more intermediate filters -- the effects to be masked.
* ``mask_apply`` -- composites the masked result back over the snapshot
  using the ``qtblend`` transition.

``apply_mask_to_effect`` performs this wrap in place: it converts the
plain rotoscoping / object_mask filter at ``mask_effect_index`` into the
corresponding ``mask_start`` form and inserts a ``mask_apply`` filter
immediately after ``target_effect_index``. Effects appended AFTER the
``mask_apply`` filter are OUTSIDE the sandwich and are NOT masked.

See ``docs/specs/2026-04-13-masking/sub-spec-2-alpha-routing.md`` for
the escalation trail that confirmed this behavior.
"""
from __future__ import annotations

import colorsys
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Normalization table for alpha_operation aliases → canonical MLT tokens.
ALPHA_OPERATION_TO_MLT: dict[str, str] = {
    "clear": "clear",
    "max": "max",
    "min": "min",
    "add": "add",
    "sub": "sub",
    # Legacy / display-name aliases accepted by this builder, normalized to
    # the five MLT-canonical tokens above.
    "write_on_clear": "clear",
    "maximum": "max",
    "minimum": "min",
    "subtract": "sub",
}

_COLOR_HEX_RE = re.compile(r"^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _check_normalized(value: float, label: str) -> None:
    """Raise ``ValueError`` if ``value`` is outside ``[0, 1]``."""
    if value < 0.0 or value > 1.0:
        raise ValueError(f"{label}={value} out of [0,1]")


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

class MaskShape(BaseModel):
    """Shape descriptor sampled into a normalized point sequence."""

    kind: Literal["rect", "ellipse", "polygon"]
    bounds: tuple[float, float, float, float] = (0.0, 0.0, 1.0, 1.0)
    points: tuple[tuple[float, float], ...] = ()
    sample_count: int = Field(default=32, ge=4)


class MaskParams(BaseModel):
    """Rotoscoping mask parameters, as consumed by ``build_rotoscoping_xml``."""

    points: tuple[tuple[float, float], ...]
    feather: int = Field(default=0, ge=0, le=500)
    feather_passes: int = Field(default=1, ge=1, le=20)
    alpha_operation: Literal["clear", "max", "min", "add", "sub"] = "add"

    @field_validator("points")
    @classmethod
    def _validate_points(
        cls, v: tuple[tuple[float, float], ...]
    ) -> tuple[tuple[float, float], ...]:
        for (x, y) in v:
            _check_normalized(x, "point.x")
            _check_normalized(y, "point.y")
        return v


# ---------------------------------------------------------------------------
# Shape sampling
# ---------------------------------------------------------------------------

def shape_to_points(shape: MaskShape) -> tuple[tuple[float, float], ...]:
    """Convert a :class:`MaskShape` to a normalized point sequence.

    * ``rect`` → 4 corners clockwise from top-left.
    * ``ellipse`` → ``sample_count`` points, first at 3 o'clock.
    * ``polygon`` → passthrough (requires at least 3 points).
    """
    x, y, w, h = shape.bounds
    if shape.kind == "rect":
        corners = ((x, y), (x + w, y), (x + w, y + h), (x, y + h))
        for (cx, cy) in corners:
            _check_normalized(cx, "bounds.x")
            _check_normalized(cy, "bounds.y")
        return corners

    if shape.kind == "ellipse":
        n = shape.sample_count
        if n < 4:
            raise ValueError(
                f"ellipse sample_count={n} must be >= 4"
            )
        cx = x + w / 2.0
        cy = y + h / 2.0
        rx = w / 2.0
        ry = h / 2.0
        pts: list[tuple[float, float]] = []
        for i in range(n):
            theta = 2.0 * math.pi * i / n
            px = cx + rx * math.cos(theta)
            py = cy + ry * math.sin(theta)
            _check_normalized(px, "ellipse.x")
            _check_normalized(py, "ellipse.y")
            pts.append((px, py))
        return tuple(pts)

    # polygon
    if len(shape.points) < 3:
        raise ValueError("polygon requires at least 3 points")
    for (px, py) in shape.points:
        _check_normalized(px, "polygon.x")
        _check_normalized(py, "polygon.y")
    return tuple(shape.points)


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

def color_to_mlt_hex(value: str | int) -> str:
    """Convert a color to MLT's ``0xRRGGBBAA`` string form.

    Accepts ``#RRGGBB`` (alpha defaulted to ``ff``), ``#RRGGBBAA``, or an
    integer that is treated as a 32-bit RGBA value.
    """
    if isinstance(value, bool):  # bool is subclass of int -- reject it explicitly
        raise ValueError(
            f"invalid color: {value!r} -- expected #RRGGBB, #RRGGBBAA, or int"
        )
    if isinstance(value, int):
        if value < 0 or value > 0xFFFFFFFF:
            raise ValueError(
                f"invalid color: {value!r} -- expected 32-bit int"
            )
        return f"0x{value:08x}"
    if isinstance(value, str):
        m = _COLOR_HEX_RE.match(value)
        if not m:
            raise ValueError(
                f"invalid color: {value!r} -- expected #RRGGBB, #RRGGBBAA, or int"
            )
        hexpart = m.group(1).lower()
        if len(hexpart) == 6:
            hexpart += "ff"
        return f"0x{hexpart}"
    raise ValueError(
        f"invalid color: {value!r} -- expected #RRGGBB, #RRGGBBAA, or int"
    )


# ---------------------------------------------------------------------------
# XML building helpers
# ---------------------------------------------------------------------------

def _make_filter(
    mlt_service: str,
    clip_ref: tuple[int, int],
    props: list[tuple[str, str]],
) -> str:
    track, clip = clip_ref
    root = ET.Element(
        "filter",
        {
            "mlt_service": mlt_service,
            "track": str(track),
            "clip_index": str(clip),
        },
    )
    for name, text in props:
        el = ET.SubElement(root, "property", {"name": name})
        el.text = text
    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Rotoscoping
# ---------------------------------------------------------------------------

def _spline_json(points: tuple[tuple[float, float], ...]) -> str:
    """Serialize a point list to Kdenlive's ``roto-spline`` format.

    v1 emits a single keyframe at frame 0 with linear (handle == point)
    connections: ``{"0": [[[x,y],[x,y],[x,y]], ...]}``.
    """
    frame0 = [[[x, y], [x, y], [x, y]] for (x, y) in points]
    return json.dumps({"0": frame0})


def build_rotoscoping_xml(
    clip_ref: tuple[int, int], mask: MaskParams
) -> str:
    """Emit the plain ``rotoscoping`` filter XML for a clip.

    Sub-Spec 2's alpha-routing pass will later wrap this into the
    ``mask_start-rotoscoping`` form with ``filter.*`` prefixed properties.
    """
    normalized = ALPHA_OPERATION_TO_MLT.get(mask.alpha_operation)
    if normalized is None:
        raise ValueError(
            f"unknown alpha_operation: {mask.alpha_operation!r}"
        )
    spline = _spline_json(mask.points)
    props: list[tuple[str, str]] = [
        ("mlt_service", "rotoscoping"),
        ("kdenlive_id", "rotoscoping"),
        ("mode", "alpha"),
        ("alpha_operation", normalized),
        ("invert", "0"),
        ("feather", str(mask.feather)),
        ("feather_passes", str(mask.feather_passes)),
        ("spline", spline),
    ]
    return _make_filter("rotoscoping", clip_ref, props)


# ---------------------------------------------------------------------------
# Object mask (frei0r.alpha0ps_alphaspot surrogate)
# ---------------------------------------------------------------------------

def build_object_mask_xml(
    clip_ref: tuple[int, int], params: dict
) -> str:
    """Build an ``object_mask`` filter by wrapping ``frei0r.alpha0ps_alphaspot``.

    Kdenlive ships no AI object-detector; this builder emulates
    ``object_mask`` via the stock alpha-spot shape filter. See
    ``docs/specs/2026-04-13-masking/index.md`` -- Object mask section.
    """
    shape = int(params.get("shape", 0))
    pos_x = float(params.get("position_x", 0.5))
    pos_y = float(params.get("position_y", 0.5))
    size_x = float(params.get("size_x", 0.5))
    size_y = float(params.get("size_y", 0.5))
    tilt = float(params.get("tilt", 0.5))
    alpha_op = int(params.get("alpha_operation", 0))
    threshold = float(params.get("threshold", 0.5))
    enabled = bool(params.get("enabled", True))

    props: list[tuple[str, str]] = [
        ("mlt_service", "frei0r.alpha0ps_alphaspot"),
        ("kdenlive_id", "frei0r_alpha0ps_alphaspot"),
        ("0", str(shape)),
        ("1", str(pos_x)),
        ("2", str(pos_y)),
        ("3", str(size_x)),
        ("4", str(size_y)),
        ("5", str(tilt)),
        ("6", str(alpha_op)),
        ("7", str(threshold)),
    ]
    if not enabled:
        props.append(("disable", "1"))
    return _make_filter("frei0r.alpha0ps_alphaspot", clip_ref, props)


# ---------------------------------------------------------------------------
# Chroma key -- basic
# ---------------------------------------------------------------------------

def build_chroma_key_xml(
    clip_ref: tuple[int, int],
    color: str,
    tolerance: float,
    blend: float = 0.0,
) -> str:
    """Build a basic ``chroma`` MLT filter.

    The ``blend`` argument is accepted for API symmetry but ignored; the
    basic chroma filter has no blend property. A warning is logged if a
    non-zero value is supplied.
    """
    if blend:
        logger.warning(
            "build_chroma_key_xml: blend=%s ignored (basic chroma has no blend property)",
            blend,
        )
    key_hex = color_to_mlt_hex(color)
    props: list[tuple[str, str]] = [
        ("mlt_service", "chroma"),
        ("kdenlive_id", "chroma"),
        ("key", key_hex),
        ("variance", f"{tolerance}"),
    ]
    return _make_filter("chroma", clip_ref, props)


# ---------------------------------------------------------------------------
# Chroma key -- advanced (avfilter.hsvkey)
# ---------------------------------------------------------------------------

def _hex_to_hsv(color: str) -> tuple[float, float, float]:
    """Convert ``#RRGGBB[AA]`` to HSV with H in degrees (0-360)."""
    m = _COLOR_HEX_RE.match(color)
    if not m:
        raise ValueError(
            f"invalid color: {color!r} -- expected #RRGGBB or #RRGGBBAA"
        )
    hexpart = m.group(1)
    r = int(hexpart[0:2], 16) / 255.0
    g = int(hexpart[2:4], 16) / 255.0
    b = int(hexpart[4:6], 16) / 255.0
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return (h * 360.0, s, v)


def build_chroma_key_advanced_xml(
    clip_ref: tuple[int, int],
    color: str,
    tolerance_near: float,
    tolerance_far: float,
    edge_smooth: float = 0.0,
    spill_suppression: float = 0.0,
) -> str:
    """Build an ``avfilter.hsvkey`` advanced chroma filter."""
    if tolerance_far < tolerance_near:
        raise ValueError("tolerance_far must be >= tolerance_near")
    hue, sat, val = _hex_to_hsv(color)
    props: list[tuple[str, str]] = [
        ("mlt_service", "avfilter.hsvkey"),
        ("kdenlive_id", "avfilter_hsvkey"),
        ("av.hue", f"{hue}"),
        ("av.sat", f"{sat}"),
        ("av.val", f"{val}"),
        ("av.similarity", f"{tolerance_near}"),
        ("av.blend", f"{edge_smooth}"),
    ]
    if spill_suppression > 0:
        props.append(("av.spill_suppression", f"{spill_suppression}"))
    return _make_filter("avfilter.hsvkey", clip_ref, props)


# ---------------------------------------------------------------------------
# Alpha routing (Sub-Spec 2): mask_start / mask_apply sandwich
# ---------------------------------------------------------------------------

MASK_START_SERVICES: tuple[str, ...] = ("mask_start",)
MASK_APPLY_SERVICE: str = "mask_apply"
MASK_CAPABLE_INNER_SERVICES: tuple[str, ...] = (
    "rotoscoping",
    "frei0r.alpha0ps_alphaspot",
    "shape",
)

# Property names on the plain rotoscoping filter that should be preserved
# (with a ``filter.`` prefix) when converting to the ``mask_start`` sandwich.
_ROTOSCOPING_INNER_PROPS: tuple[str, ...] = (
    "mode",
    "alpha_operation",
    "invert",
    "feather",
    "feather_passes",
    "spline",
)

# Property names on the object_mask (frei0r.alpha0ps_alphaspot) filter that
# should be preserved (with a ``filter.`` prefix) when converting.
_OBJECT_MASK_INNER_PROPS: tuple[str, ...] = (
    "0", "1", "2", "3", "4", "5", "6", "7",
)


def build_mask_start_rotoscoping_xml(
    clip_ref: tuple[int, int], mask: MaskParams
) -> str:
    """Emit a ``mask_start-rotoscoping`` filter (sandwich opener).

    Wraps a rotoscoping mask's parameters via ``filter.*`` prefixed
    properties, matching ``/usr/share/kdenlive/effects/mask_start_rotoscoping.xml``.
    """
    normalized = ALPHA_OPERATION_TO_MLT.get(mask.alpha_operation)
    if normalized is None:
        raise ValueError(
            f"unknown alpha_operation: {mask.alpha_operation!r}"
        )
    spline = _spline_json(mask.points)
    props: list[tuple[str, str]] = [
        ("mlt_service", "mask_start"),
        ("kdenlive_id", "mask_start-rotoscoping"),
        ("filter", "rotoscoping"),
        ("filter.mode", "alpha"),
        ("filter.alpha_operation", normalized),
        ("filter.invert", "0"),
        ("filter.feather", str(mask.feather)),
        ("filter.feather_passes", str(mask.feather_passes)),
        ("filter.spline", spline),
    ]
    return _make_filter("mask_start", clip_ref, props)


def build_mask_apply_xml(clip_ref: tuple[int, int]) -> str:
    """Emit a ``mask_apply`` filter (sandwich closer).

    Composites the masked result back via a ``qtblend`` transition.
    """
    props: list[tuple[str, str]] = [
        ("mlt_service", "mask_apply"),
        ("kdenlive_id", "mask_apply"),
        ("transition", "qtblend"),
    ]
    return _make_filter("mask_apply", clip_ref, props)


def _build_mask_start_from_existing(
    clip_ref: tuple[int, int],
    inner_service: str,
    existing_props: dict[str, str],
) -> str:
    """Build a ``mask_start`` filter by promoting an existing plain filter's
    properties to ``filter.*`` prefixed form.

    ``inner_service`` is the MLT service of the plain inner filter
    (``rotoscoping`` or ``frei0r.alpha0ps_alphaspot``).
    """
    if inner_service == "rotoscoping":
        inner_keys = _ROTOSCOPING_INNER_PROPS
        kdenlive_id = "mask_start-rotoscoping"
        filter_value = "rotoscoping"
    elif inner_service in ("frei0r.alpha0ps_alphaspot", "shape"):
        inner_keys = _OBJECT_MASK_INNER_PROPS
        kdenlive_id = "mask_start-shape"
        filter_value = inner_service
    else:
        raise ValueError(
            f"cannot convert service {inner_service!r} to mask_start form"
        )

    props: list[tuple[str, str]] = [
        ("mlt_service", "mask_start"),
        ("kdenlive_id", kdenlive_id),
        ("filter", filter_value),
    ]
    for key in inner_keys:
        if key in existing_props:
            props.append((f"filter.{key}", existing_props[key]))
    return _make_filter("mask_start", clip_ref, props)


def _rewrite_mask_to_mask_start(
    project,
    clip_ref: tuple[int, int],
    mask_effect_index: int,
    mask_service: str,
) -> None:
    """In-place conversion: replace the plain mask filter at
    ``mask_effect_index`` with its ``mask_start`` sandwich-opener form,
    promoting its properties to ``filter.*`` prefixed names.
    """
    # Imported here to avoid a module-load cycle with the patcher module.
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher

    filters = patcher.list_effects(project, clip_ref)
    existing_props = dict(filters[mask_effect_index]["properties"])
    new_xml = _build_mask_start_from_existing(
        clip_ref, mask_service, existing_props
    )
    patcher.remove_effect(project, clip_ref, mask_effect_index)
    patcher.insert_effect_xml(project, clip_ref, new_xml, mask_effect_index)


def _insert_mask_apply(
    project,
    clip_ref: tuple[int, int],
    position: int,
) -> None:
    """Insert a ``mask_apply`` filter at ``position`` in the clip's stack."""
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher
    patcher.insert_effect_xml(
        project, clip_ref, build_mask_apply_xml(clip_ref), position
    )


def apply_mask_to_effect(
    project,
    clip_ref: tuple[int, int],
    mask_effect_index: int,
    target_effect_index: int,
) -> dict:
    """Wrap a target filter with the mask_start / mask_apply sandwich.

    Converts the plain rotoscoping / object_mask filter at
    ``mask_effect_index`` into its ``mask_start`` form (if not already),
    ensures the mask precedes the target in the stack (reordering if
    needed), and inserts a ``mask_apply`` filter immediately after the
    target (unless one already exists downstream).

    Returns a dict:

    * ``reordered`` -- True if the stack was reordered.
    * ``mask_effect_index`` -- final stack index of the mask filter.
    * ``target_effect_index`` -- final stack index of the target filter.
    * ``mask_apply_effect_index`` -- final stack index of the mask_apply
      filter.
    * ``converted_to_sandwich`` -- True if this call converted a plain
      mask filter to its ``mask_start`` form (i.e., first wrap).

    Raises ``IndexError`` if either index is out of range. Raises
    ``ValueError`` if the filter at ``mask_effect_index`` is not a
    recognized mask filter.
    """
    from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher

    filters = patcher.list_effects(project, clip_ref)
    n = len(filters)
    if mask_effect_index < 0 or mask_effect_index >= n:
        raise IndexError(
            f"mask_effect_index {mask_effect_index} out of range "
            f"(clip has {n} filters)"
        )
    if target_effect_index < 0 or target_effect_index >= n:
        raise IndexError(
            f"target_effect_index {target_effect_index} out of range "
            f"(clip has {n} filters)"
        )

    mask_filter = filters[mask_effect_index]
    mask_service = mask_filter["mlt_service"]

    valid_services = ("mask_start", *MASK_CAPABLE_INNER_SERVICES)
    if mask_service not in valid_services:
        raise ValueError(
            f"effect at index {mask_effect_index} has service "
            f"{mask_service!r}; expected one of {valid_services}"
        )

    # Step 1: conversion. Plain filter -> mask_start form.
    converted = False
    if mask_service != "mask_start":
        _rewrite_mask_to_mask_start(
            project, clip_ref, mask_effect_index, mask_service
        )
        converted = True

    # Step 2: reorder if mask index is not above target index.
    reordered = False
    # Refresh after potential conversion (indices unchanged, but safe).
    filters = patcher.list_effects(project, clip_ref)
    if mask_effect_index >= target_effect_index:
        patcher.reorder_effects(
            project, clip_ref,
            from_index=mask_effect_index,
            to_index=target_effect_index,
        )
        reordered = True
        # After moving mask to target's slot, target shifts up by one
        # (mask was below or at target).
        new_mask_index = target_effect_index
        new_target_index = target_effect_index + 1
    else:
        new_mask_index = mask_effect_index
        new_target_index = target_effect_index

    # Step 3: ensure a mask_apply exists downstream of the target.
    filters = patcher.list_effects(project, clip_ref)
    mask_apply_index: int | None = None
    for i, f in enumerate(filters):
        if i > new_target_index and f["mlt_service"] == MASK_APPLY_SERVICE:
            mask_apply_index = i
            break

    if mask_apply_index is None:
        _insert_mask_apply(project, clip_ref, new_target_index + 1)
        mask_apply_index = new_target_index + 1

    return {
        "reordered": reordered,
        "mask_effect_index": new_mask_index,
        "target_effect_index": new_target_index,
        "mask_apply_effect_index": mask_apply_index,
        "converted_to_sandwich": converted,
    }
