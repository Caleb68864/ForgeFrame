# Tutorial Effect Analysis — Fire / Burning Text (Nuxttux Creative Studio)

Maps two Kdenlive tutorials to the workshop-video-brain MCP tool surface.
Tools are treated at their **intended** capability per the survey note; every
dependency on a `docs/plans/2026-07-03-kdenlive-mcp-improvements.md` **§1.1**
"pseudo-XML that MLT ignores" item is flagged inline.

Cross-cutting §1.1 caveat that touches **both** effects: the entire clip-level
effect-stack machinery (`effect_add`, all wrappers, `mask_*`, `effect_keyframe_*`,
`effect_fade`) attaches `<filter>` at the **MLT root** with custom
`track=`/`clip_index=` attrs instead of nesting inside the playlist `<entry>`.
If §1.1 is correct, none of the per-clip effects below actually render until the
placement fix lands. Both bundle tools below inherit this as a hard prerequisite.

---

## Video 1 — Fire Text Effect (`4uWfPllnOgU`, 3:53)

Two approaches shown: (A) the quick built-in filter, (B) the "real" stock-flame
composite. The bundle tool targets (A) plus the compositing scaffold of (B).

### a) Step-by-step breakdown

| Time | Action |
|---|---|
| [00:00] | Goal: set text on fire in Kdenlive, in response to a viewer question. |
| [00:15] | **Quick method:** search effects for **Burning TV**, drag it onto the text clip → text ignites. |
| [00:33] | Notes Burning TV alone is not versatile/pretty. |
| [00:40] | **Better method:** gather stock footage of fire/flames (ActionVFX etc.). |
| [00:48] | Crop the flames, add **rotoscoping**, use a **luma mask** to shape how they look; optionally push them through a separate sequence, chop them up, "play with the levels". |
| [01:10] | Bring the flames back, add a **composition strip** → use **Composite and Transform**, set compositing to **screen**. |
| [01:20] | Put the flame composite track over the text track (text on V2). |
| [01:25] | Combine with **Burning TV** on the text for extra flame. |
| [01:45] | Add fire **sound design** (crackling fire) on the bottom track. |
| [02:00] | Full-body-of-text demo: **insert a track**, **duplicate** the title, double-click → **Update title clip** to "fire", bring it in. |
| [02:26] | Drag/drop **Burning TV** onto it, hide other tracks → text is on fire. |
| [02:40] | Tune **movement threshold** parameter: add a **Transform** effect, keyframe a move; lower threshold → more fire while moving, higher → less fire. |
| [03:09] | Closing notes: no 3D text in Kdenlive; alternative is Blender. |

### b) Kdenlive features / effects used (exact names)

- **Burning TV** (`BurningTV` MLT service) — primary fire filter; param **movement threshold**.
- **Rotoscoping** (mask) on the flame clip.
- **Luma mask / luma key** to shape the flames.
- **Crop** effect.
- **Composite and Transform** transition with compositing mode = **screen**.
- **Transform** effect with a keyframed position move (to demo movement threshold).
- **Title clip** (create / duplicate / "Update title clip") for the text.
- **Insert track**; layer text on V2 over flames.
- Levels / color adjustment ("play with the levels").
- Audio: fire SFX layer.

### c) Capability mapping

| Step / feature | MCP tool(s) | Status | Notes |
|---|---|---|---|
| Add Burning TV to text | `effect_add(effect_name="BurningTV")` (in catalog as `burningtv`) | **partial** | Generic add works; **§1.1 effect-placement** may prevent render. No dedicated wrapper exposing `movement threshold`. |
| Movement-threshold tuning | `effect_add` params / `effect_keyframe_set_scalar` | **partial** | Param passable but not surfaced/validated; keyframing subject to §1.1. |
| Screen-blend composite of flames over text | `composite_set(blend_mode="screen")` | **exists** | `screen` → `frei0r.cairoblend` prop "1". Uses `AddComposition` path (not the §1.1-broken `transitions_apply*` crossfade path); render still **unverified** (Tier-1 melt gate). |
| Composite geometry / transform of flame layer | `composite_set(geometry=...)` + Transform effect via `effect_add("qtblend"/"affine")` | **partial** | Composite geometry OK; a *clip-level* Transform effect (rotate/scale/keyframed move) has **no wrapper** and hits §1.1 placement; `effect_fade` already flagged for affine `rect` mismatch. |
| Rotoscoping on flames | `mask_set(type="rotoscoping")` / `mask_set_shape` | **partial** | Static frame-0 spline only; no animation. `roto-spline` ParamType gap (§1.3) blocks preset capture. |
| Luma mask / luma key (black→transparent) | — | **missing** | No `lumakey`/`luma`-filter wrapper; not in effect catalog as a clip filter. See Burning-Text §, same gap. |
| Crop | `effect_add("crop")` (`crop` in catalog) | **partial** | Generic only; §1.1 placement. |
| Levels / color grade of flames | `effect_tcolor`, `color_apply_lut`, `lift_gamma_gain` via `effect_add` | **partial** | Exist as wrappers/generic; §1.1 placement. |
| Create / duplicate / update title text | `title_cards_generate` | **missing** | Only writes **guides**, no on-screen text (survey §6). No title-clip primitive at all. |
| Insert video track | `track_add` | **exists** | — |
| Fire SFX layer | `clip_insert` (audio) + `audio_*` | **exists** | Placement is playlist-index only. |

### d) Bundle tool spec — `effect_fire_text`

End-to-end "set this text clip on fire". Composes the quick Burning-TV path and
optionally overlays stock-flame footage with a screen composite.

```
effect_fire_text(
    workspace_path: str,
    project_file: str,
    text_track: int,               # track holding the text/title clip
    text_clip: int,
    intensity: float = 0.5,        # → BurningTV movement_threshold (inverted: higher intensity = lower threshold)
    flame_track: int | None = None,# optional stock-flame footage track
    flame_clip: int | None = None,
    blend_mode: str = "screen",    # composite mode for flame overlay
    start_frame: int = 0,
    end_frame: int | None = None,  # default = text clip duration
    grade_flames: bool = True,     # apply luma-key + levels cleanup to flames
    add_burning_tv: bool = True,   # extra ignite pass on the text itself
)
```

Composition order (existing primitives):
1. `effect_add(text_track, text_clip, "BurningTV", {movement_threshold})` — if `add_burning_tv`.
2. If flame footage given:
   a. **NEW** luma-key primitive on `flame_clip` (black→transparent).
   b. `effect_tcolor` / levels on flame clip (if `grade_flames`).
   c. `composite_set(track_a=text_track, track_b=flame_track, blend_mode="screen", start/end)`.

NEW primitives that must be built first:
- **`effect_luma_key`** wrapper (MLT `lumakey`) — black/threshold→alpha, with `threshold`, `softness`, `invert`.
- **`effect_burning_tv`** wrapper exposing `movement_threshold` (+ its keyframe passthrough).
- **`effect_transform`** wrapper (rotate/scale/position, keyframable, "fit/adjust to original size" mode) — needed for the movement demo and flame placement.
- **Title-clip creation** primitive (survey §6) — required for a truly end-to-end tool; otherwise the caller must pre-build the text clip.

§1.1-broken dependencies: effect-stack root placement (BurningTV, luma-key, levels, transform), `effect_fade`/affine rect mismatch (if fades used). Composite path is `AddComposition` (not the broken `transitions_apply*`), render-unverified.

---

## Video 2 — Burning Text Effect (`kBPN3rTUcx4`, 6:54)

A wipe-reveal "burn away" between two stacked text clips (white over orange),
plus an ember overlay. This is the more complex, more compositing-heavy effect.

### a) Step-by-step breakdown

| Time | Action |
|---|---|
| [00:00] | Goal: "burning text" reveal (à la flick edit / Premiere). Suggests finishing by **right-click → Create sequence from selection** to flatten into one clip. |
| [00:47] | Assets: **ember stock footage** (from Pexels), and a **text clip** "burning" **duplicated** — white copy on top track, orange copy on bottom track. |
| [01:10] | Move out composition strips. Orange text = bottom, white text = top. |
| [01:20] | On the **white text** clip, click bottom-left corner to add a **composition strip**; size it to the full clip length. |
| [01:32] | Leave transition type on **wipe**; change **wipe method** from *none* to **clouds** (a black-and-white luma **mat**). |
| [01:45] | Shows the **download additional luma mats** panel; uses a custom cloud mat (same idea as built-in clouds). |
| [02:17] | Explains mats are B/W images Kdenlive uses for wipes; custom mats = more burn-like distribution. |
| [02:50] | Applies the mat → wipe transitions the shot **in**; needs the opposite, so **invert** it. |
| [03:04] | Inverted → wipe **removes** the white text, revealing orange underneath. |
| [03:15] | On the **orange text** clip, add a composition strip full-length, method = **cloud** too. Check both checkboxes. |
| [03:25] | The orange text is made **~10–11 frames longer** than the white text so the two wipes are **offset** (not synchronized). |
| [04:10] | Adds a bit of **soften** (value 2–4) to the orange composition strip so orange disappears after white. |
| [04:36] | **Embers:** the clip is a vertical strip → add a **Transform**, **rotate 90°**, then scale using **"Adjust to original size"** to fill the canvas (footage is 1080×1920). |
| [05:00] | Add a **luma key** to remove the black background (black → transparent); tune **threshold**. |
| [05:21] | Add an **alpha shape** set to **ellipse**; scale it very small on the first frames, then scale up later (as text finishes burning). |
| [05:55] | Set interpolation to **cubic out** (opens fast, slows at end). |
| [06:06] | Enable **soft edges** via the **transition width** control; set **operation = minimum** (default is *clear*), tied to the luma key. |
| [06:30] | Add a **fade out** so leftover embers exit cleanly. |

### b) Kdenlive features / effects used (exact names)

- **Composition strip / transition = Wipe** (MLT `luma` transition), with a selectable **luma mat** (method **clouds/cloud**, custom `.pgm` mats).
- **Invert** wipe direction.
- **Softness / Soften** on the wipe.
- **Offset** between two wipes (achieved by differing clip lengths, ~10–11 frames).
- **Transform** effect: **rotate 90°**, scale via **"Adjust to original size"** fit mode.
- **Luma Key** (black→transparent, `threshold`).
- **Alpha shape** (frei0r alpha-spot) set to **ellipse**, with **keyframed size** (small→large), **interpolation = cubic out**, **transition width** (soft edges), **operation = minimum**.
- **Fade out**.
- **Create sequence from selection** (flatten to one clip).

### c) Capability mapping

| Step / feature | MCP tool(s) | Status | Notes |
|---|---|---|---|
| Two stacked text clips (white/orange), duplicated | `clip_insert` + title primitive | **missing** | No title-clip creation (§6); caller must supply the text clips. |
| Wipe composition strip on white text | `composite_wipe(wipe_type="wipe")` | **partial** | Hardcodes `resource=/usr/share/kdenlive/lumas/HD/luma01.pgm`; **no luma-method selection (clouds), no custom mat path, no invert, no softness**. |
| Choose clouds / custom luma mat | — | **missing** | No param to pick/download a mat; `apply_wipe` only toggles dissolve vs one fixed luma. |
| Invert wipe direction | — | **missing** | No `invert` param on `composite_wipe`. |
| Soften wipe (value 2–4) | — | **missing** | No `softness` param on `composite_wipe`. |
| Offset the two wipes (~10 frames) | `clip_trim` / clip length control | **partial** | Achievable by trimming clip lengths; frame-precise, but no first-class "offset transitions" concept. |
| Transform embers: rotate 90° + fit-to-canvas | Transform via `effect_add("qtblend"/"affine")` | **missing** | No Transform wrapper; **"Adjust to original size" fit mode** is a Kdenlive UI convenience with no direct MLT param. §1.1 placement. |
| Luma key (remove black bg, threshold) | — | **missing** | No `lumakey` wrapper/catalog filter. (Same gap as Video 1.) |
| Alpha shape = ellipse | `effect_object_mask` (wraps `frei0r.alpha0ps_alphaspot`) / `mask_set_shape(shape="ellipse")` | **partial** | `effect_object_mask` exposes only `enabled`/`threshold` — **no shape select, no position/size, no operation, no transition width**. `mask_set_shape` makes a *rotoscoping* ellipse, not alpha-spot, and is **static** (frame-0 spline only). |
| Keyframe alpha-shape size small→large | `effect_keyframe_set_rect` / `set_scalar` | **partial** | Keyframing exists but not wired to the alpha-spot size props; §1.1 placement; needs `cubic-out` easing operator support. |
| Interpolation = cubic out | keyframe easing operators (`docs/reference/mlt/keyframe-operators.md`) | **partial** | Easing infra exists; must map "cubic out" and reach the alpha-spot param. |
| Operation = minimum, transition width (soft edges) | `effect_object_mask` params | **missing** | Neither `alpha_operation` nor `transition_width` surfaced by the tool. |
| Fade out embers | `effect_fade(fade_out_frames=...)` | **partial** | Exists (transform-based) but **§1.1 flags affine `rect` property mismatch** — may not render. |
| Flatten (create sequence from selection) | — | **missing** | No sequence/nesting support (survey §Low: sequences deferred). |

### d) Bundle tool spec — `effect_burning_text`

Reproduces the wipe-reveal burn between two text clips plus the animated ember overlay.

```
effect_burning_text(
    workspace_path: str,
    project_file: str,
    top_track: int,                 # white (top) text clip track
    top_clip: int,
    bottom_track: int,              # orange (bottom) text clip track
    bottom_clip: int,
    ember_track: int | None = None, # optional ember overlay footage
    ember_clip: int | None = None,
    luma_mat: str = "clouds",       # wipe mat: "clouds" | path to custom .pgm
    softness: float = 3.0,          # wipe soften (transcript 2–4)
    invert: bool = True,            # burn-away (reveal underlying orange)
    offset_frames: int = 10,        # desync between the two wipes
    ember_rotate: int = 90,         # transform rotation for vertical footage
    ember_luma_threshold: float = 0.2,
    ellipse_grow: bool = True,      # keyframed alpha-shape small→large
    ellipse_easing: str = "cubic_out",
    ember_soft_edges: float = 0.3,  # alpha-shape transition width
    fade_out_frames: int = 12,
    start_frame: int = 0,
    end_frame: int | None = None,
)
```

Composition order (existing + new primitives):
1. `clip_trim` bottom clip to be `offset_frames` longer than top → wipe offset.
2. **NEW** `composite_wipe` extended: wipe on `top_clip` with `luma_mat="clouds"`, `invert=True`, `softness`.
3. **NEW** extended `composite_wipe` on `bottom_clip` (method clouds, softness).
4. Embers (if provided):
   a. **NEW** `effect_transform` — rotate 90°, fit-to-canvas.
   b. **NEW** `effect_luma_key` — black→alpha, `threshold`.
   c. **NEW** animated `effect_alpha_shape` — ellipse, keyframed size small→large, `cubic_out`, `operation=minimum`, `transition_width=ember_soft_edges`.
   d. `effect_fade(fade_out_frames)`.
   e. `composite_set` to layer embers over text (or place on top track).

NEW primitives that must be built first:
- **`composite_wipe` extension**: add `luma_mat`/`luma_resource`, `invert`, `softness` params (currently a fixed single luma, no invert/soften).
- **`effect_luma_key`** wrapper (MLT `lumakey`): `threshold`, `softness`, `invert`.
- **`effect_transform`** wrapper (qtblend/affine): rotation, scale, position, **fit-mode "adjust to original size"**, keyframable.
- **`effect_alpha_shape`** wrapper (frei0r alpha-spot) with `shape` (ellipse), keyframed `size`/`position`, `operation` (min/max/clear), `transition_width`, easing — a superset of today's minimal `effect_object_mask`.
- **Title-clip creation** primitive (survey §6) for the text clips (or require caller to supply them).
- (Optional, "later") **sequence flatten** to mirror "create sequence from selection".

§1.1-broken dependencies: effect-stack root placement (transform, luma-key, alpha-shape, keyframes); `effect_fade` affine `rect` mismatch; composites use `AddComposition`/`luma` transition path (render-unverified via Tier-1 melt, but distinct from the broken `transitions_apply*` crossfade emitter). `clip_speed` not used. Rotoscoping `roto-spline` ParamType gap (§1.3) blocks saving any preset that contains the alpha-shape/roto mask.

---

## Raw data summary

### Video 1 — `effect_fire_text`
- **Effect name:** Fire Text (Burning TV + optional screen-blended stock-flame composite).
- **Missing primitives:** `effect_luma_key` (lumakey wrapper); `effect_burning_tv` wrapper (movement_threshold); `effect_transform` wrapper (rotate/scale/keyframed, fit-mode); title-clip creation primitive.
- **Proposed bundle tool:** `effect_fire_text(workspace_path, project_file, text_track, text_clip, intensity=0.5, flame_track=None, flame_clip=None, blend_mode="screen", start_frame=0, end_frame=None, grade_flames=True, add_burning_tv=True)`.
- **Composes (existing):** `effect_add(BurningTV)`, `effect_tcolor`, `composite_set(blend_mode="screen")`.
- **§1.1-broken deps:** effect-stack root placement (BurningTV/luma/levels/transform); composite render unverified (AddComposition path); `effect_fade` affine mismatch if fades used.

### Video 2 — `effect_burning_text`
- **Effect name:** Burning Text wipe-reveal (clouds-luma wipe between two text clips) + animated ember overlay.
- **Missing primitives:** `composite_wipe` extension (custom luma mat / clouds, `invert`, `softness`); `effect_luma_key`; `effect_transform` (rotate 90 + fit-to-canvas); `effect_alpha_shape` (ellipse, keyframed size, `operation=minimum`, `transition_width`, cubic-out easing); title-clip creation; sequence-flatten (optional).
- **Proposed bundle tool:** `effect_burning_text(workspace_path, project_file, top_track, top_clip, bottom_track, bottom_clip, ember_track=None, ember_clip=None, luma_mat="clouds", softness=3.0, invert=True, offset_frames=10, ember_rotate=90, ember_luma_threshold=0.2, ellipse_grow=True, ellipse_easing="cubic_out", ember_soft_edges=0.3, fade_out_frames=12, start_frame=0, end_frame=None)`.
- **Composes (existing):** `clip_trim` (offset), `composite_wipe` (extended), `composite_set`, `effect_keyframe_set_rect/scalar`, `effect_fade`.
- **§1.1-broken deps:** effect-stack root placement (transform/luma-key/alpha-shape/keyframes); `effect_fade` affine `rect` mismatch; wipe/composite render unverified (AddComposition `luma` path, distinct from broken `transitions_apply*`); rotoscoping `roto-spline` ParamType gap blocks preset capture.
</content>
</invoke>
