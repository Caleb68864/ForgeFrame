"""Resolve an MLT filter's Kdenlive registry identity."""
from __future__ import annotations

import logging
from collections.abc import Iterable

from .effect_ids import EFFECT_IDS, KNOWN_EFFECT_IDS

logger = logging.getLogger(__name__)


def normalize_effect_id(
    mlt_service: str, kdenlive_id: str = "", props: Iterable[str] = ()
) -> str | None:
    """Return the registered effect id, or ``None`` for an unknown service."""
    prop_names = set(props)
    if kdenlive_id in KNOWN_EFFECT_IDS:
        return kdenlive_id
    if kdenlive_id in EFFECT_IDS:
        return EFFECT_IDS[kdenlive_id][0]
    if (
        mlt_service == "affine"
        and kdenlive_id == "transform"
        and "transition.rect" in prop_names
    ):
        return "pan_zoom"
    if mlt_service in KNOWN_EFFECT_IDS:
        return mlt_service
    matches = [
        effect_id
        for effect_id, service in EFFECT_IDS.values()
        if service == mlt_service
    ]
    if len(matches) == 1:
        return matches[0]
    logger.warning(
        "No unique Kdenlive effect identity for service %r and id %r",
        mlt_service,
        kdenlive_id,
    )
    return None
