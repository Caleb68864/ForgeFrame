"""Paper-cutout transition pipeline -- torn-paper reveal filter stack.

Pure-logic module (no filesystem I/O, no MCP, no ``KdenliveProject`` mutation),
following the ``pipelines/masking.py`` / ``pipelines/effect_presets.py`` pattern.

Effect source
-------------
Distilled from the *"Kdenlive | Paper Cutout Transition Tutorial"* (Mint
Visual, ``Fh1xhOzfjBE``). See
``docs/research/2026-07-03-tutorial-effect-analysis/paper-cutout-transition.md``.

The tutorial builds a stepped, hand-masked paper-tear reveal spread across
three video tracks (still frames, a screen-blended paper texture, and a white
torn edge). The full multi-track assembly requires producers that the MCP
surface does not yet expose (extract-frame-to-project, single-image and
solid-colour producers -- SYNTHESIS gaps #8/#9) and hand-drawn per-still roto
splines. This module implements the achievable, per-clip **torn-paper cutout
stack** -- the visual signature that makes one layer read as a torn cutout:

1. **Transform** (``affine``) -- optional uniform scale about frame centre,
   the "white rim / paper edge" trick (tutorial [04:34]-[05:20]); applied
   first so the mask cuts the scaled image.
2. **Rotoscoping mask** (``rotoscoping``) -- the torn subject outline. The
   tutorial hand-traces this per still with feather width / passes = 2
   ([00:46]). Callers pass an explicit normalized polygon; when none is
   given a deterministic procedural *torn* polygon is generated so the tool
   works out of the box.
3. **Distort** (``frei0r.distort0r``) -- optional edge-roughening wobble
   (tutorial [05:20]).
4. **Drop shadow** (``dropshadow``) -- the paper-lift shadow (tutorial
   [05:20], black, x/y offset ~4, raised blur radius).

Documented omissions (not reproducible per-clip today): the stepped
multi-still reveal, the screen-blended paper-texture layer (use
``composite_set(blend_mode="screen")`` on a separate track -- subject to the
§1.2 transition-placement bug), the white-edge as a *separate* colour-clip
track, and hand-drawn roto splines. See the analysis report for the full map.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET

from workshop_video_brain.edit_mcp.pipelines import masking


# ---------------------------------------------------------------------------
# frei0r.distort0r property indices (Amplitude, Frequency, Use Velocity, Velocity)
# ---------------------------------------------------------------------------
_DISTORT_AMPLITUDE_KEY = "0"
_DISTORT_FREQUENCY_KEY = "1"

# A deterministic torn-paper polygon: a jagged near-rectangle around a subject
# roughly centred in the lower-middle of the frame. Normalized coordinates.
DEFAULT_TORN_BOUNDS: tuple[float, float, float, float] = (0.18, 0.12, 0.64, 0.82)


# ---------------------------------------------------------------------------
# XML helper
# ---------------------------------------------------------------------------

def _make_filter(
    mlt_service: str,
    clip_ref: tuple[int, int],
    props: list[tuple[str, str]],
) -> str:
    """Build a Kdenlive/MLT ``<filter>`` XML string (mirrors ``masking._make_filter``)."""
    track, clip = clip_ref
    root = ET.Element(
        "filter",
        {"mlt_service": mlt_service, "track": str(track), "clip_index": str(clip)},
    )
    for name, text in props:
        el = ET.SubElement(root, "property", {"name": name})
        el.text = text
    return ET.tostring(root, encoding="unicode")


# ---------------------------------------------------------------------------
# Procedural torn polygon
# ---------------------------------------------------------------------------

def build_torn_polygon(
    bounds: tuple[float, float, float, float] = DEFAULT_TORN_BOUNDS,
    sides: int = 16,
    jitter: float = 0.05,
    seed: int = 1,
) -> tuple[tuple[float, float], ...]:
    """Return a deterministic jagged (torn-paper) closed polygon.

    Points are sampled around the ellipse inscribed in ``bounds`` and pushed
    in/out by a seeded pseudo-random radial ``jitter`` to fake a torn edge.
    All coordinates are clamped to ``[0, 1]`` so they satisfy
    :class:`masking.MaskParams`.

    Deterministic: the same ``(bounds, sides, jitter, seed)`` always yields the
    same polygon (no ``random`` module -- a small LCG keeps tests stable across
    Python versions).
    """
    if sides < 3:
        raise ValueError(f"sides must be >= 3; got {sides}")
    if jitter < 0.0:
        raise ValueError(f"jitter must be >= 0; got {jitter}")
    x, y, w, h = bounds
    cx, cy = x + w / 2.0, y + h / 2.0
    rx, ry = w / 2.0, h / 2.0

    # Tiny deterministic LCG in [0, 1).
    state = (seed * 2654435761 + 12345) & 0xFFFFFFFF

    def _rand() -> float:
        nonlocal state
        state = (1103515245 * state + 12345) & 0x7FFFFFFF
        return state / 0x7FFFFFFF

    pts: list[tuple[float, float]] = []
    for i in range(sides):
        theta = 2.0 * math.pi * i / sides
        wobble = 1.0 + (_rand() * 2.0 - 1.0) * jitter
        px = min(1.0, max(0.0, cx + rx * math.cos(theta) * wobble))
        py = min(1.0, max(0.0, cy + ry * math.sin(theta) * wobble))
        pts.append((round(px, 4), round(py, 4)))
    return tuple(pts)


# ---------------------------------------------------------------------------
# Per-filter property builders
# ---------------------------------------------------------------------------

def transform_rect(scale: float, frame_width: int, frame_height: int) -> str:
    """Return an ``affine`` ``rect`` string for a centred uniform ``scale``.

    Format is ``"x y w h opacity"`` (matches ``effect_fade`` / Kdenlive's
    Transform effect). ``scale > 1`` grows the layer about the frame centre --
    the tutorial's white-rim / paper-edge trick.
    """
    if scale <= 0.0:
        raise ValueError(f"edge_scale must be > 0; got {scale}")
    if frame_width <= 0 or frame_height <= 0:
        raise ValueError("frame_width and frame_height must be > 0")
    w = frame_width * scale
    h = frame_height * scale
    px = (frame_width - w) / 2.0
    py = (frame_height - h) / 2.0
    return f"{px:.1f} {py:.1f} {w:.1f} {h:.1f} 1"


def distort_props(amplitude: float, frequency: float) -> list[tuple[str, str]]:
    """Return ``frei0r.distort0r`` properties for edge-roughening."""
    if amplitude < 0.0:
        raise ValueError(f"distort_amplitude must be >= 0; got {amplitude}")
    if frequency < 0.0:
        raise ValueError(f"distort_frequency must be >= 0; got {frequency}")
    return [
        ("mlt_service", "frei0r.distort0r"),
        ("kdenlive_id", "frei0r_distort0r"),
        (_DISTORT_AMPLITUDE_KEY, f"{amplitude:.4f}"),
        (_DISTORT_FREQUENCY_KEY, f"{frequency:.4f}"),
    ]


def dropshadow_props(
    offset: int, blur: float, color: str
) -> list[tuple[str, str]]:
    """Return ``dropshadow`` filter properties (black paper-lift shadow)."""
    if blur < 0.0:
        raise ValueError(f"shadow_blur must be >= 0; got {blur}")
    color_hex = masking.color_to_mlt_hex(color)
    return [
        ("mlt_service", "dropshadow"),
        ("kdenlive_id", "dropshadow"),
        ("radius", f"{blur:.2f}"),
        ("x", str(int(offset))),
        ("y", str(int(offset))),
        ("color", color_hex),
    ]


# ---------------------------------------------------------------------------
# Full stack
# ---------------------------------------------------------------------------

def paper_cutout_filter_xml(
    clip_ref: tuple[int, int],
    *,
    points: tuple[tuple[float, float], ...] = (),
    feather: int = 2,
    feather_passes: int = 2,
    alpha_operation: str = "add",
    edge_scale: float = 1.0,
    frame_width: int = 1920,
    frame_height: int = 1080,
    distort_amplitude: float = 0.0,
    distort_frequency: float = 0.02,
    drop_shadow: bool = True,
    shadow_offset: int = 4,
    shadow_blur: float = 8.0,
    shadow_color: str = "#000000",
) -> list[str]:
    """Build the ordered torn-paper cutout ``<filter>`` XML strings for a clip.

    Order (application / stack order, index 0 applied first):

    1. Transform (``affine``) -- only when ``edge_scale != 1.0``.
    2. Rotoscoping mask (``rotoscoping``) -- always. Uses ``points`` if given
       (>= 3 normalized pairs), else a deterministic procedural torn polygon.
    3. Distort (``frei0r.distort0r``) -- only when ``distort_amplitude > 0``.
    4. Drop shadow (``dropshadow``) -- only when ``drop_shadow`` is true.

    Raises ``ValueError`` on invalid inputs (bad polygon, out-of-range mask
    params, non-positive scale, negative amplitudes, bad colour).
    """
    if points and len(points) < 3:
        raise ValueError(
            f"points must contain at least 3 [x, y] pairs; got {len(points)}"
        )
    resolved_points = points or build_torn_polygon()

    # Validate mask params up front (also validates point normalization).
    # Normalize pydantic ValidationError to ValueError so callers only need to
    # catch (ValueError, TypeError).
    try:
        mask = masking.MaskParams(
            points=resolved_points,
            feather=feather,
            feather_passes=feather_passes,
            alpha_operation=alpha_operation,
        )
    except ValueError:
        raise
    except Exception as exc:  # pydantic ValidationError et al.
        raise ValueError(str(exc)) from exc

    xmls: list[str] = []

    if edge_scale != 1.0:
        rect = transform_rect(edge_scale, frame_width, frame_height)
        xmls.append(
            _make_filter(
                "affine",
                clip_ref,
                [
                    ("mlt_service", "affine"),
                    ("kdenlive_id", "transform"),
                    ("rect", rect),
                ],
            )
        )

    xmls.append(masking.build_rotoscoping_xml(clip_ref, mask))

    if distort_amplitude > 0.0:
        xmls.append(
            _make_filter(
                "frei0r.distort0r",
                clip_ref,
                distort_props(distort_amplitude, distort_frequency),
            )
        )

    if drop_shadow:
        xmls.append(
            _make_filter(
                "dropshadow",
                clip_ref,
                dropshadow_props(shadow_offset, shadow_blur, shadow_color),
            )
        )

    return xmls
