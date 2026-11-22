# Kdenlive trim operations (slip, slide, replace, ripple insert)

Prompt 20, 2026-11-22. Planner `edit_mcp/pipelines/trim_ops.py`; intents applied in `edit_mcp/adapters/kdenlive/patcher_trims.py`; tools `clip_slip`, `clip_slide`, `clip_replace`, `clip_ripple_insert` (`server/bundles/clip_trims.py`).

## What each changes in the playlists

- **Slip**: the clip's `in` and `out` both move by the same delta. Its place, its length and every other entry stay. Refused before source frame 0 or past the source's last frame.
- **Slide**: the clip's own `in`/`out` stay; it moves along the track. Sliding later, the entry before grows (a clip's `out`, or a blank's length; a new blank if the clip was first) and the entry after shrinks (a clip's `in`, or a blank, removed at zero). Sliding earlier mirrors that. Refused when the shrinking side has nothing, a neighbour clip would drop below one frame, a growing clip has no spare source, or a transition overlaps the range. Entry-local keyframes of the neighbours are not adjusted.
- **Replace**: the clip points at another producer from `new_in`, same length (`out = new_in + length - 1`).
- **Ripple insert**: the clip goes in before `before_clip_index`; that track and the first audio track get the clip (or, for media without audio, a blank of the same length) via `plan_insert`; every other track gets a blank via `plan_insert_blank` (a straddling clip is split and both halves keep its filters); guides and transitions at or after the frame move right (transition `in`/`out` as frames or `HH:MM:SS.mmm`, written back in the same form). A transition spanning the insert frame refuses the whole insert.

Slip, slide and replace never change any playlist's total length.

## Linked audio

A clip's audio half is the entry on an audio track with the same producer (audio-twin suffix ignored) starting on the same timeline frame (`patcher_trims.find_linked_audio`). Every trim applies the same change to it. If the audio track cannot take the change (for example its neighbours differ and are too short for the slide), the whole intent is skipped: video never moves alone. `clip_replace(replace_audio=false)` deliberately leaves the old audio under the new picture.

## Rule 14 after a slip

A slip (or slide, replace, insert) can push an entry's `out` past the producer's stored `length`; Kdenlive then drops that entry on load. `ensure_producer_length` raises `length` to the largest `out + 1` of any entry using the producer, and never lowers it.

## Speed-changed clips

Clips on a `timewarp` producer are refused for slip, slide and replace: their in/out are in warped frames and are not rescaled here.
