"""Effect-find pipeline: resolve a filter index within a clip's filter stack.

Pure-logic helper. Delegates enumeration to
``patcher.list_effects`` rather than parsing XML directly.
"""
from __future__ import annotations

import logging

from workshop_video_brain.core.models.kdenlive import KdenliveProject
from workshop_video_brain.edit_mcp.adapters.kdenlive.patcher import list_effects

logger = logging.getLogger(__name__)


def _format_available(effects: list[dict]) -> str:
    parts = []
    for e in effects:
        parts.append(
            f"{{index={e['index']}, "
            f"kdenlive_id='{e.get('kdenlive_id', '')}', "
            f"mlt_service='{e.get('mlt_service', '')}'}}"
        )
    return "[" + ", ".join(parts) + "]"


def find(
    project: KdenliveProject,
    clip_ref: tuple[int, int],
    name: str,
) -> int:
    """Resolve an effect index on a clip by kdenlive_id (preferred) or mlt_service.

    Matching strategy:
      1. Collect indices where ``kdenlive_id == name``. If non-empty, resolve
         within this bucket only (cross-bucket matches never disambiguate).
      2. Otherwise, collect indices where ``mlt_service == name``.

    Raises
    ------
    LookupError
        No effect matched. Error message lists all effects on the clip.
    ValueError
        Multiple effects matched within a bucket. Error message lists all
        matching indices and suggests ``effect_index=`` for disambiguation.
    """
    effects = list_effects(project, clip_ref)

    kid_matches = [e["index"] for e in effects if e.get("kdenlive_id") == name]
    if kid_matches:
        matches = kid_matches
    else:
        matches = [e["index"] for e in effects if e.get("mlt_service") == name]

    if not matches:
        raise LookupError(
            f"No effect named '{name}'. Available: {_format_available(effects)}"
        )

    if len(matches) > 1:
        raise ValueError(
            f"Ambiguous effect name '{name}': matched indices {matches}. "
            f"Pass effect_index= to disambiguate."
        )

    return int(matches[0])
