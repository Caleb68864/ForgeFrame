"""Shape Alpha pipeline: consume an external matte/mask *file* as a clip's
alpha channel.

Pure-logic module (no filesystem I/O, no MCP, no project mutation), mirroring
the ``pipelines/masking.py`` builder pattern.

Why this exists
---------------
Kdenlive 25.04's **Object Mask** (SAM2 local-AI segmentation) runs as an
*application* plugin, not an MLT filter, so it is not directly scriptable
through our file-based integration. What it *does* leave behind, however, is
consumable from a file: the plugin generates a **mask video/image file** and
its "Apply Mask" action inserts a **Shape Alpha** effect (MLT service
``shape``) whose ``resource`` property points at that generated matte.

This module builds that same ``shape`` filter, letting our file-based tools
**consume any external matte file** (a SAM2-exported mask, a rendered luma
wipe, a hand-painted alpha video, etc.) as a clip's alpha channel. It is the
concrete implementation of the ``image_alpha`` mask type that
``server/tools.py::mask_set`` currently rejects as "not yet implemented", and
of the deferred "feed our own SAM/YOLO segmentation output in as luma-matte
video" item in ``docs/plans/2026-07-03-kdenlive-mcp-improvements.md`` §5.

Schema verified against ``/usr/share/kdenlive/effects/shape.xml`` and
``/usr/share/kdenlive/effects/mask_start_shape.xml``:

* MLT service ``shape`` (Shape Alpha). Properties: ``resource`` (matte file),
  ``mix`` (threshold %, 0-100), ``softness`` (0.0-1.0), ``invert`` (bool),
  ``use_luminance`` (bool -- use luma instead of alpha), ``use_mix`` (bool --
  apply the threshold at all), ``in`` (mask start offset), ``out`` (mask end,
  ``-1`` = to clip end), ``audio_match`` (fixed ``0``).
* The masked-effect sandwich form is ``mask_start`` / ``kdenlive_id
  mask_start-shape`` with ``filter=shape`` and ``filter.*`` prefixed inner
  properties, closed by a ``mask_apply`` filter (see ``masking.py``).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


# Inner property names carried on the plain ``shape`` filter, in the order
# Kdenlive writes them. Used for both the plain and the ``filter.*`` sandwich
# form.
SHAPE_INNER_PROPS: tuple[str, ...] = (
    "resource",
    "mix",
    "softness",
    "invert",
    "use_luminance",
    "use_mix",
    "in",
    "out",
    "audio_match",
)


def _bool01(value: bool) -> str:
    return "1" if value else "0"


def _make_filter(
    mlt_service: str,
    clip_ref: tuple[int, int],
    props: list[tuple[str, str]],
) -> str:
    """Serialize a ``<filter>`` element (attrs + ``<property>`` children)."""
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


def _shape_inner_props(
    resource: str,
    mix: int,
    softness: float,
    invert: bool,
    use_luminance: bool,
    use_mix: bool,
    mask_in: int,
    mask_out: int,
) -> list[tuple[str, str]]:
    if not resource or not str(resource).strip():
        raise ValueError("resource (mask file path) is required and non-empty")
    if not 0 <= mix <= 100:
        raise ValueError(f"mix={mix} out of [0,100]")
    if not 0.0 <= softness <= 1.0:
        raise ValueError(f"softness={softness} out of [0,1]")
    if mask_in < 0:
        raise ValueError(f"mask_in={mask_in} must be >= 0")
    if mask_out < -1:
        raise ValueError(f"mask_out={mask_out} must be >= -1 (-1 = clip end)")
    return [
        ("resource", str(resource)),
        ("mix", str(mix)),
        ("softness", f"{softness}"),
        ("invert", _bool01(invert)),
        ("use_luminance", _bool01(use_luminance)),
        ("use_mix", _bool01(use_mix)),
        ("in", str(mask_in)),
        ("out", str(mask_out)),
        ("audio_match", "0"),
    ]


def build_shape_alpha_xml(
    clip_ref: tuple[int, int],
    resource: str,
    *,
    mix: int = 100,
    softness: float = 0.1,
    invert: bool = False,
    use_luminance: bool = False,
    use_mix: bool = True,
    mask_in: int = 0,
    mask_out: int = -1,
) -> str:
    """Build a plain ``shape`` (Shape Alpha) filter referencing ``resource``.

    This replaces a clip's alpha channel with the matte read from
    ``resource`` (a SAM2-exported mask video, a luma wipe, an alpha video,
    etc.). Use ``use_luminance=True`` for mattes that carry the mask in luma
    (white = keep) rather than in an alpha channel.
    """
    props: list[tuple[str, str]] = [
        ("mlt_service", "shape"),
        ("kdenlive_id", "shape"),
    ]
    props.extend(
        _shape_inner_props(
            resource, mix, softness, invert, use_luminance, use_mix,
            mask_in, mask_out,
        )
    )
    return _make_filter("shape", clip_ref, props)


def build_mask_start_shape_xml(
    clip_ref: tuple[int, int],
    resource: str,
    *,
    mix: int = 70,
    softness: float = 0.1,
    invert: bool = False,
    use_luminance: bool = False,
    use_mix: bool = True,
    mask_in: int = 0,
    mask_out: int = -1,
) -> str:
    """Build the ``mask_start-shape`` sandwich-opener form of Shape Alpha.

    Emits ``filter.*`` prefixed inner properties, matching
    ``/usr/share/kdenlive/effects/mask_start_shape.xml``. Pair with
    ``masking.build_mask_apply_xml`` to route the matte's alpha onto the
    effects placed between the two filters. ``in``/``out`` are NOT prefixed
    (they sit on the outer ``mask_start`` filter per the stock XML).
    """
    inner = _shape_inner_props(
        resource, mix, softness, invert, use_luminance, use_mix,
        mask_in, mask_out,
    )
    props: list[tuple[str, str]] = [
        ("mlt_service", "mask_start"),
        ("kdenlive_id", "mask_start-shape"),
        ("filter", "shape"),
    ]
    for name, value in inner:
        # ``in``/``out`` live on the outer mask_start filter, not prefixed.
        if name in ("in", "out"):
            props.append((name, value))
        else:
            props.append((f"filter.{name}", value))
    return _make_filter("mask_start", clip_ref, props)
