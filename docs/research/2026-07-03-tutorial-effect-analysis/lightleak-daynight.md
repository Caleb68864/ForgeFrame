---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: additive-overlay looks (light leaks + day-to-night)"
author: analysis agent
tags: [kdenlive-mcp, research, compositing, blend-modes, color-grade, overlay]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_scout: "vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md"
sources:
  - "vault/Transcripts/Kdenlive Tutorials/Using Screen-Lighten Blend mode transition to include light leaks in KDENLIVE 2020.md"
  - "vault/Transcripts/Kdenlive Tutorials/From Day to Night - kdenlivetutorials Blog.md"
video: -3TjF3OzECc
channel: Fabiano
blog: https://www.kdenlivetutorials.com/2014/11/from-day-to-night/
built_tools: [effect_light_leak, effect_day_to_night]
---

# Additive-Overlay Looks → MCP Tool Surface Mapping

Two tutorials from the scout landscape (`vault/Research/Kdenlive Tutorial
Landscape - Uncovered Effects.md`: top-5 item #5, tutorials #12 + #13) share one
**additive-overlay** pattern — lay a second clip on a track *above* the base
footage and composite it with a **lightening** blend mode (Screen / Lighten /
Add) so only the bright parts of the upper layer bleed through:

* **Light leaks** — Fabiano's *"Using Screen/Lighten Blend mode transition to
  include light leaks in KDENLIVE"* (`-3TjF3OzECc`). A light-leak / lens-flare
  clip over the footage, blended with **Screen** or **Lighten**.
* **Day → night** — the kdenlivetutorials.com *"From Day to Night"* blog. A
  hue/saturation/levels grade toward a dark blue night, then a starry-**sky
  overlay** composited on a track above (Darken/Lighten/Invert/Box-Blur passes).

The overlay-blend and whole-frame grade layers are buildable today on the
existing `apply_composite` (blend-mode) pipeline + effect-insertion + keyframe
machinery. The only pieces that hit known blockers are the blog's *animated
rotoscoping* stages (subject-scoped brightening). This report ships the
achievable subsets as **`effect_light_leak`** and **`effect_day_to_night`** and
documents the omissions.

## Technique breakdown

### Light leaks (video `-3TjF3OzECc`)

1. **Add a light-leak / lens-flare clip** on a track *above* the footage
   (drag from the project bin; set the I/O zone before inserting).
2. **Composite the two tracks** and set the composition/transition **blend mode
   to Screen or Lighten** — only the bright leak pixels show through; blacks drop
   out. Screen for a soft additive bloom, Lighten for a harder max-of-both look.
3. **Motivation** — the presenter stresses having a bright in-frame source (sun,
   window) so the leak reads as real light, not an obvious overlay. Also usable
   as a bright wash *transition* between two shots.

Named effects: **Screen** / **Lighten** (composition blend mode). No colour
filters — the whole look is the blend mode on an overlay clip.

### Day → night (blog)

1. **[grade]** On the day clip: add **Saturation** + **Hue Shift** effects
   (values set below).
2. **[grade]** **Levels** on the **Luma** channel — raise incoming black (~120)
   to darken the whole frame.
3. **[grade]** Second **Levels** on the **Red** channel (incoming black ~125,
   white ~915) to boost red contrast for a colder residual.
4. **[grade]** Set **Saturation below 100 (~80)** (desaturate) and push **Hue
   Shift toward blue** (the classic day-for-night blue cast).
5. **[render]** Render the graded plate to a high-quality MP4 as the new base.
6. **[sky]** Place a **starry-sky image** on the track *above* (Video2), graded
   movie below (Movie3); apply a **Darken** transition full-length. Re-add the
   movie on Video1 with a **Lighten** transition; add **Invert** to reveal the
   stars through the dark sky; apply **Box Blur** (factor 5, vertical ×3,
   horizontal ×1) to soften the join.
7. **[distance brightness]** Overlap the render on two tracks with a
   **Composite** transition; **Curves** on **Luma** (shadows/mids low, highlights
   high) on the top clip; add a **Rotoscoping** mask *with keyframes* so only
   foreground objects stay bright; render; optionally fine-tune **Luma** / **Blue**
   with Curves.

Named effects: **Saturation**; **Hue Shift**; **Levels** (Luma, Red); **Darken**
/ **Lighten** / **Composite** transitions; **Invert**; **Box Blur**; **Curves**
(Luma); **Rotoscoping** (keyframed).

## Capability mapping

| Step | Kdenlive effect | MCP surface | Status | Why |
|---|---|---|---|---|
| Overlay clip on a track above | drag clip to upper track | model-level insert in `pipelines/overlay_looks.insert_overlay_clip` / **`effect_light_leak`** | **built** | `clip_insert` only targets the first video track (known gap); insert done against the model directly, like `_apply_add_clip`, without touching patcher/serializer. |
| Screen / Lighten blend | composition blend mode | `composite_set` / `apply_composite` (`frei0r.cairoblend` `1=screen\|lighten`) / **`effect_light_leak`** | **exists** | `BLEND_MODE_TO_MLT` already maps `screen`/`lighten`/`add`. |
| Overlay opacity | composition alpha | geometry `:NN` suffix / **`effect_light_leak`** (`opacity`) | **built** | opacity 0..1 → geometry 0..100. |
| Leak fade in/out | opacity keyframes | `build_fade_keyframes` + `affine`/`transform` rect / **`effect_light_leak`** (`fade_in/out_frames`) | **built** | reuses the proven `effect_fade` keyframe path on the overlay clip. |
| Desaturate + darken | Saturation + Levels(Luma) | `avfilter.eq` (`av.saturation`, `av.brightness`, `av.contrast`) / **`effect_day_to_night`** | **built** | one eq filter distils Saturation + Levels-darken. |
| Hue toward blue | Hue Shift + blue Levels(Red) | `frei0r.colorize` (hue ≈ 0.62 blue) / **`effect_day_to_night`** | **built** | colorize gives the blue night tint; per-channel Levels(Red) is not a small honest scalar surface (same reasoning as `color_grade` dropping `avfilter.colorbalance`/`curves`). |
| Ramped day→night | keyframed grade | `keyframes.build_keyframe_string` / **`effect_day_to_night`** (`keyframed=True`) | **built** | eq brightness/saturation/contrast + colorize saturation ramp neutral→night across the clip. |
| Sky overlay | sky clip on track above + Darken/Lighten | shared `insert_overlay_clip` + `apply_composite` / **`effect_day_to_night`** (`sky_media`) | **built** | same additive-overlay helper as the light leak. |
| Invert / Box Blur sky join | Invert + Box Blur | `avfilter.negate` / `boxblur` (exist in catalog) | **not folded in** | left to the operator; the additive Screen/Lighten composite is the honest single-mode subset of the blog's multi-pass Darken+Lighten+Invert join. |
| Distance brightness | Composite + Curves + **animated Rotoscoping** | — | **blocked** | per-frame roto is the shared hard blocker (`masking._spline_json` emits frame 0 only). Subject-scoped brightening is not achievable; the grade is whole-frame. |

**§1.1/§1.2 placement (known, not a blocker):** `apply_composite` addresses
tracks by index and the transition/filter XML lands at the MLT root rather than
nested in the `<tractor>` / playlist `<entry>` (§1.1/§1.2 of
`docs/plans/2026-07-03-kdenlive-mcp-improvements.md`). Both tools inherit this;
they still write well-formed XML that relocates correctly once the placement fix
lands. Composite `a_track`/`b_track` are the passed video-track indices (same
convention as `composite_set`).

## Bundle tool specs — BUILT

```
effect_light_leak(
  workspace_path: str,
  project_file: str,
  leak_media: str,          # light-leak / lens-flare clip
  target_track: int,        # base footage (layer below)
  at_frame: int,            # start frame on the overlay track
  overlay_track: int = -1,  # -1 => target_track + 1 (must already exist)
  blend_mode: str = "screen",   # screen | lighten | add
  opacity: float = 1.0,     # composite opacity 0..1 -> geometry 0..100
  fade_in_frames: int = 0,
  fade_out_frames: int = 0,
  duration_frames: int = 120,
) -> dict
```

```
effect_day_to_night(
  workspace_path: str,
  project_file: str,
  track: int,
  clip_index: int,
  intensity: float = 0.5,   # how far toward night (0..1)
  sky_media: str = "",      # optional sky overlay clip
  keyframed: bool = True,   # ramp neutral(day)->night across the clip
  blend_mode: str = "screen",   # sky composite (screen | lighten | add)
  overlay_track: int = -1,  # -1 => track + 1
  sky_at_frame: int = 0,
  sky_duration_frames: int = 120,
) -> dict
```

Both built on `pipelines/overlay_looks.py` (pure): `LIGHT_LEAK_BLEND_MODES`,
`overlay_geometry`, `insert_overlay_clip` (model-level playlist-targeted insert),
`day_to_night_chain` (static or keyframed grade), `lookup_catalog_id`,
`build_filter_xml`. The bundle module `server/bundles/overlay_looks.py` does the
single snapshot + XML I/O and returns `_ok`/`_err`, reusing `apply_composite`
(compositing pipeline), `build_fade_keyframes` (effect_presets) and
`build_keyframe_string` (keyframes).

### Omitted sub-effects (documented; not built as broken pretend-functionality)

- **Day→night distance-brightness stage** (Composite + Curves + **animated
  Rotoscoping** to keep foreground objects bright). Per-frame roto is the shared
  hard blocker; the grade is applied whole-frame. Add static region-scoping
  separately via `mask_set` / `mask_apply`.
- **Blog sky multi-pass join** (Darken → Lighten → Invert → Box Blur). Reduced to
  a single lightening blend mode (Screen/Lighten/Add) — the honest core of the
  additive-overlay pattern. Invert (`avfilter.negate`) and Box Blur (`boxblur`)
  can be layered afterward with `effect_add`.
- **Per-channel Levels (Red) / Curves (Luma)** — no small honest scalar surface
  (same reasoning that `color_grade` uses to drop `avfilter.colorbalance` /
  `avfilter.curves`); distilled into `avfilter.eq` + `frei0r.colorize`.

### New primitives that would complete the tutorials 1:1

- **Animated / keyframed rotoscoping** (day→night subject brightening) — shared
  hard blocker (`masking._spline_json` frame-0 only).
- **§1.1/§1.2 filter/composite placement fix** — gates render fidelity of the
  whole stack (shared with every effect/composite tool).
- **`clip_insert` track parameter + place-at-frame** — would replace the
  model-level `insert_overlay_clip` workaround with a first-class primitive.

## Raw summary

- **Effect names:** `effect_light_leak` (additive overlay: leak clip above +
  Screen/Lighten/Add composite + opacity + optional keyframed fades);
  `effect_day_to_night` (whole-frame day→night grade: eq darken/desaturate +
  blue colorize, optionally ramped; optional additive sky overlay).
- **Built on:** `pipelines/overlay_looks.py` (pure) → `server/bundles/
  overlay_looks.py` (`@mcp.tool`), reusing `apply_composite`,
  `build_fade_keyframes`, `build_keyframe_string`.
- **Shared pattern:** track-above overlay + lightening blend mode.
- **Missing primitives (for full 1:1):** animated rotoscoping; §1.1/§1.2
  placement fix; `clip_insert` track/place-at-frame parameter.
- **§1.1/§1.2-inherited:** composite/filter root-placement + index-addressed
  tracks — noted in both tool docstrings, not a blocker.
