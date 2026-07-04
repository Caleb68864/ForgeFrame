"""Small shared pipeline helpers.

Extraction target for byte-identical primitives that were independently
reimplemented across ``pipelines/`` modules (consistency pass 1). Kept
deliberately dependency-light so any pipeline can import it without pulling in
the server/adapter layers.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET


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
