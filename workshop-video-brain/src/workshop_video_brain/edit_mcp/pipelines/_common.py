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


def seconds_to_mmss(seconds: float) -> str:
    """Convert float seconds to a ``M:SS`` string (minutes are not zero-padded)."""
    total_secs = int(seconds)
    minutes = total_secs // 60
    secs = total_secs % 60
    return f"{minutes}:{secs:02d}"
