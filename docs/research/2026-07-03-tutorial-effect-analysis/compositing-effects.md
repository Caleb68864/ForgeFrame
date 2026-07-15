---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: compositing effects"
author: analysis agent
tags: [kdenlive-mcp, research, compositing, masking, tracking]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
---

# Compositing-Effect Tutorials → MCP Tool Surface Mapping

Three Nuxttux Creative Studio tutorials analysed against the
workshop-video-brain MCP surface (`edit_mcp/server/tools.py`,
`pipelines/compositing.py`, `pipelines/masking.py`, `pipelines/effect_apply.py`,
`pipelines/effect_catalog.py`, `pipelines/effect_wrappers/`).

## Cross-cutting findings (apply to all three videos)

These primitives are named in every transcript and gate every bundle tool below.

| Capability | MCP status | Notes |
|---|---|---|
| **Motion tracker (`opencv.tracker`)** | **MISSING** | Not in `effect_catalog.py` (grep: 0 hits for `opencv.tracker`). Only OpenCV entries are face-blur/face-detect descriptions. §5 of the plan *designs* `subject_track` around `opencv.tracker` but it is **not built**. Every tutorial's "add motion tracker → analyze → copy keyframes → import to transform" flow is unbuildable today. |
| **Keyframed / animated rotoscoping** | **PARTIAL → effectively MISSING** | `mask_set(type="rotoscoping")` exists, but `masking._spline_json` emits **only frame 0** (`{"0": [...]}`). All three tutorials keyframe the roto spline across time (eyes closing, fire mask, smoke edge). Static single-frame masks only. Also the `roto-spline` `ParamType` gap (plan §1.1) keeps rotoscoping out of `effect_catalog`, so it cannot be saved in stack presets. |
| **Import tracker keyframes → transform** | **PARTIAL** | `effect_keyframe_set_rect` can write a rect keyframe string to a `qtblend`/`affine` property, so if tracked rects existed they could be applied. The producer of those rects (the tracker) is missing, so the pair is non-functional end-to-end. |
| **Effect placement renders in Kdenlive** | **BROKEN (plan §1.1)** | `effect_add`, all 22 wrappers, `mask_set`, `mask_apply`, `effect_keyframe_*`, stack ops attach filters at the **MLT root** with custom `track=`/`clip_index=` attrs, not nested in the playlist `<entry>`. May not render at all. This undermines **every** bundle tool proposed here until the §1.1 filter-placement fix lands. |
| **Blend-mode composition ("Cairo blend")** | **EXISTS** | `composite_set(track_a, track_b, blend_mode, geometry)` routes through `BLEND_MODE_TO_MLT`: screen, multiply, lighten, darken, color_burn, overlay, etc. all present (frei0r.cairoblend + qtblend). This is the one heavily-used primitive that is real. |
| **Alpha-shape mask (rect/ellipse/polygon)** | **EXISTS** | `mask_set_shape(shape, bounds, points, feather, feather_passes, alpha_operation)`. |
| **Mask-apply sandwich** | **EXISTS** | `mask_apply(mask_effect_index, target_effect_index)` builds the `mask_start`/`mask_apply` qtblend sandwich (subject to §1.1 root-placement risk). |
| **Extract frame → project bin asset** | **MISSING** | No tool grabs a still from a clip into the bin. Plan §5 proposes `subject_locate_frames` (ffmpeg extract) but it is not built. Needed for object-removal-with-motion and the frozen-patch technique. |
| **Clip duplicate to another track (trimmed)** | **MISSING** | No copy-clip-to-track-N primitive; `clip_move` is same-track only (plan §3). Used as a tracking-perf trick (video 1) and to layer smoke (video 3). |
| **Lift/Gamma/Gain color wheels** | **PARTIAL** | No `lift_gamma_gain` in catalog. `effect_add("lift_gamma_gain", …)` would pass the raw service string through unvalidated; nearest catalog entries are `avfilter.colorbalance` (Color balance) and `frei0r.threelay0r`. Used in videos 1 and 3. |
| **Curves (with Alpha channel)** | **MISSING** | No `avfilter.curves`/`frei0r.curves` in catalog. Video 3 uses curves on the **Alpha** channel to control smoke opacity — no equivalent. |
| **Keyframable effect-param wrappers** | **MISSING** | Generated wrappers accept static values only (plan §3 "Keyframable effect wrappers"). Video 3 animates Edge-Glow amplitude 7→15 / frequency 80→120 — cannot be expressed. |

Named-effect availability (via generic `effect_add` / wrappers):

- **Levels** → `avfilter.colorlevels` ✅ (catalog).
- **Colorize** → `avfilter.colorize` ✅ and a frei0r "Colorize" ✅.
- **Saturation** → `frei0r.saturat0r` ✅.
- **Gaussian blur** → `avfilter.gblur` ✅.
- **Edge glow** → `frei0r.edgeglow` ✅ (wrapper `effect_frei0r_edgeglow`), but static only.
- **Glow / "soft glow"** → `frei0r.glow` ✅ (Glow). No dedicated `softglow`; "soft glow" is an approximation.
- **Vignette** → `frei0r.vignette` ✅. **Letterbox** → `frei0r.letterb0xed` ✅ (wrapper).
- **Corners** → `frei0r.c0rners` ✅. **Horizontal flip** → `frei0r.mirr0r` (wrapper `effect_frei0r_mirr0r`) ~partial.
- **Brightness** → `avfilter.eq` (Brightness/contrast/gamma/saturation) ✅.
- **CMYK adjust** → **MISSING** (no catalog hit). **Video noise generator** → MISSING (producer, not a filter).
- **Composite & Transform transition + horizontal flip + keyframed transform** = `composite_set` + effect + `effect_keyframe_set_rect`, all present but placement-risky.

---

## Video 1 — "Compositing Challenge: Lucifer Eyes" (S8-GYX2AYnM, 21:38)

The most complex of the three: rotoscoped + tracked recolored eyes, tracked pupil
overlays, keyed/graded background, nested sequences, CRT-screen comp.

### a) Technique breakdown

1. **[00:46]** Source clip is 17:9 inside a 16:9 project (black bars). Fix with the
   **built-in Transform** (enabled via Settings → Configure → *Enable built-in
   effects*): magnifier "fit height" then center, or "adjust & center in frame".
2. **[02:19]** **Rotoscoping** effect on the right eye. Left-click to drop spline
   points, right-click to close. Set **Alpha operation = Add** to preview. **Feather
   width = 1**, **Feather passes = 2**. Add points (double-click line), delete
   (double-click point), curve via handles.
3. **[03:50]** Animate the mask: move a few frames, drag the whole selection (center
   X handle), **add keyframe** (manual, or auto-keyframes toggle). Keyframe the spline
   through the shot until the eyes close.
4. **[05:23]** **Motion Tracker** on the iris: place seed rect at the eye corner,
   **keyframe spacing = 3**, **algorithm = KCF**.
5. **[06:08]** Perf trick: **duplicate the clip to a new track below**, trim to the
   VFX zone, run **"Analyze to apply effect"** on that short copy (less to analyze).
6. **[06:53]** Repeat rotoscope + motion tracker for the other (top) eye.
7. **[07:38]** Set a **timeline zone** + **timeline preview render** (pre-render for
   smooth playback).
8. **[08:23]** Recolor option A — "mask-apply sandwich": `mask_apply` at bottom,
   `rotoscoping` above it, **Colorize** above the mask-apply and under the roto;
   modes **minimum** then **add**.
9. **[09:11]** Recolor option B (chosen): a **solid color clip** above; drag-drop the
   rotoscopes onto it; cut at the end of the VFX zone; **Composition → Cairo blend →
   Color burn**, control opacity.
10. **[10:00]** Optional iris exclusion: **Alpha shape (ellipse, Subtract)** over the
    iris, tracked to follow it.
11. **[10:43]** Pupils/iris: **insert 2 tracks**; a red-colorized iris image; **built-in
    transform** scale ≈4.5; lower opacity to align.
12. **[11:29]** From the eye's motion tracker: hamburger → **Copy all keyframes to
    clipboard**; disable tracker. On the pupil add a **Transform**; hamburger → **Import
    keyframes** → map **Position**, **Center → center to rectangle**, **uncheck "limit
    keyframe number"**, use **offset sliders** to place.
13. **[12:14]** Duplicate pupil to track above; reset transform; second motion tracker
    → import for the other eye. Uses **two transforms** — one carries the tracked
    position, the second scales the object (tracker follows position, not size).
14. **[13:47]** Manual X/Y keyframe corrections.
15. **[14:00]** Transfer rotoscopes onto the iris clips; **Alpha operation = minimum**;
    **Alpha operation "shrink soft"** to trim spill; can stack two alpha operations.
16. **[15:18]** Blend iris with the real eye: **Composition → Cairo blend → Lighten**,
    composite track = V3.
17. **[16:50]** Background: **Chroma key** (remove red, lower variance) → **Alpha
    operations** to soften edges → **Blur** on hair edges → **CMYK adjust** (relative,
    remove reds) → **Lift/Gamma/Gain** (shadows −red +blue; gamma −brightness/−red;
    gain −red +green).
18. **[18:22]** Background solid color + **Colorize** + **Video noise generator**
    (uniform, to kill vignette banding) + **Vignette**.
19. **[18:22]** Nest into **Sequences** (comp1, comp2).
20. **[19:07]** comp2: **Corners** effect to deform footage into the TV screen +
    Transform (scale down) + **Rotoscope** to match the screen + Alpha op soften.
21. **[19:52]** Scene bg: **Brightness** + **Lift/Gamma/Gain** + **LUT** for final look;
    top clip **Composition → Cairo blend → Screen**.
22. **[20:00]** CRT **"Shut off"** old preset/template (downloaded from an older
    Kdenlive to keep in library).
23. **[20:38]** Sequence1: **Soft glow** on the screen (ghostly) + **Transform** zoom
    in/out. **Master track**: **Vignette** + **Letterbox** (black bars).

### b) Kdenlive features/effects named

Built-in Transform; Rotoscoping (alpha operation add/minimum/shrink-soft, feather
width/passes, animated spline keyframes, handles); Motion Tracker (KCF, keyframe
spacing, analyze-to-apply); clip duplication to track; timeline zone + preview
render; Mask apply; Colorize; solid color clip; Composition track / Cairo blend
(color burn, lighten, screen); opacity; Alpha shape (ellipse, subtract); import
keyframes → Transform (position map, center-to-rect, unlimited keyframes, offset);
dual-transform track+scale; Chroma key (key/variance); Alpha operations; Blur; CMYK
adjust; Lift/Gamma/Gain; Video noise generator; Vignette; Sequences / nested comps;
Corners; Brightness; LUT; "Shut off" CRT template; Soft glow; Letterbox; Master-track
effects.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Built-in transform scale-to-fit | `effect_add("affine"/"qtblend")` + `effect_keyframe_set_rect` | partial | affine exists; no "fit height/center" helper; static geometry only. §1.1 placement. |
| Rotoscoping right/left eye | `mask_set(type="rotoscoping", params)` | partial | Exists but **frame-0-only spline**; no animated keyframes for eye-close. |
| Animate roto over time | — | **missing** | `_spline_json` writes single keyframe. |
| Motion tracker (iris) | — | **missing** | no `opencv.tracker`. |
| Duplicate clip to lower track, trim | — | **missing** | no cross-track duplicate; `clip_move` same-track only. |
| Analyze-to-apply tracking | — | **missing** | tracker missing. |
| Timeline zone + preview render | `render_preview` (~) | partial | previews whole workspace, not a zone. |
| Mask-apply sandwich (recolor) | `mask_apply` + `mask_set` + `effect_add("avfilter.colorize")` | partial | sandwich + colorize exist; §1.1 placement; alpha-op mode routing manual. |
| Solid color clip + drag rotoscopes | — | **missing** | no solid-color producer insertion tool. |
| Composition → Cairo blend (burn/lighten/screen) | `composite_set(blend_mode=…)` | **exists** | color_burn/lighten/screen all mapped. |
| Alpha shape ellipse subtract (iris) | `mask_set_shape("ellipse", alpha_operation="sub")` | exists | static only; tracking it = missing. |
| Insert 2 tracks | `track_add` (×2) | exists | — |
| Red iris image, scale, opacity | `effect_add("avfilter.colorize")` + affine | partial | no bin-image-insert-and-scale bundle. §1.1. |
| Copy tracker kf → import to Transform | `effect_keyframe_set_rect` | partial | consumer exists; producer (tracker) missing. |
| Dual transform (track + scale) | `effect_add` ×2 + `effect_keyframe_set_rect` | partial | expressible if tracked rects existed. |
| Manual X/Y kf correction | `effect_keyframe_set_rect(mode="replace")` | exists | — |
| Alpha op minimum / shrink-soft | `mask_set_shape(alpha_operation=…)` | partial | "shrink soft" morphology not modelled. |
| Chroma key bg | `effect_chroma_key(color,tolerance)` | exists | variance≈tolerance; §1.1 placement. |
| Blur hair edges | `effect_add("avfilter.gblur")` | exists | — |
| CMYK adjust | — | **missing** | no CMYK service in catalog. |
| Lift/Gamma/Gain | `effect_add("lift_gamma_gain")` | partial | not in catalog; unvalidated passthrough. |
| Video noise generator | — | **missing** | producer, not modelled. |
| Vignette / Letterbox | `effect_add("frei0r.vignette")` / `effect_frei0r_letterb0xed` | exists | — |
| Sequences / nested comps | — | **missing** | parser assumes single tractor (plan §3 Low). |
| Corners deform | `effect_add("frei0r.c0rners")` | exists | static; keyframed corners = partial. |
| Brightness | `effect_add("avfilter.eq")` | exists | — |
| LUT | `color_apply_lut` | exists | — |
| Soft glow | `effect_add("frei0r.glow")` | partial | Glow ≠ soft-glow; approximation. |
| CRT "shut off" template | — | **missing** | template-clip library not modelled. |
| Master-track effects | — | **missing** | no master/tractor-level effect target. |

### d) Bundle tool spec — `effect_glow_eyes`

Composes the core recolored-eye effect (rotoscope both eyes → recolor via graded
solid over a tracked mask → optional tracked pupil overlay).

```
effect_glow_eyes(
  workspace_path: str,
  project_file: str,
  track: int,
  clip: int,
  eye_masks: str,               # JSON: [{"points_by_frame": {...}}, ...] per eye, animated spline
  color: str = "#7a0000",       # target eye color (colorize hue)
  blend_mode: str = "color_burn", # cairoblend mode for the recolor over the eye
  opacity: float = 1.0,
  glow: float = 0.4,            # frei0r.glow strength on the recolored layer
  pupil_image: str = "",        # optional bin asset for tracked iris overlay
  tracker_algo: str = "KCF",
  keyframe_spacing: int = 3,
  feather: int = 1,
  feather_passes: int = 2,
)
```

Composes existing primitives, in order: `track_add` (recolor + pupil tracks) →
`mask_set(type="rotoscoping")` per eye → `effect_add("avfilter.colorize")` →
`mask_apply` sandwich → `composite_set(blend_mode)` for the graded layer →
`effect_add("frei0r.glow")` → (pupil) `effect_keyframe_set_rect` on a transform.

**NEW primitives required first:**
- `motion_track` (opencv.tracker headless: seed rect + algo + spacing → keyframed rects). **CRITICAL, blocks the tracked-pupil and tracked-mask paths.**
- animated/keyframed rotoscoping (multi-frame `roto-spline`) — the whole point of "eyes closing".
- `clip_duplicate_to_track` (tracking-perf trick, and pupil-on-second-track).
- solid-color producer insert (graded recolor layer).
- `lift_gamma_gain` catalog entry; CMYK-adjust effect; video-noise producer (grade fidelity, optional).
- import-tracker-keyframes → transform bridge (pupil follow).

**§1.1-broken dependencies:** effect/mask/keyframe root-placement (all steps);
`mask_apply` qtblend-in-stack; `composite_set` transition placement (verify);
`effect_fade`/affine if fades added. Nested-sequence output is unsupported (single-tractor parser).

---

## Video 2 — "How to Remove Objects From Video" (d8gj-DjdWgM, 3:07)

Patch-over object removal: cover an object with a clean patch of background,
static then tracked.

### a) Technique breakdown

1. **[00:00]** Static tripod clip. Effects → **Mask**: **Alpha-shapes mask** (or
   Rotoscoping for complex shapes). Then **Mask apply**, then a **Transform**
   *between* the two.
2. **[00:45]** Place the **alpha shape** over the object to gauge size; **disable
   mask apply** to view the selection; adjust edge feather via the **transition
   width slider**. Move the shape to a **clean area of background** (the patch
   source). On the **Transform**, adjust **X/Y** to move that patch over the object.
3. Extend the alpha shape, or make a **new stack with the same effects** using an
   **ellipse** to cover a second object (the clock).
4. **[01:31]** Clip with camera motion: **Extract frame to project** (right-click
   monitor → *Extract Frame to Project*), save near project. Place the still over the
   clip, **match length**. Add the same effects **minus mask apply** (rotoscoping or
   alpha shape). **Ellipse** over the clock; move to the side.
5. **Disable top track**; add **Motion tracker** to the video clip beneath; track
   near the object (the clock); **KCF**.
6. **[02:16]** **Copy all keyframes** (hamburger) → clipboard; disable tracker; enable
   top track. **Import keyframes** to the Transform; **uncheck limit keyframe number**;
   **map = Position**; **Top-Center** for both; **offset** until patch covers the clock.
7. **Levels** effect under the Transform; nudge **gamma** down to match wall brightness.
8. Nest the two clips into a **sequence**.

### b) Kdenlive features/effects named

Alpha-shapes mask (rect/ellipse/triangle); Rotoscoping mask; Mask apply; Transform
(X/Y position); feather via transition-width slider; Extract Frame to Project;
Motion tracker (KCF, keyframe spacing); Copy/Import keyframes (map position,
top-center, unlimited); Levels (gamma); Sequence nesting.

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Alpha-shapes mask over object | `mask_set_shape("rect"/"ellipse", bounds, feather)` | exists | triangle not in shape set; §1.1 placement. |
| Mask apply | `mask_apply(mask_effect_index, target_effect_index)` | exists | §1.1 qtblend-in-stack risk. |
| Transform between mask+apply (patch move) | `effect_add("affine")` + `effect_keyframe_set_rect` | partial | expressible; ordering-between-filters via `effect_reorder`. |
| Feather via transition-width | `mask_set_shape(feather=…)` | partial | maps to feather, slider semantics approximate. |
| Second object (ellipse, new stack) | `mask_set_shape("ellipse")` + `mask_apply` | exists | repeat the sandwich. |
| **Extract frame to project** | — | **missing** | no still-grab-to-bin tool (plan §5 designs it). |
| Place still over clip, match length | `clip_insert` (+ trim) | partial | insert exists; auto-match-length missing. |
| Motion tracker on underlying clip | — | **missing** | no opencv.tracker. |
| Copy → import tracker keyframes to Transform | `effect_keyframe_set_rect` | partial | consumer only; producer missing. |
| Levels gamma match | `effect_add("avfilter.colorlevels")` | exists | — |
| Nest into sequence | — | **missing** | single-tractor parser. |

### d) Bundle tool spec — `effect_object_remove`

```
effect_object_remove(
  workspace_path: str,
  project_file: str,
  track: int,
  clip: int,
  object_bounds: str,           # JSON rect [x,y,w,h] normalized: object to cover
  patch_source_offset: str,     # JSON [dx,dy]: vector to a clean background patch
  shape: str = "ellipse",       # rect|ellipse
  feather: int = 20,
  track_object: bool = False,   # if camera moves: extract frame + motion-track
  tracker_algo: str = "KCF",
  keyframe_spacing: int = 5,
  brightness_match: float = 0.0, # levels gamma nudge to blend the patch
)
```

Static path composes: `mask_set_shape(shape, bounds=object_bounds, feather)` →
`effect_add("affine")` (patch = shape moved by `patch_source_offset`, applied via
`effect_keyframe_set_rect`) → `mask_apply` → `effect_add("avfilter.colorlevels")`
for gamma match. Motion path additionally: extract still → place on a new top
track (`track_add`, `clip_insert`) → `motion_track` the underlying clip → import
rects into the patch transform.

**NEW primitives required first:**
- `extract_frame_to_project` (ffmpeg still → bin asset; adapter exists, no tool).
- `motion_track` (opencv.tracker) — needed for `track_object=True`.
- match-length clip insert helper (place still spanning the clip).

**§1.1-broken dependencies:** mask/`affine`/levels root-placement; `mask_apply`
qtblend-in-stack; nested-sequence output unsupported. The **static path is the
closest-to-shippable bundle of all three** once §1.1 placement is fixed — it needs
no tracker.

---

## Video 3 — "Composite Fire Into Your Scenes" (mfF_DEGylqY, 9:03)

Tracked fire + smoke overlay graded and masked into a live-action door scene.

### a) Technique breakdown

1. **[00:10]** Add clips; use a **zone** to import just the video (skip the black
   first frame) via the film icon.
2. **[00:55]** Fire overlay prepped in the **project bin** with two effects: **Levels**
   (raise **input black level** — the "black" around the flame isn't pure black) and
   **Rotoscoping** (**alpha operation = minimum**) to exclude an unwanted lower flame.
   Import just the video; place above clip 1; trim.
3. **[01:00]** Click the **purple dot** (bottom-left of top clip) → adds a **transition**;
   switch **Wipe → Composite and Transform**; set **compositing = Screen**.
4. **[01:40]** Use **Composite and Transform** to position/scale/rotate the flame;
   add a **Horizontal flip** to the fire; place the flame on the door.
5. **[02:00]** Fire doesn't stick. Disable fire track; on clip 1 add **Motion tracker**;
   scale/reposition the red rect on something **static**; algo options (**DaSiamRPN /
   Nano** are AI, need libraries; **KCF** used); **keyframe spacing** (smaller = shakier
   footage); **Analyze to apply effect**.
6. **[02:25]** **Copy keyframes**; **disable** tracker (don't delete). **Import keyframes**
   into the **Composite and Transform** layer: **data = rectangle**, **map = Position**,
   **Center → center**, **uncheck limit keyframe number**; **offset** to fix position.
7. **[03:10]** Add a **Transform** to the fire to manually correct position/scale as the
   camera dollies (perspective change).
8. **[03:57]** Blend: **Saturation** (lower) → **Lift/Gamma/Gain** (tweak colors) →
   **Gaussian blur** X/Y = 3.
9. **[03:57]** Fix shaky track: re-track something else; **remove all keyframes after
   cursor** (hamburger); re-import.
10. **[04:42]** Smoke behind fire: move fire+composite to the track above; change
    **composite track** from **Automatic → V1**. Smoke asset has **Rotoscoping**
    (**subtract**, feather) in the bin; drag to timeline, match length; add
    **Composite and Transform → Multiply** (bg is white); position/scale/rotate.
11. **[05:27]** Add **Rotoscoping** to smoke to mask the top edge; the mask misbehaves
    because it acts on the **original** position, not the transform result — move the
    composite layer aside, adjust mask, move back; set **rotoscoping = minimum**.
    Import the earlier keyframes into the smoke's composite layer; drag the fire's
    **corrective Transform** onto the smoke; add another Transform to nudge it up.
12. **[06:13]** **Curves** (channel = **Alpha**) for smoke opacity; **Lift/Gamma/Gain**
    to add red.
13. **[06:13]** Make fire part of the scene: on clip 1 add **Rotoscoping mask** +
    **Mask apply**; between them **Colorize** + **Edge glow** + a **dark** effect;
    colorize hue to fire; edge glow **low threshold**, **bump brightness**, **down
    scaling = min**; **animate** amplitude **7→15**, frequency **80→120** (keyframes).
    Roto mask around the fire, keyframe through, add feather.
14. **[07:47]** Speed change: **Ctrl-drag** clip edge to change speed (percentage
    shown); keyframes on other effects **get displaced**; workaround: re-drag the
    corrective Transform back on.

### b) Kdenlive features/effects named

Zone import (film icon); Levels (input black level); Rotoscoping (alpha op
minimum/subtract, feather, keyframed spline); Composite & Transform transition
(Screen / Multiply blend); Horizontal flip; Motion tracker (KCF, DaSiamRPN/Nano,
keyframe spacing, analyze-to-apply, remove-keyframes-after-cursor); Copy/Import
keyframes (rectangle, position, center); corrective Transform (perspective);
Saturation; Lift/Gamma/Gain; Gaussian blur; Composite-track selection
(Automatic/V1); Curves (Alpha channel); Colorize; Edge glow (animated
amplitude/frequency); Mask apply; clip speed (Ctrl-drag).

### c) Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Zone import (skip black frame) | `clip_insert` + `clip_trim` | partial | no zone-based selective import. |
| Levels (input black level) | `effect_add("avfilter.colorlevels")` | exists | — |
| Rotoscoping exclude flame (min) | `mask_set(type="rotoscoping", alpha_operation="min")` | partial | static frame-0 spline only. |
| Composite & Transform (Screen/Multiply) | `composite_set(blend_mode="screen"/"multiply", geometry)` | exists | blend + geometry present. |
| Horizontal flip on fire | `effect_frei0r_mirr0r` / `effect_add("frei0r.mirr0r")` | partial | mirror wrapper ≈ flip; verify axis param. |
| Motion tracker on scene | — | **missing** | no opencv.tracker (KCF/DaSiam/Nano all absent). |
| Analyze-to-apply / remove kf after cursor | — | **missing** | tracker + kf-trim ops absent. |
| Copy → import tracker kf to composite | `effect_keyframe_set_rect` | partial | consumer only; producer missing. |
| Corrective Transform (perspective) | `effect_add("affine")` + `effect_keyframe_set_rect` | partial | manual kf expressible; §1.1. |
| Saturation | `effect_add("frei0r.saturat0r")` | exists | — |
| Lift/Gamma/Gain | `effect_add("lift_gamma_gain")` | partial | not in catalog; passthrough. |
| Gaussian blur X/Y=3 | `effect_add("avfilter.gblur")` | exists | — |
| Composite-track Automatic→V1 | `composite_set(track_a, track_b)` | partial | explicit tracks yes; "automatic" mode + track-broke-on-move workflow not modelled. |
| Curves on Alpha channel (smoke opacity) | — | **missing** | no curves effect in catalog. |
| Colorize | `effect_add("avfilter.colorize")` | exists | — |
| Edge glow animated amp/freq | `effect_frei0r_edgeglow` | partial | wrapper is **static** — cannot animate 7→15 / 80→120. |
| Roto mask + mask apply on fire | `mask_set(rotoscoping)` + `mask_apply` | partial | static spline; §1.1 placement. |
| Clip speed change (smoke) | `clip_speed` | **broken (§1.1)** | writes bogus `<filter type="speed">`; no-op in editor. Needs `timewarp` producer. |

### d) Bundle tool spec — `effect_composite_fire`

```
effect_composite_fire(
  workspace_path: str,
  project_file: str,
  scene_track: int,             # live-action base clip
  overlay_asset: str,           # fire clip (bin/media asset)
  smoke_asset: str = "",        # optional smoke asset
  blend_mode: str = "screen",   # fire→screen, smoke→multiply
  position: str = "",           # JSON rect for placement/scale/rotate
  flip_horizontal: bool = False,
  input_black_level: float = 0.05, # levels lift to clean the overlay's near-black
  track_algo: str = "KCF",
  keyframe_spacing: int = 5,
  saturation: float = 0.6,
  blur: float = 3.0,
  color_grade: str = "",        # JSON lift/gamma/gain to marry fire to scene
  edge_glow: str = "",          # JSON {amp:[7,15], freq:[80,120]} animated
)
```

Composes, in order: `track_add` (overlay/smoke tracks) → `effect_add("avfilter.colorlevels")`
(black-level clean) → `mask_set(rotoscoping)` (exclude unwanted flame) → `clip_insert`
overlay → optional `effect_frei0r_mirr0r` → `composite_set(blend_mode, geometry=position)`
→ `motion_track` scene → import rects via `effect_keyframe_set_rect` on the composite
→ `effect_add("frei0r.saturat0r")` + lift/gamma/gain + `effect_add("avfilter.gblur")`
→ scene-integration roto+`mask_apply` sandwich with `avfilter.colorize` +
`frei0r.edgeglow`. Smoke path mirrors the fire path with `blend_mode="multiply"` and
a curves-alpha opacity step.

**NEW primitives required first:**
- `motion_track` (opencv.tracker) — **CRITICAL**; the fire/smoke "stick to the door" is the whole trick.
- keyframable Edge-Glow wrapper (animate amplitude/frequency) — static wrapper can't do the 7→15 / 80→120 animation.
- curves effect with **Alpha** channel (smoke opacity).
- animated/keyframed rotoscoping (fire mask through the shot).
- `lift_gamma_gain` catalog entry.
- match-length overlay insert; horizontal-flip verified (`frei0r.mirr0r` axis).

**§1.1-broken dependencies:** effect/mask/keyframe root-placement (whole chain);
`mask_apply` qtblend-in-stack; **`clip_speed` is on the broken list** (smoke speed step
is a no-op until `timewarp` lands); `composite_set` transition placement to verify.

---

## Raw summary (per video)

### Video 1 — Lucifer Eyes
- **Effect name:** `effect_glow_eyes` (rotoscoped + tracked recolored eyes / pupil overlay)
- **Missing primitives:** motion_track (opencv.tracker); animated rotoscoping; clip_duplicate_to_track; solid-color producer insert; lift_gamma_gain catalog entry; CMYK-adjust effect; video-noise producer; nested sequences; master-track effect target; CRT-template clip library; import-tracker-kf→transform bridge
- **Bundle tool:** `effect_glow_eyes(workspace_path, project_file, track, clip, eye_masks, color="#7a0000", blend_mode="color_burn", opacity=1.0, glow=0.4, pupil_image="", tracker_algo="KCF", keyframe_spacing=3, feather=1, feather_passes=2)`
- **§1.1-broken deps:** effect/mask/keyframe root-placement; mask_apply qtblend-in-stack; composite_set transition placement (verify); effect_fade affine/rect if fades used

### Video 2 — Object Removal
- **Effect name:** `effect_object_remove` (patch-over cover, static + tracked)
- **Missing primitives:** extract_frame_to_project; motion_track (opencv.tracker); match-length clip insert; nested sequences; triangle alpha shape
- **Bundle tool:** `effect_object_remove(workspace_path, project_file, track, clip, object_bounds, patch_source_offset, shape="ellipse", feather=20, track_object=False, tracker_algo="KCF", keyframe_spacing=5, brightness_match=0.0)`
- **§1.1-broken deps:** mask/affine/levels root-placement; mask_apply qtblend-in-stack. (Static path is closest-to-shippable — needs no tracker.)

### Video 3 — Fire Compositing
- **Effect name:** `effect_composite_fire` (tracked fire + smoke overlay, graded/masked)
- **Missing primitives:** motion_track (opencv.tracker; KCF/DaSiamRPN/Nano); keyframable edge-glow wrapper; curves-with-Alpha effect; animated rotoscoping; lift_gamma_gain catalog entry; match-length overlay insert; verified horizontal flip; remove-keyframes-after-cursor op; zone-selective import
- **Bundle tool:** `effect_composite_fire(workspace_path, project_file, scene_track, overlay_asset, smoke_asset="", blend_mode="screen", position="", flip_horizontal=False, input_black_level=0.05, track_algo="KCF", keyframe_spacing=5, saturation=0.6, blur=3.0, color_grade="", edge_glow="")`
- **§1.1-broken deps:** effect/mask/keyframe root-placement; mask_apply qtblend-in-stack; **clip_speed no-op (smoke speed step)**; composite_set transition placement (verify)

### Shared critical blocker
`motion_track` (MLT `opencv.tracker`) is **absent from the entire codebase** and is
required by all three effects. Plan §5 designs it (`subject_track`) but it is unbuilt.
It is the single highest-leverage new primitive for this tutorial cluster.
