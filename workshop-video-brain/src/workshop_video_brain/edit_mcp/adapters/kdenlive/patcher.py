"""Kdenlive project patcher (compatibility shim).

The patcher was split into two focused modules:

* :mod:`.patcher_intents` -- ``patch_project`` and every ``_apply_*`` timeline
  intent handler plus their private helpers.
* :mod:`.effect_stack` -- the per-clip effect-stack API
  (``insert_effect_xml``, ``list_effects``, ``get_effect_property``,
  ``set_effect_property``, ``remove_effect``, ``reorder_effects``) plus its
  ``_iter_clip_filters`` helper.

This module re-exports every public and private name that previously lived in
``patcher.py`` so that existing imports -- both
``from ...adapters.kdenlive.patcher import X`` and
``from ...adapters.kdenlive import patcher`` (then ``patcher.X``) -- keep
working unchanged.
"""
from __future__ import annotations

from .patcher_intents import (
    calculate_crossfade,
    patch_project,
    _take_snapshot,
    _find_playlist,
    _playlist_index,
    _apply_add_guide,
    _apply_add_clip,
    _apply_trim_clip,
    _apply_insert_gap,
    _apply_add_subtitle_region,
    _apply_create_track,
    _apply_remove_clip,
    _apply_move_clip,
    _sync_tractor_out,
    _remap_clip_filters,
    _apply_place_clip,
    _apply_move_clip_to_track,
    _apply_split_clip,
    _apply_ripple_delete,
    _timewarp_resource,
    _apply_set_clip_speed,
    _tw_producer_id,
    _ensure_timewarp_producer,
    _ramp_entries,
    _apply_speed_ramp,
    _apply_audio_fade,
    _set_hide_directive,
    _apply_set_track_mute,
    _apply_set_track_visibility,
    _apply_add_effect,
    _resolve_track_index,
    _track_filter_meta,
    _apply_clear_track_filters,
    _apply_add_track_filter,
    _apply_add_composition,
    _resolve_clip_index,
    _tractor_index,
    _emit_simple_transition,
    _apply_add_transition,
)
from .effect_stack import (
    _iter_clip_filters,
    list_effects,
    get_effect_property,
    set_effect_property,
    insert_effect_xml,
    remove_effect,
    reorder_effects,
)

__all__ = [
    "calculate_crossfade",
    "patch_project",
    "insert_effect_xml",
    "list_effects",
    "get_effect_property",
    "set_effect_property",
    "remove_effect",
    "reorder_effects",
]
