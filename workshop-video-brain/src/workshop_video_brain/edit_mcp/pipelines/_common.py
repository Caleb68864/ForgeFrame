"""Small shared pipeline helpers.

Extraction target for byte-identical primitives that were independently
reimplemented across ``pipelines/`` modules (consistency pass 1). Kept
deliberately dependency-light so any pipeline can import it without pulling in
the server/adapter layers.
"""
from __future__ import annotations

import math
import xml.etree.ElementTree as ET


def seconds_to_frames(seconds: float, fps: float) -> int:
    """Convert a timeline offset in seconds to an integer frame index/count.

    This is the ONE canonical seconds->frames conversion for the whole codebase.
    Rounds half-up (``floor(seconds * fps + 0.5)``) so placement is frame-exact
    and deterministic at fractional NTSC rates (23.976 / 29.97 / 59.94) -- i.e.
    what a human editor expects, not the truncation ``int(t*fps)`` nor Python's
    bankers' ``round``.  Raises ``ValueError`` on a negative time or
    non-positive fps.

    Callers that need a graceful fps fallback (``guides``/``vo_loop``) keep
    their own wrappers; everything computing a frame from seconds should route
    through here.
    """
    if seconds < 0:
        raise ValueError(f"seconds must be >= 0 (got {seconds})")
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    return int(math.floor(seconds * fps + 0.5))


def make_filter_xml(
    mlt_service: str,
    clip_ref: tuple[int, int],
    props: list[tuple[str, str]],
) -> str:
    """Serialize a Kdenlive/MLT ``<filter>`` element to an XML string.

    Emits ``<filter mlt_service=.. track=.. clip_index=..>`` with one
    ``<property name=..>text</property>`` child per ``(name, text)`` in *props*.
    This is the simple builder shared by the masking / shape-alpha / paper-cutout
    pipelines; the richer, id-normalizing variant lives in
    ``server/tools_helpers._build_filter_xml``.
    """
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


def make_filter_element_xml(
    mlt_service: str,
    kdenlive_id: str,
    clip_ref: tuple[int, int],
    props: list[tuple[str, str]],
    *,
    include_service_prop: bool = True,
) -> str:
    """Serialize a Kdenlive ``<filter>`` that carries a ``kdenlive_id`` property.

    Richer than :func:`make_filter_xml`: emits the root
    ``<filter mlt_service track clip_index>`` then a ``kdenlive_id`` property
    child (and, when *include_service_prop*, an explicit ``mlt_service`` property
    child) followed by one ``<property name=..>`` per ``(name, value)`` in
    *props*. This is the shared builder for the transform/keyframe bundle tools
    (``effect_pan_zoom``, ``subject_zoom``, ``transition_zoom_whip``) that
    previously hand-rolled the same element in the server layer.

    ``include_service_prop=True`` matches the pan/zoom + motion-track shape
    (svc + kid + props); ``False`` matches the zoom-whip shape (kid + props only).
    """
    track, clip = clip_ref
    root = ET.Element(
        "filter",
        {
            "mlt_service": mlt_service,
            "track": str(track),
            "clip_index": str(clip),
        },
    )
    if include_service_prop:
        svc = ET.SubElement(root, "property", {"name": "mlt_service"})
        svc.text = mlt_service
    kid = ET.SubElement(root, "property", {"name": "kdenlive_id"})
    kid.text = kdenlive_id
    for name, value in props:
        el = ET.SubElement(root, "property", {"name": name})
        el.text = str(value)
    return ET.tostring(root, encoding="unicode")


def check_unit_interval(name: str, value: object) -> float:
    """Validate *value* is a real number in ``[0.0, 1.0]`` and return it as float.

    Rejects bools and non-numerics with a ``ValueError`` naming the parameter.
    Shared by the overlay-looks / color-wash pipelines (opacity/intensity guards).
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric in [0.0, 1.0]; got {value!r}")
    v = float(value)
    if not 0.0 <= v <= 1.0:
        raise ValueError(f"{name} must be in [0.0, 1.0]; got {v}")
    return v


def keyword_match_strength(text_lower: str, keyword: str) -> float:
    """Return a keyword-vs-text match strength for marker / b-roll heuristics.

    Exact substring (phrase) match -> ``1.0``; all individual words of a
    multi-word keyword present but not contiguous -> ``0.7``; otherwise ``0.0``.
    *text_lower* and *keyword* are expected already lower-cased. Shared by the
    ``auto_mark`` and ``broll_suggestions`` pipelines.
    """
    if keyword in text_lower:
        return 1.0
    words = keyword.split()
    if len(words) > 1 and all(w in text_lower for w in words):
        return 0.7
    return 0.0


def parabolic_peak_offset(y, i: int) -> float:
    """Sub-sample peak offset in ``[-0.5, 0.5]`` via a 3-point parabola around ``i``.

    Pure NumPy-array math (no import of numpy needed here -- operates via
    indexing/arithmetic). Returns ``0.0`` at the array edges or when the three
    points are collinear. Canonical sub-sample interpolation shared by the
    ``audio_sync`` cross-correlation and ``beat_grid`` tempo autocorrelation.
    """
    if i <= 0 or i >= y.size - 1:
        return 0.0
    left, mid, right = y[i - 1], y[i], y[i + 1]
    denom = left - 2.0 * mid + right
    if denom == 0.0:
        return 0.0
    return 0.5 * (left - right) / denom


def seconds_to_mmss(seconds: float) -> str:
    """Convert float seconds to a ``M:SS`` string (minutes are not zero-padded)."""
    total_secs = int(seconds)
    minutes = total_secs // 60
    secs = total_secs % 60
    return f"{minutes}:{secs:02d}"
