---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: Color Wash / Light Wash VFX"
author: analysis agent
tags: [kdenlive-mcp, research, color, masking, compositing]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Master Color Wash VFX in Kdenlive.md"
video: "https://www.youtube.com/watch?v=X0CnXskcBpc"
channel: Photolearningism
duration: "14:38"
bundle_tool: effect_color_wash
---

# "Master Color Wash VFX in Kdenlive" → MCP Tool Surface Mapping

Photolearningism's tutorial (video id `X0CnXskcBpc`, 14:38) demonstrates a
**light-wash** / **colour-wash** effect: simulating the coloured light a
lightsaber (or any bright coloured source) throws onto the presenter and the
surrounding room. The core idea is a **colour grade confined to a region by a
rotoscoping mask**, layered over one or more clean copies of the same clip so
that the mask-induced transparency has something opaque to bleed onto.

Analysed against the workshop-video-brain MCP surface
(`edit_mcp/server/tools.py`, `pipelines/masking.py`, `pipelines/color_tools.py`,
`pipelines/effect_catalog.py`, `pipelines/effect_presets.py`,
`pipelines/effect_wrappers/`).

## a) Technique breakdown (steps, times, exact names)

| Time | Action |
|---|---|
| [00:00] | Goal: generate the **wash of light** emanating from a lightsaber so the moving prop reads as a real light source impacting its surroundings. |
| [00:48] | Multiple **copies of the same clip** are stacked; Kdenlive works **top-to-bottom** for video layers *and* for the effect stack (top effect = highest priority). |
| [01:35] | On the **top clip (V3)**, add the **Rotoscoping** *mask* effect (Kdenlive effect **"Rotoscoping"** — the mask variant, distinct from the plain roto). This effect acts as a **unifier**: everything **above it in the stack** is **limited to inside the mask**. So it must sit **below** every effect it should constrain. |
| [02:21] | Effects placed **below** the mask are **not** constrained by it. Stack order is load-bearing. |
| [02:21] | A **motion tracker** was tried (to import positional keyframes into the mask) but **does not work** — tracker keyframes will not transfer into the rotoscoping mask. Bug reported upstream; author falls back to **manual keyframing**. (Matches the MCP's own missing `opencv.tracker` gap.) |
| [03:07] | **Step 1 — define the mask region.** Rough-cut a shape around the subject (the light target). Key params: **Feathering width** (grows the blur/gradation from edge to transparency → the diffused wash look) and **Passes** (compounded feathering; **~4** is enough; more = more CPU). |
| [04:41] | Mask points are **keyframed** to follow the subject's motion; Bézier handles on each point allow curved shapes on two axes. Rough-drag through, spot-check, fill gaps. |
| [06:11] | **Step 2 — the wash colour.** Add a **Colorize** effect (**keyframable**): controls **colour (hue)**, **saturation**, and **lightness**. **Lightness is keyframed** so the wash gets bolder as the saber moves closer and dimmer as it recedes. |
| [07:44] | Add a **Transparency** effect — full-strength colorize looks too bold/unrealistic, so this tones it down. This *is* why a clean **under-layer copy** is needed: the mask + transparency make un-selected areas transparent, so an opaque copy below must supply the rest of the frame. |
| [08:30] | **Second layer (copy #2):** a **second Rotoscoping mask** selects **portions of the room** (light disperses off the subject onto the environment). Higher **feathering**, **~5 passes**. Note: when transparency-invoking effects lose their alpha, set the mask's **Alpha operation → minimum** (default starts on *clear*) to restore it — "always works consistently." |
| [10:02] | **Brightness & Contrast** added **outside (below) the mask** so it affects the **whole media element**, mimicking a camera auto-exposing to the blade's light. Keyframed. |
| [10:49] | Trick: two effects that need keyframes at the same frames — use the effect's **⋮ / three-lines → "Copy all keyframes to clipboard"**, then on the target effect **"Import keyframes from clipboard"** and choose **Position** (Geometry sometimes works). Saves re-authoring keyframe timing. |
| [12:21] | **Third layer (copy #3)** underneath everything, carrying the **same Brightness/Contrast** — a mirror image so all the mask-induced transparency lands on real image, not black. |
| [13:07] | Eye light-reflection is teased as a separate future topic (out of scope here). |
| [13:52] | Closes: the technique also generalises to precisely recolouring any masked region; the only real friction is the broken tracker forcing manual keyframes. |

## b) Kdenlive effects used (exact names → MLT service)

| Tutorial effect | Kdenlive name | MLT service | In catalog |
|---|---|---|---|
| Region mask (the "unifier") | **Rotoscoping** (mask) | roto/`frei0r` spline mask | `mask_set(type="rotoscoping")` — **frame-0 only** |
| Wash colour | **Colorize** | `frei0r.colorize` (hue/saturation/lightness) | ✅ `frei0r_colorize` |
| Tone-down | **Transparency** | `frei0r.transparency` (param `0`) | ✅ `frei0r_transparency` (wrapper `effect_frei0r_transparency`) |
| Brightness | **Brightness** | `frei0r.brightness` (`Brightness`) | ✅ `frei0r_brightness` |
| Contrast | **Contrast** | `frei0r.contrast0r` (`Contrast`) | ✅ `frei0r_contrast0r` |
| (alt combined) | Brightness/contrast | `avfilter.eq` (`av.brightness`,`av.contrast`) | ✅ `avfilter_eq` (constant-only) |

## c) Capability mapping (tutorial step → MCP status)

| Capability | MCP tool(s) | Status | Notes |
|---|---|---|---|
| Colorize wash (hue/sat/lightness) | `effect_add("frei0r.colorize")` / **`effect_color_wash`** | **exists** | Params map 1:1. `frei0r` values stored normalized 0..1. |
| Transparency tone-down | `effect_frei0r_transparency` / **`effect_color_wash`** | **exists** | Param `0` = opacity. |
| Brightness & contrast | `effect_add`/wrappers / **`effect_color_wash`** | **exists** | Two frei0r filters (animatable) or `avfilter.eq` (static). |
| Correct **stack order** (colour inside mask, brightness outside) | `effect_reorder` / `move_*` + bundle insertion order | **exists** | Bundle appends colorize→transparency→brightness→contrast in order. |
| Region mask around subject | `mask_set(type="rotoscoping")`, `mask_set_shape`, `mask_apply` | **partial → blocked** | `masking._spline_json` emits **frame 0 only**; the tutorial **keyframes the spline** across the whole shot. Static single-frame masks only. |
| Alpha operation → minimum | `mask_set_shape(alpha_operation=...)` | **partial** | Shape-mask path exposes it; the rotoscoping-mask path does not surface a keyframed alpha op. |
| Motion tracker → import to mask | — (`opencv.tracker`) | **missing** | Not in catalog; **the tutorial author confirms it is broken in Kdenlive itself** and falls back to manual keyframes. Doubly blocked. |
| Duplicate clip onto under-layers | — | **missing** | No cross-track clip-duplication primitive; `clip_move` is same-track only. The tutorial needs 2–3 opaque copies. |
| Keyframe lightness/brightness (pulse) | `effect_keyframe_set_scalar` | **exists (manual follow-up)** | Bundle applies static values; caller keyframes afterwards. |
| Copy/import keyframes between effects | `effects_copy`/`effects_paste`, `effect_keyframe_*` | **partial** | Copy/paste whole stacks exists; per-effect "position keyframes to clipboard" parity is approximate. |
| Filter placement renders in Kdenlive | (all effect tools) | **known issue (§1.1/§1.2)** | Per `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`, filters attach at MLT root with `track=`/`clip_index=` rather than nesting in the playlist `<entry>`; may not render. **Not a blocker for this task**, shared by every effect tool. |

## d) Bundle tool — `effect_color_wash`

Appends the tutorial's **whole-clip colour-grade stack** to one clip in a single
snapshot, composing existing catalog primitives (mirrors `effect_glitch_stack`).

```
effect_color_wash(
    workspace_path: str,
    project_file: str,
    track: int,
    clip: int,
    color: str = "blue",       # name (red/orange/yellow/green/cyan/blue/purple/magenta)
                               #   or normalized hue float 0.0..1.0
    intensity: float = 0.5,    # scales saturation, brightness lift, contrast
    opacity: float = 0.6,      # frei0r.transparency amount (1.0 = fully applied)
) -> dict
```

Pipeline: `edit_mcp/pipelines/color_wash.py` (pure: `resolve_hue`,
`color_wash_params`, `COLOR_WASH_SERVICES`, `COLOR_HUES`).

Insertion order (matches the tutorial's top-to-bottom effect order on the washed
clip):

1. `frei0r.colorize` — the wash tint. `hue` from `color`; `saturation` = `0.5 + intensity*0.5`; `lightness` = `0.5` (neutral, keyframe later).
2. `frei0r.transparency` — `0` = `opacity`.
3. `frei0r.brightness` — `Brightness` = `0.5 + intensity*0.12` (subtle glow lift).
4. `frei0r.contrast0r` — `Contrast` = `0.5 + intensity*0.08`.

Returns `{first_effect_index, filter_count, color, intensity, opacity, snapshot_id}`.
Snapshot taken before write (`before_effect_color_wash`); error-result convention
throughout (missing project, bad clip ref, out-of-range `intensity`/`opacity`,
unknown `color`, missing catalog service).

## e) Honest omissions (implemented subset only)

`effect_color_wash` reproduces the **colour grade**, not the full multi-layer,
region-masked, keyframed pipeline. Omitted, with reasons:

1. **Rotoscoping-mask region scoping** — the defining move (confine the wash to
   the subject, then a second mask for the room). The mask spline is **animated**
   across the shot; `masking._spline_json` emits **frame 0 only** (a known hard
   blocker, see SYNTHESIS.md), so per-frame roto cannot be authored. The bundle
   therefore washes the **whole clip**. Static region-scoping can be layered on
   separately via `mask_set` / `mask_set_shape` / `mask_apply`.
2. **Multi-layer under-copies** — the tutorial stacks 2–3 identical clips so the
   transparency has opaque layers to bleed onto. No cross-track clip-duplication
   primitive exists (`clip_move` is same-track only), so a single clip is graded.
3. **Keyframed lightness / brightness** (light pulsing with saber distance, and
   the camera-reaction brightness swing) — the bundle writes **static** values;
   a caller keyframes them afterwards with `effect_keyframe_set_scalar` (the
   `frei0r.brightness` / `frei0r.colorize` params are animated-type).
4. **Alpha-operation = minimum** on the (absent) mask — only relevant once the
   rotoscoping-mask path exists.
5. **Motion-tracker → mask keyframe import** — not built (`opencv.tracker`
   missing) **and** confirmed broken in Kdenlive itself by the tutorial author.
6. **§1.1/§1.2 filter placement** — the standing open issue affecting every
   effect tool (filters at MLT root vs. nested in the `<entry>`); noted, not a
   blocker for this task.

## f) Follow-up primitives that would complete the effect

- Animated (keyframed) rotoscoping spline + `roto-spline` ParamType (Wave 2).
- Cross-track clip duplication (opaque under-layers).
- Keyframable effect-param wrappers (so the bundle could emit the lightness /
  brightness pulse directly instead of a static grade).
- `subject_track` (§5) — would restore the tutorial's intended tracker-driven
  mask motion once Kdenlive's own tracker bug is resolved.
