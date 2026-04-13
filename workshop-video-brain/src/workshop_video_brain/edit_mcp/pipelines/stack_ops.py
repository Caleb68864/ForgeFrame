"""Stack-ops pipeline: serialize/deserialize/paste/reorder a clip's filter stack.

Pure-logic module. No MCP concerns, no filesystem I/O. Operates on
``KdenliveProject`` instances via the ``patcher`` functions from Sub-Spec 1.

See docs/specs/2026-04-13-stack-ops.md for the feature spec.
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Literal

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher

logger = logging.getLogger(__name__)

VALID_MODES: tuple[str, ...] = ("append", "prepend", "replace")

# Regex bounded to the first <filter ...> opening tag to rewrite attrs
# without round-tripping inner <property> children (which would reflow
# keyframe animation strings).
_FILTER_OPEN_RE = re.compile(r"<filter\b([^>]*)(/?)>", re.DOTALL)
_TRACK_ATTR_RE = re.compile(r'\strack="[^"]*"')
_CLIPIDX_ATTR_RE = re.compile(r'\sclip_index="[^"]*"')


def _rewrite_scope_attrs(xml_str: str, track: int, clip: int) -> str:
    """Rewrite/inject track= and clip_index= on the first <filter ...> open tag.

    Preserves the rest of the XML (including <property> children) byte-exact.
    """
    m = _FILTER_OPEN_RE.search(xml_str)
    if m is None:
        raise ValueError(
            "stack_ops: filter xml does not contain a <filter ...> opening tag"
        )
    attrs = m.group(1)
    self_close = m.group(2)

    # Replace or inject track=
    if _TRACK_ATTR_RE.search(attrs):
        attrs = _TRACK_ATTR_RE.sub(f' track="{track}"', attrs, count=1)
    else:
        attrs = attrs.rstrip() + f' track="{track}"'

    # Replace or inject clip_index=
    if _CLIPIDX_ATTR_RE.search(attrs):
        attrs = _CLIPIDX_ATTR_RE.sub(f' clip_index="{clip}"', attrs, count=1)
    else:
        attrs = attrs.rstrip() + f' clip_index="{clip}"'

    new_open = f"<filter{attrs}{self_close}>"
    return xml_str[: m.start()] + new_open + xml_str[m.end():]


def serialize_stack(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
) -> dict:
    """Serialize a clip's filter stack to a JSON-friendly dict.

    Returns ``{"source_clip": [track, clip], "effects": [{...}, ...]}`` where
    each effect entry has keys ``xml`` (verbatim ``OpaqueElement.xml_string``),
    ``kdenlive_id``, and ``mlt_service``.
    """
    filters = patcher._iter_clip_filters(project, clip_ref)
    effects: list[dict] = []
    for _idx, elem, root in filters:
        kdenlive_id = ""
        for child in root:
            if child.tag == "property" and child.get("name") == "kdenlive_id":
                kdenlive_id = child.text or ""
                break
        effects.append(
            {
                "xml": elem.xml_string,
                "kdenlive_id": kdenlive_id,
                "mlt_service": root.get("mlt_service") or "",
            }
        )
    return {
        "source_clip": [clip_ref[0], clip_ref[1]],
        "effects": effects,
    }


def deserialize_stack(stack_dict: dict) -> list[str]:
    """Validate a stack dict and return the ordered list of filter XML strings.

    Raises ``ValueError`` on malformed input, pointing the caller at
    ``effects_copy`` as the expected producer.
    """
    if not isinstance(stack_dict, dict):
        raise ValueError(
            "stack must be a dict produced by effects_copy; got "
            f"{type(stack_dict).__name__}"
        )
    if "effects" not in stack_dict:
        raise ValueError(
            "stack dict missing 'effects' key -- did you pass the output of "
            "effects_copy?"
        )
    effects = stack_dict["effects"]
    if not isinstance(effects, list):
        raise ValueError(
            "'effects' must be a list (from effects_copy); got "
            f"{type(effects).__name__}"
        )
    xml_list: list[str] = []
    for i, entry in enumerate(effects):
        if not isinstance(entry, dict):
            raise ValueError(
                f"effects[{i}] must be a dict; got {type(entry).__name__}"
            )
        if "xml" not in entry or not isinstance(entry["xml"], str):
            raise ValueError(
                f"effects[{i}] missing required str 'xml' field (from "
                f"effects_copy)"
            )
        xml_list.append(entry["xml"])
    return xml_list


def apply_paste(
    project: KdenliveProject,
    target_clip_ref: tuple[int, int],
    stack_dict: dict,
    mode: Literal["append", "prepend", "replace"] = "append",
) -> int:
    """Apply a serialized stack to the target clip in the given mode.

    Rewrites ``track=``/``clip_index=`` attributes on each pasted filter to
    match ``target_clip_ref`` (byte-exact preservation of inner content).

    Returns the number of filters pasted.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"mode must be one of: append, prepend, replace; got {mode!r}"
        )

    xml_list = deserialize_stack(stack_dict)

    if mode == "replace":
        existing = patcher.list_effects(project, target_clip_ref)
        for idx in range(len(existing) - 1, -1, -1):
            patcher.remove_effect(project, target_clip_ref, idx)

    if not xml_list:
        return 0

    if mode == "prepend":
        base = 0
    else:
        # append or post-clear replace
        base = len(patcher.list_effects(project, target_clip_ref))

    track, clip = target_clip_ref
    for i, xml_str in enumerate(xml_list):
        rewritten = _rewrite_scope_attrs(xml_str, track, clip)
        patcher.insert_effect_xml(
            project, target_clip_ref, rewritten, position=base + i
        )

    logger.info(
        "apply_paste: clip %s mode=%s pasted %d filters",
        target_clip_ref, mode, len(xml_list),
    )
    return len(xml_list)


def reorder_stack(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    from_index: int,
    to_index: int,
) -> None:
    """Thin pass-through to ``patcher.reorder_effects`` for layering symmetry."""
    patcher.reorder_effects(project, clip_ref, from_index, to_index)


__all__ = [
    "serialize_stack",
    "deserialize_stack",
    "apply_paste",
    "reorder_stack",
    "VALID_MODES",
]


# Silence unused-import warnings for ET (kept available for future use).
_ = ET
