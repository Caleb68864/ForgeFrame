"""Inspect and edit effects already applied to a clip (pure, no I/O).

The shells in ``server/bundles/effect_edit.py`` parse and save; this module
resolves which effect is meant, describes it, and checks parameter names.
"""
from __future__ import annotations

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.kdenlive.effect_stack import list_effects
from workshop_video_brain.edit_mcp.pipelines import effect_find
from workshop_video_brain.edit_mcp.pipelines.keyframes import _TIMESTAMP_RE

#: Bookkeeping properties a parameter edit must never touch: the service and
#: Kdenlive identity define the effect; ``disable`` belongs to effect_toggle.
PROTECTED_PARAMS = frozenset({"mlt_service", "kdenlive_id", "disable"})


def resolve_effect_index(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    effect_index: int,
    effect_name: str,
) -> int:
    """The stack index meant by exactly one of *effect_index* / *effect_name*.

    Raises ValueError for both or neither; LookupError / ValueError (ambiguous)
    from ``effect_find.find``; IndexError for an index past the stack.
    """
    by_index = effect_index is not None and effect_index >= 0
    by_name = bool(effect_name and effect_name.strip())
    if by_index == by_name:
        raise ValueError("Pass exactly one of effect_index (>= 0) or effect_name.")
    if by_name:
        return effect_find.find(project, clip_ref, effect_name.strip())
    count = len(list_effects(project, clip_ref))
    if effect_index >= count:
        raise IndexError(f"effect_index {effect_index} out of range (clip has {count} effects)")
    return effect_index


def is_keyframed(value: str) -> bool:
    """A Kdenlive animated value: ``frame=value`` pairs joined by ``;``, or timestamped."""
    if "=" not in value:
        return False
    if ";" in value:
        return True
    key = value.split("=", 1)[0].rstrip("~|!-$<>")  # easing marks follow the time
    return bool(_TIMESTAMP_RE.match(key))


def _bookkeeping(name: str) -> bool:
    return name in PROTECTED_PARAMS or name.startswith("kdenlive:")


def describe_effect(effect: dict) -> dict:
    """One ``list_effects`` row as ``{index, kdenlive_id, mlt_service, enabled, static_params, keyframed_params}``."""
    props = effect.get("properties", {})
    static, keyframed = {}, {}
    for name, value in props.items():
        if _bookkeeping(name):
            continue
        (keyframed if is_keyframed(value) else static)[name] = value
    return {
        "index": effect["index"],
        "kdenlive_id": effect.get("kdenlive_id", ""),
        "mlt_service": effect.get("mlt_service", "") or props.get("mlt_service", ""),
        "enabled": props.get("disable", "0") != "1",
        "static_params": static,
        "keyframed_params": keyframed,
    }


def check_param_names(kdenlive_id: str, mlt_service: str, names) -> list[str]:
    """Names the effect catalog does not know for this effect ([] if the effect is not catalogued).

    Looked up by service first: catalog keys are Kdenlive effect-file stems,
    which are not always the registry id written into ``kdenlive_id``.
    """
    from workshop_video_brain.edit_mcp.pipelines import effect_catalog

    effect = (effect_catalog.find_by_service(mlt_service) if mlt_service else None) \
        or (effect_catalog.find_by_name(kdenlive_id) if kdenlive_id else None)
    if effect is None:
        return []
    known = {param.name for param in effect.params}
    return [name for name in names if name not in known]


def stringify(value) -> str:
    """A JSON value as an MLT property string (``True`` -> ``"1"``)."""
    if isinstance(value, bool):
        return "1" if value else "0"
    return str(value)
