# Tutorial Effect Analysis — Teleportation & Duplicate Yourself

Date: 2026-07-03
Source transcripts: Nuxttux Creative Studio (Kdenlive tutorials)
Scope: map taught techniques → workshop-video-brain MCP tool surface; propose one
end-to-end bundle tool per video.

Context notes:
- Tool-surface files inspected: `edit_mcp/server/tools.py` (all `@mcp.tool()`),
  `edit_mcp/pipelines/masking.py`, `compositing.py`, `effect_apply.py`,
  `effect_catalog.py`, `keyframes.py`, `effect_wrappers/`.
- **§1.1 broken-list dependencies** (treat tools as *intended* capability, but
  flag): effect-stack machinery (`effect_add`, all 22 wrappers, `mask_set`,
  `mask_set_shape`, `mask_apply`, `effect_keyframe_set_*`, stack ops) attaches
  filters at the **MLT root** with custom `track=`/`clip_index=` attrs instead of
  nested inside the playlist `<entry>` — MLT may not associate them with clips.
  `clip_speed` writes a bogus `<filter type="speed">` (no-op). `transitions_apply*`
  emit invalid transition XML. `composite_set`/`composite_pip` use a *separate*
  compositing pipeline (`frei0r.cairoblend`/`qtblend` transition) — not on the
  explicit §1.1 broken list but unverified against melt/Kdenlive.

Catalog reality check (for the effects these videos need):
- `frei0r.distort0r` — **in catalog** (kdenlive_id `frei0r_distort0r`; animated
  params `Amplitude`, `Frequency`, `Velocity`).
- `avfilter.dblur` (Directional Blur) — **in catalog** (kdenlive_id `avfilter_dblur`).
- `freeze` — **in catalog** (kdenlive_id `freeze`).
- `avfilter.lut3d` — used by `color_apply_lut` tool.
- Letterbox — `effect_frei0r_letterb0xed` wrapper exists.
- **Transform** (Kdenlive's `qtblend`/`affine` scale+position+rotation effect) —
  **NOT a catalog entry**. Only appears as the `transition` property of
  mask_apply, and `affine` appears as `shear`. Addable via `effect_add` with a raw
  service string, but there is no first-class transform helper and no catalog
  validation for its rect/keyframe params.
- **Rotoscoping** — **excluded from catalog** (the known `roto-spline` ParamType
  gap, §1.3). Reachable only through the dedicated `mask_set` / `mask_set_shape`
  tools, and the emitted spline is **single-keyframe (frame 0) only** — no
  animated/moving rotoscope.

---

## Video 1 — Create Teleportation Effect

### a) Step-by-step technique breakdown

1. **[00:16]** Transcode phone footage (VFR → CFR) via clip → Transcode / "edit
   friendly format".
2. **[00:46]** Mark in/out around the two mid-air jump points; insert zone into
   project bin (action plate).
3. **[01:00]** Capture a **clean plate** (empty frame, camera left rolling); mark
   in/out, add to bin.
4. **[01:32]** Layer: clean plate on track 1 (bottom), action plate above.
5. **[01:40]** Length-match clean plate to action plate: copy/paste, trim a few
   head frames, butt the two clips, **double-click to add a transition**, slightly
   increase transition duration.
6. **[02:00]** Leave ~1 s of breathing room at the head for the effect.
7. **[02:17]** **Cut ≥1 frame out of the action clip** (`Shift+R` cut, jump to
   end, back one frame, second cut). This isolates a short segment.
8. **[02:40]** Make that first cut last ≥5 frames; grab the move tool, hold Ctrl,
   drag the clip end to **slow the single frame down into a pseudo-freeze-frame**
   (deliberately avoids the native Freeze effect — "renders errors once you start
   using a transform clip with it"). Repeat for the last frame.
9. **[03:03]** Alternative noted: set monitor 1:1, right-click project monitor →
   **Extract Frame to Project** (PNG steel frame).
10. **[03:49]** **Rotoscope the subject**: add Rotoscoping effect to the clip,
    rough point selection on first frame, `alpha_operation = minimum`,
    `feather = 1`, curve handles; can toggle mode alpha ↔ RGB to preview.
11. **[04:35]** Add **Transform** effect: on last frame add a keyframe (locks
    scale+position); on first frame set **scale 30 %** + reposition subject
    (slightly higher for motion); **interpolation = cubic in** (ease).
12. **[05:00]** **Directional Blur (dblur)** for fake motion blur: match angle to
    motion (~70°, downward-forward); first keyframe radius 5, last keyframe radius
    0. On the exit cut mirror it: cubic-out, radius back to 5.
13. **[05:50]** `Ctrl+A` → right-click → **Create Sequence from Selection**
    ("teleportation raw") — nest everything.
14. **[06:07]** In the raw sequence, **rotoscope the background action area** (or
    the sky) to freeze cloud/shadow drift: feather 15, passes 4, `minimum`.
15. **[07:00]** Add **guides** ("VFX in 1", "VFX in 2") marking where distortion
    starts.
16. **[07:39]** Cut out short segments around each VFX guide to isolate the
    distortion region in time.
17. **[07:55]** Add **Distort** effect to those cuts: amplitude/frequency 0 at
    head & tail, mid keyframe amplitude 30 / frequency -0.0x (taste).
18. **[08:40]** Distort covers the whole frame → isolate it: add **Mask (mask
    apply)** underneath + a **Secondary Color Correction** area selection set to
    "add" as the mask source; then a **normal Rotoscoping above the distort** to
    restrict distortion to a hand-drawn area (feather 10, passes 2, `minimum`).
19. **[09:57]** Adjust to hide ghosting; **copy effects** and **paste effects**
    onto the second cut; move the rotoscope over the new (disappear) area.
20. **[10:44]** `Ctrl+A` → **Create Sequence from Selection** ("teleport VFX").
21. **[11:30]** Optional extras: import a **spell-hit** overlay on a track above,
    set **Composite → Composite and Transform**, **blend mode = screen**, position
    to match.
22. **[12:17]** Color grade the nested sequence: LUT (creative), sharpness reduced,
    curves to tame LUT intensity.
23. **[13:02]** Apply a **camera-shake preset** (downloadable) to the sequence.
24. **[13:20]** Add **Letterbox** effect to master, value 200 (black bars).

### b) Kdenlive features / effects used (exact names)

Transcode (VFR→CFR) · zone in/out + insert to bin · clean plate · same-track
transition (double-click crossfade) · manual frame **cuts** (`Shift+R`) · **speed
drag** to fake a freeze frame (explicitly *not* the Freeze effect) · Extract Frame
to Project (PNG steel) · **Rotoscoping** (alpha_operation minimum, feather,
passes, alpha/RGB mode) · **Transform** (scale, position, cubic-in/out
interpolation) · **Directional Blur / dblur** (angle, radius keyframes) · **Create
Sequence from Selection** (nesting) · **Guides** · **Distort** (frei0r.distort0r —
amplitude/frequency keyframes) · **Mask (mask_apply) + Secondary Color Correction
area selection (add)** · **copy effects / paste effects** · **Composite and
Transform** transition · **blend mode = screen** · LUT + curves + sharpness ·
**camera-shake preset** · **Letterbox** (master).

### c) Capability mapping

| # | Step | MCP tool(s) | Status | Notes |
|---|------|-------------|--------|-------|
| 1 | Transcode VFR→CFR | `media_check_vfr`, `media_transcode_cfr` | exists | fine |
| 2-3 | Zone marks / clean plate to bin | `markers_*`, `media_ingest` | partial | no "extract sub-zone as new bin clip"; no clean-plate concept |
| 4 | Layer plates on tracks | `track_add`, `clip_insert` | partial | `clip_insert` is playlist-index placement, not place-at-frame-on-track |
| 5 | Same-track transition (crossfade) | `transitions_apply_between` | **missing/broken** | §1.1: transition XML invalid; also no same-track "mix" |
| 7-8 | Frame cuts + speed-drag freeze | `clip_split`, `clip_trim`, `clip_speed` | **broken** | `clip_speed` is a no-op (§1.1); no freeze-frame helper |
| 9 | Extract PNG steel frame | — | missing | no frame-extract-to-clip tool |
| 10 | Rotoscope subject | `mask_set(type=rotoscoping)`, `mask_set_shape` | partial | §1.1 root placement; spline is single-frame only; roto excluded from catalog |
| 11 | Transform scale/pos + easing | `effect_add("qtblend"/"affine")` + `effect_keyframe_set_rect` | partial | no transform helper; not in catalog; §1.1 placement; easing operators exist in `keyframes.py` (cubic) |
| 12 | Directional blur keyframes | `effect_add("avfilter.dblur")` + `effect_keyframe_set_scalar` | partial | in catalog; §1.1 placement; angle/radius must be keyed manually |
| 13/20 | Create Sequence from Selection (nest) | — | **missing** | parser assumes single tractor; nesting unsupported (§3 low) |
| 14/18 | Background/area rotoscope | `mask_set_shape`, `mask_apply` | partial | area-freeze workflow; §1.1; no secondary-color-correction mask source |
| 15 | Guides (VFX in 1/2) | `markers_auto_generate`, `markers_list` | partial | markers are side-car JSON, not project `kdenlive:docproperties.guides` (§3) |
| 16 | Time-isolate distortion cuts | `clip_split` | exists | ok |
| 17 | Distort keyframes | `effect_add("frei0r.distort0r")` + `effect_keyframe_set_scalar` | partial | in catalog; §1.1 placement |
| 18 | Mask distort to a region | `mask_set`+`mask_apply` sandwich | partial | §1.1; secondary-color-correction area-select mask source not modeled |
| 19 | Copy/paste effects | `effects_copy`, `effects_paste` | exists | ok (subject to §1.1 placement) |
| 21 | Spell-hit overlay, Composite&Transform, screen | `composite_set(blend_mode="screen")`, `composite_pip` | partial | "screen" supported; "Composite **and Transform**" (blend+geometry keyframes) not a distinct mode; composite pipeline unverified |
| 22 | LUT + curves + sharpness | `color_apply_lut`, `effect_add` | partial | LUT ok; curves/sharpness via generic effect_add |
| 23 | Camera-shake preset | `effect_stack_preset`, `effect_stack_apply` | partial | can store/apply a stack, but no shipped shake preset; roto-containing stacks can't be saved (§1.3) |
| 24 | Letterbox on master | `effect_frei0r_letterb0xed` | partial | wrapper exists; "master/track-level" application not supported (clip-only); §1.1 |

### d) Bundle tool spec — `effect_teleport`

Composes the disappear/reappear teleport end-to-end on a two-plate (action over
clean-plate) layout.

```
effect_teleport(
    workspace_path: str,
    project_file: str,
    action_track: int,                 # track holding the subject clip
    clean_plate_track: int,            # bottom track with empty background
    action_clip: int,                  # clip index on action_track
    disappear_at_seconds: float,       # where subject vanishes
    reappear_at_seconds: float,        # where subject returns
    subject_rect: str,                 # JSON [x,y,w,h] normalized seed roto/bbox
    dissolve_scale: float = 0.30,      # transform target scale at vanish
    dissolve_frames: int = 5,          # length of the pseudo-freeze/dissolve
    blur_angle: float = 70.0,          # dblur angle to match motion
    blur_radius: float = 5.0,          # peak dblur radius
    easing: str = "cubic",             # cubic-in on exit, cubic-out on entry
    distort_amplitude: float = 30.0,   # frei0r.distort0r peak
    distort_frequency: float = 0.05,
    add_letterbox: bool = False,
    letterbox_size: int = 200,
    nest_as_sequence: str = "",        # optional: name the resulting nested seq
)
```

Composes existing primitives, in order:
1. `clip_split` ×2 to isolate the dissolve segment around each teleport point.
2. **[NEW `clip_freeze_hold`]** to hold/slow the boundary frame (replaces the
   broken `clip_speed`; can't use catalog `freeze` reliably per the tutorial).
3. `mask_set`(rotoscoping, seed=`subject_rect`, alpha_operation=min, feather) on
   the action clip.
4. **[NEW `effect_transform`]** (thin helper over `effect_add("qtblend")` +
   `effect_keyframe_set_rect`) — scale `dissolve_scale`, reposition, `easing`.
5. `effect_add("avfilter.dblur")` + `effect_keyframe_set_scalar` — angle +
   radius keyframes.
6. `effect_add("frei0r.distort0r")` + `effect_keyframe_set_scalar` on the region
   cut; wrapped with `mask_set`/`mask_apply` to localize.
7. `effects_copy`/`effects_paste` to mirror the treatment onto the reappear cut.
8. Optional `effect_frei0r_letterb0xed` if `add_letterbox`.
9. Optional **[NEW `sequence_from_selection`]** if `nest_as_sequence`.

New primitives required first:
- **`clip_freeze_hold`** — real frame-hold (timewarp/freeze producer), because
  `clip_speed` is a §1.1 no-op and native `freeze` is what the tutorial avoids.
- **`effect_transform`** — first-class scale/position/rotation transform helper
  (qtblend) with keyframable rect + easing; transform is not in the catalog.
- **`sequence_from_selection`** — nesting (parser is single-tractor today).
- **Animated rotoscoping** — multi-keyframe spline (current spline is frame-0
  only); needed if the localized distort mask must move.
- **§1.1 fix** — filter/composite placement inside `<entry>` is a hard
  prerequisite for *all* of steps 3-6 to render.

§1.1-broken dependencies: `clip_speed` (no-op), `transitions_apply_between`
(invalid XML), `effect_add`/wrappers/`mask_*`/`effect_keyframe_*` (root-level
placement), `composite_set` (separate pipeline, unverified).

---

## Video 2 — Duplicate Yourself (clone)

### a) Step-by-step technique breakdown

1. **[00:00]** In-camera method: single take, **audio call-outs** ("I pour, I
   look up, I sit") let the performer sync both halves; act part 1, then part 2 on
   the same audio cue.
2. **[00:20]** In Kdenlive, the two performances are stacked **one clip on top of
   the other** (same shot, tripod / locked-off camera).
3. **[00:46]** **Sync the two clips by the repeated audio**, then delete the audio.
4. **[01:00]** Head-of-clip fix: a portion where the chair wasn't present is
   handled by adding a **steel frame + rotoscope** so the same chair reads on both
   sides.
5. **[01:15]** **Rotoscope** the top clip to reveal the bottom performer:
   alpha ↔ **Luma** preview, a little **feathering**.
6. **[01:33]** Nest into a **sequence**; imported the externally graded version
   (Dehancer) — no grade done in Kdenlive.
7. **[02:19]** The **rotoscope is animated** — after character 2 finishes pouring,
   the mask moves over the cup so character 1 can grab it (moving matte).
8. Sound design added on separate audio tracks (out of scope for the visual
   effect).

### b) Kdenlive features / effects used (exact names)

Locked-off/tripod dual-take · **audio sync** of two overlaid clips · audio delete
· **steel frame** insert · **Rotoscoping** (alpha ↔ Luma mode, feather) ·
**animated / moving rotoscope mask** (keyframed spline following the cup) ·
**Create Sequence** (nest) · external color grade import.

### c) Capability mapping

| # | Step | MCP tool(s) | Status | Notes |
|---|------|-------------|--------|-------|
| 2 | Overlay two clips on stacked tracks | `track_add`, `clip_insert` | partial | placement is playlist-index, not place-at-frame; cross-track move unsupported |
| 3 | Sync two clips by audio, delete audio | `audio_analyze` | **missing** | no audio-alignment/sync-offset tool; no per-clip audio detach |
| 4 | Steel-frame + roto for chair | — + `mask_set` | missing/partial | no extract-frame-to-clip; roto exists (§1.1) |
| 5 | Rotoscope top clip (alpha/Luma) | `mask_set(type=rotoscoping)`, `mask_set_shape` | partial | mode is fixed `alpha` in builder — **no Luma mode**; §1.1 placement |
| 6 | Nest into sequence | — | **missing** | no create-sequence/nesting |
| 7 | **Animated rotoscope** (mask follows cup) | `mask_set` | **missing** | spline is single frame-0 keyframe only — cannot animate the matte |
| 8 | Sound design tracks | `track_add`, audio tools | partial | audio tools operate on standalone files, disconnected from timeline (§3) |

### d) Bundle tool spec — `effect_clone_self`

Produces the "two of me in one shot" composite from two overlaid takes.

```
effect_clone_self(
    workspace_path: str,
    project_file: str,
    take_a_track: int,                 # bottom performer
    take_b_track: int,                 # top performer (gets the reveal mask)
    take_a_clip: int,
    take_b_clip: int,
    reveal_region: str,                # JSON [x,y,w,h] or polygon points (norm.)
    sync_offset_seconds: float = 0.0,  # manual A/B alignment if audio-sync absent
    mask_mode: str = "alpha",          # "alpha" | "luma"
    feather: int = 8,
    feather_passes: int = 1,
    mask_keyframes: str = "",          # JSON: frame -> spline, for a MOVING matte
    detach_audio: bool = True,         # drop the sync-guide audio after aligning
    nest_as_sequence: str = "",
)
```

Composes existing primitives, in order:
1. **[NEW `audio_sync_clips`]** (or manual `sync_offset_seconds`) to align B to A.
2. `clip_move`/`clip_trim` to seat the aligned clips (needs cross-track move).
3. **[NEW `clip_detach_audio`]** if `detach_audio`.
4. `mask_set`/`mask_set_shape` (rotoscoping) on take B with `reveal_region`,
   `feather` — but requires **Luma-mode support** and **animated spline**.
5. Optional **[NEW `sequence_from_selection`]** if `nest_as_sequence`.

New primitives required first:
- **Animated rotoscoping** (keyframed spline / moving matte) — the core of this
  effect; current builder emits a single frame-0 keyframe. **Hard blocker.**
- **Rotoscoping Luma mode** — builder hardcodes `mode="alpha"`; tutorial uses Luma.
- **`audio_sync_clips`** — cross-correlate two clips' audio, return offset.
- **`clip_detach_audio`** — split/remove a clip's audio stream on the timeline.
- **Cross-track `clip_move`** + place-at-frame — current `clip_move` is
  same-track/index only.
- **`sequence_from_selection`** — nesting.
- **§1.1 fix** — roto filter must be nested in the clip `<entry>` to render.

§1.1-broken dependencies: `mask_set`/`mask_set_shape` (root-level placement),
`clip_move` (index-only), timeline audio tools (disconnected from project).

---

## Raw data summary

### Video 1 — Teleportation
- **effect_name:** `effect_teleport`
- **missing primitives:**
  - `clip_freeze_hold` (real frame hold; `clip_speed` is a §1.1 no-op, native `freeze` avoided by tutorial)
  - `effect_transform` (first-class qtblend scale/pos/rotation helper; not in catalog)
  - `sequence_from_selection` (nesting; parser single-tractor)
  - animated/multi-keyframe rotoscoping spline
  - frame-extract-to-clip (PNG steel frame)
  - secondary-color-correction area-select as mask source
  - "Composite and Transform" blend+geometry composite mode
  - master/track-level effect application (letterbox on master)
- **bundle tool + params:** `effect_teleport(workspace_path, project_file, action_track, clean_plate_track, action_clip, disappear_at_seconds, reappear_at_seconds, subject_rect, dissolve_scale=0.30, dissolve_frames=5, blur_angle=70.0, blur_radius=5.0, easing="cubic", distort_amplitude=30.0, distort_frequency=0.05, add_letterbox=False, letterbox_size=200, nest_as_sequence="")`
- **§1.1-broken deps:** `clip_speed`, `transitions_apply_between`, `effect_add`+wrappers, `mask_set`/`mask_set_shape`/`mask_apply`, `effect_keyframe_set_*`, `composite_set` (unverified separate pipeline)

### Video 2 — Duplicate Yourself
- **effect_name:** `effect_clone_self`
- **missing primitives:**
  - animated rotoscoping (keyframed/moving matte) — hard blocker
  - rotoscoping Luma mode (builder hardcodes `mode="alpha"`)
  - `audio_sync_clips` (audio cross-correlation alignment)
  - `clip_detach_audio` (timeline audio split/remove)
  - cross-track `clip_move` + place-at-frame
  - `sequence_from_selection` (nesting)
  - frame-extract-to-clip (steel frame)
- **bundle tool + params:** `effect_clone_self(workspace_path, project_file, take_a_track, take_b_track, take_a_clip, take_b_clip, reveal_region, sync_offset_seconds=0.0, mask_mode="alpha", feather=8, feather_passes=1, mask_keyframes="", detach_audio=True, nest_as_sequence="")`
- **§1.1-broken deps:** `mask_set`/`mask_set_shape` (root-level placement), `clip_move` (index-only), timeline audio tools (disconnected)

### Cross-cutting new primitives (shared by both bundles)
1. **Animated rotoscoping** (multi-keyframe spline) — blocks both videos.
2. **§1.1 filter/composite placement fix** — prerequisite for every masked/keyed/
   transformed step in both.
3. **`sequence_from_selection` / nesting** — both videos nest at the end.
4. **`effect_transform`** helper (qtblend) — teleport; reusable for clone slide-ins.
