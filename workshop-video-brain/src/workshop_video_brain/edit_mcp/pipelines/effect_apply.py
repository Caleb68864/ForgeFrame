"""Generic effect application pipeline."""
from __future__ import annotations

import logging
from typing import Any

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.core.models.timeline import AddEffect
from workshop_video_brain.edit_mcp.adapters.kdenlive import patcher as _patcher

logger = logging.getLogger(__name__)

# Curated reference list -- informational only, NOT a validation gate.
# Kdenlive builds have different effects installed depending on MLT version,
# frei0r availability, and FFmpeg build flags.
_COMMON_EFFECTS: list[dict[str, str]] = [
    {
        "name": "lift_gamma_gain",
        "description": "Color wheels for shadows, midtones, highlights",
    },
    {
        "name": "avfilter.curves",
        "description": "Curve-based color adjustment",
    },
    {
        "name": "frei0r.colgate",
        "description": "White balance correction",
    },
    {
        "name": "avfilter.lut3d",
        "description": "Apply LUT file",
    },
    {
        "name": "avfilter.eq",
        "description": "Brightness, contrast, saturation",
    },
    {
        "name": "frei0r.IIRblur",
        "description": "Gaussian blur",
    },
    {
        "name": "avfilter.chromakey",
        "description": "Chroma key (green screen)",
    },
    {
        "name": "affine",
        "description": "Transform (scale, position, rotate)",
    },
]


def apply_effect(
    project: KdenliveProject,
    track_index: int,
    clip_index: int,
    effect_name: str,
    params: dict[str, str] | None = None,
) -> KdenliveProject:
    """Add a named effect to a clip in a Kdenlive project.

    Creates an AddEffect intent and patches the project via deep-copy.
    Does NOT validate effect_name -- any string is accepted.
    Multiple calls on the same clip append effects (no replacement).

    Parameters
    ----------
    project:
        Parsed Kdenlive project.
    track_index:
        Zero-based track index.
    clip_index:
        Zero-based clip index within the track.
    effect_name:
        MLT service name (e.g., "avfilter.eq", "lift_gamma_gain").
    params:
        Key-value pairs for effect properties. None or empty dict for defaults.

    Returns
    -------
    New KdenliveProject with the effect appended.

    Raises
    ------
    IndexError:
        If track_index or clip_index is out of range.
    ValueError:
        If effect_name is empty.
    """
    if not effect_name or not effect_name.strip():
        raise ValueError("effect_name must be a non-empty string")

    intent = AddEffect(
        track_index=track_index,
        clip_index=clip_index,
        effect_name=effect_name.strip(),
        params=params or {},
    )
    return _patcher.patch_project(project, [intent])


def list_common_effects() -> list[dict[str, str]]:
    """Return a curated list of common Kdenlive/MLT effects.

    This list is informational only -- it helps users discover effects
    but is NOT used for validation. Any effect name can be passed to
    apply_effect() regardless of whether it appears here.
    """
    return list(_COMMON_EFFECTS)  # return a copy
