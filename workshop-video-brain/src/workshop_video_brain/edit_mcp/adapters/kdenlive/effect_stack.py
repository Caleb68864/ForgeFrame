"""Kdenlive clip effect-stack API.

The effect-stack functions used by every effect bundle to inspect and mutate
the per-clip filter stack: enumerating filters, reading/writing filter
properties, and inserting/removing/reordering filters.

Split out of ``patcher.py`` (pure code movement, no behaviour change); the
public API remains importable from ``patcher`` via a compatibility shim.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from workshop_video_brain.core.models.kdenlive import (
    KdenliveProject,
    OpaqueElement,
)

logger = logging.getLogger(__name__)

__all__ = [
    "insert_effect_xml",
    "list_effects",
    "get_effect_property",
    "set_effect_property",
    "remove_effect",
    "reorder_effects",
]


# ---------------------------------------------------------------------------
# Effect-property accessors (additive; used by the keyframe pipeline).
# ---------------------------------------------------------------------------


def _iter_clip_filters(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
) -> list[tuple[int, OpaqueElement, ET.Element]]:
    """Return [(effect_index, opaque_element, parsed_root), ...] for a clip.

    effect_index is the position of the filter within this clip's filter
    stack (0-based), NOT the index in project.opaque_elements. Stack order
    matches insertion order in project.opaque_elements.

    Raises IndexError if clip_ref refers to a non-existent track or clip.
    """
    track_index, clip_index = clip_ref

    if track_index < 0 or track_index >= len(project.playlists):
        raise IndexError(
            f"track_index {track_index} out of range "
            f"(have {len(project.playlists)} playlists)"
        )

    playlist = project.playlists[track_index]
    real_entries = [e for e in playlist.entries if e.producer_id]
    if clip_index < 0 or clip_index >= len(real_entries):
        raise IndexError(
            f"clip_index {clip_index} out of range "
            f"(track has {len(real_entries)} clips)"
        )

    result: list[tuple[int, OpaqueElement, ET.Element]] = []
    track_attr = str(track_index)
    clip_attr = str(clip_index)
    effect_index = 0
    for elem in project.opaque_elements:
        if elem.tag != "filter":
            continue
        try:
            root = ET.fromstring(elem.xml_string)
        except ET.ParseError:
            continue
        if root.get("track") != track_attr or root.get("clip_index") != clip_attr:
            continue
        result.append((effect_index, elem, root))
        effect_index += 1
    return result


def list_effects(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
) -> list[dict]:
    """Enumerate filters on a clip in stack order.

    Each dict has keys: index, mlt_service, kdenlive_id, properties.
    """
    out: list[dict] = []
    for effect_index, _elem, root in _iter_clip_filters(project, clip_ref):
        properties: dict[str, str] = {}
        kdenlive_id = ""
        for child in root:
            if child.tag != "property":
                continue
            name = child.get("name")
            if name is None:
                continue
            text = child.text or ""
            properties[name] = text
            if name == "kdenlive_id":
                kdenlive_id = text
        out.append(
            {
                "index": effect_index,
                "mlt_service": root.get("mlt_service") or "",
                "kdenlive_id": kdenlive_id,
                "properties": properties,
            }
        )
    return out


def get_effect_property(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
    property_name: str,
) -> str | None:
    """Return the property value for a filter on a clip, or None if missing.

    Raises IndexError if effect_index is out of range for the clip's stack.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    _idx, _elem, root = filters[effect_index]
    for child in root:
        if child.tag == "property" and child.get("name") == property_name:
            return child.text or ""
    return None


def set_effect_property(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
    property_name: str,
    value: str,
) -> None:
    """Set (or create) a <property name=...> entry on a clip's filter.

    Mutates project.opaque_elements in place by re-serializing the target
    filter's XML. Raises IndexError on bad clip_ref or effect_index.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    _idx, elem, root = filters[effect_index]
    target = None
    for child in root:
        if child.tag == "property" and child.get("name") == property_name:
            target = child
            break
    if target is None:
        target = ET.SubElement(root, "property", {"name": property_name})
    target.text = value
    elem.xml_string = ET.tostring(root, encoding="unicode")
    logger.info(
        "set_effect_property: clip %s effect %d property '%s'",
        clip_ref, effect_index, property_name,
    )


def insert_effect_xml(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    xml_string: str,
    position: int,
) -> None:
    """Insert a new filter OpaqueElement into a clip's effect stack.

    `position` is a per-clip stack index in [0, len(stack)]. 0 inserts at
    the top of the stack; `len(stack)` appends to the bottom.

    Raises IndexError on bad clip_ref or out-of-range position.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if position < 0 or position > len(filters):
        raise IndexError(
            f"position {position} out of range "
            f"(clip has {len(filters)} filters)"
        )

    new_element = OpaqueElement(
        tag="filter",
        xml_string=xml_string,
        position_hint="after_tractor",
    )

    if len(filters) == 0:
        project.opaque_elements.append(new_element)
    elif position < len(filters):
        abs_index = project.opaque_elements.index(filters[position][1])
        project.opaque_elements.insert(abs_index, new_element)
    else:
        abs_index = project.opaque_elements.index(filters[-1][1]) + 1
        project.opaque_elements.insert(abs_index, new_element)

    logger.info(
        "insert_effect_xml: clip %s position %d (stack len now %d)",
        clip_ref, position, len(filters) + 1,
    )


def remove_effect(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
) -> None:
    """Remove the filter at stack-index `effect_index` from a clip.

    Raises IndexError on bad clip_ref or out-of-range effect_index.
    """
    filters = _iter_clip_filters(project, clip_ref)
    if effect_index < 0 or effect_index >= len(filters):
        raise IndexError(
            f"effect_index {effect_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    target_elem = filters[effect_index][1]
    project.opaque_elements.remove(target_elem)
    logger.info(
        "remove_effect: clip %s effect %d (stack len now %d)",
        clip_ref, effect_index, len(filters) - 1,
    )


def reorder_effects(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    from_index: int,
    to_index: int,
) -> None:
    """Move a filter within a clip's stack from `from_index` to `to_index`.

    Semantics mirror `list.insert(to, list.pop(from))` applied to the clip's
    filter subset. `from_index == to_index` is a silent no-op.

    Raises IndexError on bad clip_ref or out-of-range indices.
    """
    if from_index == to_index:
        return

    filters = _iter_clip_filters(project, clip_ref)
    if from_index < 0 or from_index >= len(filters):
        raise IndexError(
            f"from_index {from_index} out of range "
            f"(clip has {len(filters)} filters)"
        )
    if to_index < 0 or to_index >= len(filters):
        raise IndexError(
            f"to_index {to_index} out of range "
            f"(clip has {len(filters)} filters)"
        )

    moving = filters[from_index][1]
    project.opaque_elements.remove(moving)

    filters_after = _iter_clip_filters(project, clip_ref)
    if to_index < len(filters_after):
        abs_index = project.opaque_elements.index(filters_after[to_index][1])
    elif len(filters_after) > 0:
        abs_index = project.opaque_elements.index(filters_after[-1][1]) + 1
    else:
        abs_index = len(project.opaque_elements)

    project.opaque_elements.insert(abs_index, moving)
    logger.info(
        "reorder_effects: clip %s moved %d -> %d",
        clip_ref, from_index, to_index,
    )
