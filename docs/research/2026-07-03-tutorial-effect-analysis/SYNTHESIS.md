# Tutorial Effect Analysis — Synthesis

Consolidates the four per-batch reports in this folder (fire-text-effects.md,
clone-teleport-effects.md, compositing-effects.md, motion-graphics-pipeline.md)
covering all 10 videos of the Nuxttux Kdenlive tutorials playlist. Transcripts:
`vault/Transcripts/Kdenlive Tutorials/`.

## Proposed bundle tools (one MCP tool per tutorial effect)

| Bundle tool | Video | Blocking gaps |
|---|---|---|
| `effect_fire_text` | Fire Text Effect | placement fix, title clips, effect_luma_key, effect_transform |
| `effect_burning_text` | Burning Text Effect | placement fix, title clips, composite_wipe ext (custom luma/invert/softness), effect_alpha_shape, effect_transform |
| `effect_teleport` | Teleportation | placement fix, clip_freeze_hold, effect_transform, frame-extract, animated roto (partial), sequence nesting (optional) |
| `effect_clone_self` | Duplicate Yourself | placement fix, **animated rotoscoping (hard blocker)**, roto luma mode, cross-track clip_move, audio detach/sync |
| `effect_glow_eyes` | Lucifer Eyes | placement fix, **motion_track**, animated roto, clip_duplicate_to_track, solid-color producer, lift_gamma_gain |
| `effect_object_remove` | Object Removal | placement fix, frame-extract-to-project, motion_track (static path needs neither tracker nor roto — **closest to shippable**) |
| `effect_composite_fire` | Fire Compositing | placement fix, motion_track, keyframable wrappers, animated roto, working clip_speed |
| `mograph_import` | Glaxnimate vs Friction | **composite placement (§1.2)**, clip_insert track param, .rawr/SVG/solid producers |
| `sequence_to_alpha_video` | Blender/Friction pipeline | image-sequence ingest, alpha render profile — **additive, unblocked** |

## Consolidated missing primitives, by demand

1. **§1.1/§1.2 placement fix** — blocks every bundle. Filters must nest in playlist
   `<entry>`s; transitions must land inside the `<tractor>` (composite_* builds
   well-formed XML that the serializer relocates to root because it never reads
   `position_hint`). Melt-oracle harness proves the fix (design doc:
   docs/plans/2026-07-03-melt-oracle-test-harness-design.md).
2. **Animated rotoscoping** (4 videos) — `masking._spline_json` emits frame 0 only;
   need keyframed splines + luma mode + `roto-spline` ParamType.
3. **motion_track / subject_track** (3 videos) — `opencv.tracker` absent everywhere;
   plan §5 already designs it; needs tracker→transform keyframe bridge.
4. **effect_transform** (4 videos) — first-class qtblend/affine wrapper (scale, pos,
   rotation, keyframable, fit modes); not in the catalog at all.
5. **Title clips** (2 videos) — plan §6; prerequisite for both text-effect bundles.
6. **Timeline placement upgrades** — clip_insert track param, cross-track clip_move,
   place-at-frame, match-length insert, clip_duplicate_to_track.
7. **effect_luma_key** (2), **composite_wipe extension** (custom luma mat, invert,
   softness), **effect_alpha_shape** (keyframed size, operations, easing).
8. **clip_freeze_hold** (real frame hold; clip_speed is a §1.1 no-op),
   **frame-extract-to-project** (2 videos).
9. **Producers**: solid color, single image, image sequence (`%04d`), `.rawr`/SVG.
   *(Partially addressed additively: `media_slideshow` (bundle) assembles an image
   folder into an ingestable `.mp4` via FFmpeg — timelapse/slideshow tutorial #21,
   analysis `timelapse-slideshow.md`. The native MLT image-sequence producer +
   `DEFAULT_EXTENSIONS`/glob scan (`probe.py:16`) remain deferred.)*
10. **Alpha render profile** (render-with-alpha template) — pairs with #9.
11. **Keyframable effect wrappers** (wrappers accept static values only) — already
    plan §3 Medium; fire compositing needs animated edge-glow.
12. **Sequence nesting, master/track-level effect target, audio detach/sync** — later.

## Build order

- **Wave 0 (foundation)**: melt-oracle harness (per design doc), then the placement
  fix that flips its strict xfails. Nothing else ships credibly before this.
- **Wave 1 (primitives)**: effect_transform, effect_luma_key, title clips (§6),
  clip_insert track param + place-at-frame, freeze/frame-extract, composite_wipe
  ext, alpha render profile + image/solid/sequence producers.
- **Wave 2 (tracking & roto)**: subject_track (§5), animated rotoscoping,
  keyframable wrappers.
- **Wave 3 (bundles)**: sequence_to_alpha_video and effect_object_remove(static)
  first (fewest deps), then fire_text, burning_text, mograph_import, teleport,
  composite_fire, glow_eyes, clone_self.

## Migration note — gap #6 Timeline placement upgrades: BUILT (Wave-3b, 2026-07-03)

Gap #6 ("Timeline placement upgrades") is **BUILT**. The canonical, public
placement engine now lives in:

- `edit_mcp/pipelines/clip_place.py` — pure planning: frame-exact
  `seconds_to_frames` (half-up, correct at 23.976/29.97), `plan_overwrite`,
  `plan_insert`, `plan_insert_blank`, plus reference-clip helpers. Returns an
  `index_map` so clip-filter associations follow the renumbering.
- `core/models/timeline.py` — `PlaceClip` + `MoveClipToTrack` intents.
- `adapters/kdenlive/patcher.py` — `_apply_place_clip` / `_apply_move_clip_to_track`
  (+ `_remap_clip_filters`, `_sync_tractor_out`), `ripple_all_tracks` implemented.
- `server/bundles/clip_place.py` — MCP tools `clip_place`, `clip_move_to`,
  `clip_place_matched` (overwrite + insert modes, cross-track move, match-length).

Melt-proven (`tests/integration/external/test_clip_place_render.py`): overwrite
places blue over red at exact time (1.9s red / 2.5s blue / 3.1s red); insert
ripples content right and grows duration; cross-track move reveals the lower
track at the old position and shows the moved clip at the new; match-length spans
exactly the reference clip (boundary frames 89 blue / 90 white).

**Modules that should migrate onto this engine** (they currently carry private
model-level insert-at-time workarounds; do NOT keep re-implementing placement):
`pipelines/overlay_looks.py` (`insert_overlay_clip`), `pipelines/titles.py`, and
the Wave-3a `vo_loop` / `image_overlay` modules once they land. Point their
inserts at `pipelines.clip_place.plan_overwrite` / `plan_insert` (or the
`PlaceClip` intent) so placement math has one home.
