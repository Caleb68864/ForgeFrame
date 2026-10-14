# Prompt 20: trim tools as patcher intents (slip, slide, replace, ripple insert)

Read `docs/prompts/00-README.md` first. Its shared rules apply and are not
repeated here.

**Summary.** ForgeFrame has basic clip edits (`clip_trim`, `clip_split`,
`clip_move`, `clip_remove`, `clip_ripple_delete`, `gap_insert`, `clip_place`
with overwrite/insert modes). It lacks the four classic NLE trims: **slip**
(change which part of the source a clip shows, same place and length),
**slide** (move a clip along the track while its neighbours absorb the move),
**replace** (swap a clip's media, same place and length), and **ripple
insert** of a clip with its audio before an existing clip. Build each as a
pure planning function + a patcher intent + a thin MCP shell, keep the linked
audio entry in sync (prompt 02 made every A/V clip a video entry plus an audio
entry at the same timeline frame), respect CLAUDE.md hard rule 14 (producer
`length` must cover every entry's out-point), and prove each with a melt
render. Depends on prompt 02.

## What exists (read before writing code)

- Intents: `core/models/timeline.py` (`TrimClip` ~43, `PlaceClip` ~149, ...).
  Apply functions + the `patch_project` dispatcher (~174):
  `edit_mcp/adapters/kdenlive/patcher_intents.py`. Apply functions log a
  warning containing "skipped" for a no-op; `PatchReport` relies on that.
- Pure placement math: `edit_mcp/pipelines/clip_place.py`: `entry_length`,
  `playlist_length`, `plan_insert` (returns `PlacementResult(entries,
  index_map, placed_index)`), `plan_insert_blank` (ripples another track;
  **splits a clip that straddles the point**), `clip_at_index`,
  `clip_start_frame`.
- `patcher_intents._remap_clip_filters(project, track_index, index_map)` (~588):
  clip effects are filters keyed by `track` (playlist index) + `clip_index`
  (index among non-blank entries). Anything that changes clip indices on a
  track must remap that track's filters.
- `PlaceClip(mode="insert", ripple_all_tracks=True)` already ripples other
  tracks and guides, but inserts a **blank** on the audio track (no audio),
  does not shift `<transition>` elements, and does not remap filters on other
  tracks where `plan_insert_blank` split a clip. Do not "fix" PlaceClip;
  write the ripple insert as its own intent and list those PlaceClip gaps in
  the report.
- Shell patterns: `clip_trim` / `clip_ripple_delete` in
  `edit_mcp/server/tools/clips_nle.py` (~401, ~454): `_load_latest_project`,
  `_resolve_playlist(project, track)` (**`track` = video-track index**, 0 =
  first video track), `patch_project(..., with_report=True)`, `_save_patched`.
  Source resolution: `_resolve_source` / `_producer_id_for` in
  `edit_mcp/server/bundles/clip_place.py` (~56-100); import them, do not copy.
- Linked audio: after prompt 02 a clip's audio half is the entry on an audio
  track with the same `producer_id` and the same timeline start frame. Grep
  `patcher_intents.py` for the helper prompt 02 added (e.g. "linked"). If
  there is none, add `_find_linked_audio(project, video_playlist, clip_index)
  -> tuple[Playlist, int] | None` there and use it everywhere below.

### Behaviour harvested from another project (ideas only)

- Slip: shift `in` and `out` by the same delta, position and length fixed;
  error if `in` would go below 0. (Source delta is scaled by clip speed there;
  we refuse speed-changed clips instead, see below.)
- Slide: move the clip by delta; the previous adjacent clip's out-point and
  the next adjacent clip's in-point move by the same delta; error if a
  neighbour would be consumed entirely.
- Replace: point the clip at different media, keep timeline position and
  length.
- Ripple insert: everything at or after the insert point moves right by the
  new clip's length, on all tracks by default.

## Steps

1. **Pure planner** `edit_mcp/pipelines/trim_ops.py` (no I/O, works on
   `list[PlaylistEntry]`, raises `ValueError` with a clear message):
   - `plan_slip(entries, clip_index, delta, source_frames: int | None) -> list`:
     new in/out = old + delta; reject `in < 0` and, when `source_frames` is
     known, `out > source_frames - 1`.
   - `plan_slide(entries, clip_index, delta, prev_source_frames, next_source_frames)
     -> list`. Neighbour = the entry directly before/after in
     `entries`, which may be a **blank** or a clip. delta > 0: previous
     neighbour grows by delta (a clip's out += delta, a blank's length +=
     delta), next shrinks by delta (a clip's in += delta; a blank's length
     -= delta and is removed at 0; a removed blank does not change clip
     indices, blanks are not counted). delta < 0 mirrors this (previous shrinks:
     a clip's out += delta; next grows: a clip's in += delta). Reject if a
     neighbour clip would drop below 1 frame, a growing clip would run past
     its source (or below source frame 0), or there is no neighbour on the shrinking side (first/last
     clip).
   - `plan_replace(entries, clip_index, new_producer_id, new_in) -> list`: same
     length, `out = new_in + length - 1`.
   - `insert_frame_for(entries, before_clip_index) -> int` (start frame of
     that clip; `len(real clips)` means "append at end of track").
   - Every planner must keep `playlist_length` unchanged (slip, slide,
     replace). Assert it in the planner and in tests.
2. **Intents** in `core/models/timeline.py`: `SlipClip(track_ref, clip_index,
   delta_frames, source_frames: int | None = None)`, `SlideClip(track_ref,
   clip_index, delta_frames, prev_source_frames=None, next_source_frames=None)`,
   `ReplaceClip(track_ref, clip_index, producer_id, source_path="", new_in=0,
   replace_audio: bool = True, new_has_audio: bool = True)` (the shell probes
   the media and fills `new_has_audio`; intents never probe), `RippleInsert(track_ref, before_clip_index,
   producer_id, source_path="", in_point, out_point, with_audio: bool = True,
   ripple_all_tracks: bool = True)`.
3. **Apply functions** in `patcher_intents.py` + dispatch branches:
   - All four apply the same change to the **linked audio entry** (slip: same
     delta; slide: same delta on the audio track's neighbours; replace with
     `replace_audio=True`: new producer and in-point, or a blank of the same
     length when the new media has no audio; `replace_audio=False` leaves the
     audio entry untouched, keeping the old sound under the new picture;
     ripple insert: the audio half goes on the first audio track at the same
     frame, and when the media has no audio a blank of length L goes there).
     If the video clip has a linked audio entry but the audio change is
     impossible (e.g. different neighbours on the audio track make the slide
     invalid there), skip the whole intent with a "skipped" warning; never
     change video alone.
   - Ripple insert: `plan_insert` on the video track and (with audio) on the
     audio track; `plan_insert_blank` on every other track when
     `ripple_all_tracks`; shift guides at/after the frame; shift every
     `<transition>` OpaqueElement whose `in` >= frame by L (their `in`/`out`
     properties may be ints or `HH:MM:SS.mmm`; parse both, write back in the
     same format); refuse (skip) when a transition straddles the frame.
     Remap filters on every track whose clip indices changed (target: the
     `index_map`; other tracks: build a map when a straddling clip was split,
     giving both halves the original filters).
   - Rule 14: add `_ensure_producer_length(project, producer_id)`: if the
     producer has a `length` property, raise it to `max(out_point) + 1` over
     all entries using that producer; never lower it. Call it after slip,
     slide, replace and ripple insert.
   - Speed-changed clips (entry producer has `mlt_service == "timewarp"`):
     skip with a clear warning for slip/slide/replace; list as a known gap.
   - Slide: also skip when a `<transition>` overlaps the moved clip's range.
4. **Shells**: new module `edit_mcp/server/bundles/clip_trims.py` with
   `clip_slip(workspace_path, clip_index, offset_seconds, track=0)`,
   `clip_slide(workspace_path, clip_index, offset_seconds, track=0)`,
   `clip_replace(workspace_path, clip_index, source, source_in_seconds=0.0,
   track=0, replace_audio=True)`, `clip_ripple_insert(workspace_path, source,
   before_clip_index, in_seconds=0.0, out_seconds=-1.0, track=0,
   ripple_all_tracks=True)`. Seconds -> frames with `seconds_to_frames`. Probe
   media length with `probe_media` (`adapters/ffmpeg/probe.py`) for
   `source_frames`; for MLT `color` producers use their `length` property as
   the bound. Validate (`invalid_index`, `invalid_input`, `missing_file`),
   all-skipped report -> `invalid_input` with the reasons, then
   `_save_patched`. Return the clip's new in/out/start frame, the linked audio
   result (`audio_synced: true/false`), and the playlist total length before
   and after.

## Tests

1. **Unit** `tests/unit/test_trim_ops.py` (planner + intents) and
   `tests/unit/test_clip_trims_tools.py` (shells; workspace via the
   `_make_workspace` pattern in `tests/unit/test_nle_operations.py` ~73):
   - Invariant on every slip/slide/replace: each playlist's
     `playlist_length` is unchanged; clips not involved are byte-identical.
   - Ripple insert: target and audio tracks grow by L; other tracks grow by L
     only if they extend past the insert frame; guides and transitions after
     the frame move by L; filters stay on the same clips.
   - Audio sync: after every op the video clip and its audio entry start on
     the same frame with the same in/out.
   - Rule 14: a slip past the producer's stored `length` raises `length`.
   - Errors: slip past source start/end, slide into a too-short neighbour,
     slide of the first clip backwards, timewarp clip, bad indices.
2. **External render proofs** `tests/integration/external/test_trim_tools_render.py`
   (pattern: `test_clip_place_render.py`; `render_frame`, `mean_color`,
   `probe`, `audio_stats` from `_oracle.py`):
   - Slip: make one media file of three 2 s solid segments (red, green, blue)
     plus a sine track with ffmpeg (`requires_ffmpeg`; e.g. three
     `-f lavfi -i color=...:d=2` inputs joined with the `concat` filter and a
     `sine` audio input, `-shortest`). Clip = source frames 0-49 (red). Slip
     +50: the same timeline frame now renders green; the render's duration
     (probe) is unchanged.
   - Slide: `sequence_project([RED, BLUE, GREEN])` from the testkit (colour
     producers have 10 spare frames). Slide clip 1 by +5: frame
     `start(1) + 2` renders red, frame `end(1) + 2` renders blue; duration
     unchanged.
   - Replace: replace clip 1 by a green producer: its frames render green,
     duration unchanged.
   - Ripple insert: insert a green clip before clip 1 of `[RED, BLUE]` with
     audio media: frames read red, green, blue in order; duration grows by L;
     `audio_stats` mean volume of the render is above -60 dB.

## Acceptance criteria

- Four tools registered; planner invariants hold; audio entries never drift.
- Each render proof passes under `xvfb-run -a`; full suite green; ruff clean.

## Do NOT

- Do not change `PlaceClip`, `TrimClip`, `clip_trim` or the dissolve logic
  (commit `38fe0e1`).
- Do not touch serializer output shape, `kdenlive:id` numbering or producer
  layout (prompts 04, 05, 24 own those).
- Do not rescale in/out for speed-changed clips; refuse them.
- Do not adjust entry-local keyframes of neighbours during slide; list it as a
  known limitation instead.

## When done

1. Document the four tools in `workshop-video-brain/skills/ff-rough-cut-review/SKILL.md`
   (or the skill that already documents `clip_trim`; grep for it).
2. Add `vault/wiki/kdenlive-trim-operations.md`: what each trim changes in the
   playlists, the linked-audio rule, and rule 14 for slip.
3. Regenerate `docs/capabilities.md`; mark Phase 4 item 5 done in
   `docs/plans/2026-10-13-media-mcp-expansion.md`.
4. Report as in `00-README.md`, including the PlaceClip/SplitClip filter-remap
   gaps you saw and which existing intents still ignore linked audio.
