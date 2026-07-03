---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: realistic hologram VFX"
author: analysis agent
tags: [kdenlive-mcp, research, hologram, compositing, chroma-key, tracking]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/How to Create Realistic Holograms in KDENlive - VFX Tutorial.md"
video: P0eI7YLN3FU
channel: Photolearningism
built_tool: effect_hologram
---

# Hologram-Effect Tutorial → MCP Tool Surface Mapping

Photolearningism's *"How to Create Realistic Holograms in KDENlive - VFX
Tutorial"* (`P0eI7YLN3FU`, 11:33) analysed against the workshop-video-brain MCP
surface (`edit_mcp/server/tools.py`, `pipelines/effect_presets.py`,
`pipelines/hologram.py`, `pipelines/compositing.py`, `pipelines/masking.py`,
`pipelines/effect_catalog.py`, `pipelines/effect_wrappers/`).

Unlike the four Nuxttux batches (see `SYNTHESIS.md`), this tutorial is a single
end-to-end hologram build. It is a **compositing + isolation + tracking + look**
pipeline. The **look** layer is buildable today; the **isolation** and
**tracking** layers hit the same blockers catalogued in
`compositing-effects.md` (§ motion tracker, animated rotoscoping, §1.1
placement). This report ships the achievable subset as `effect_hologram` and
documents the omissions.

## Technique breakdown (steps, effects, [mm:ss])

1. **[00:45]** **Plan / base plate.** Shoot a base clip (wide 0.5× lens) with the
   "projector" (a watch) in frame; this is the plate the hologram composites onto.
2. **[01:31]** **Green-screen subject.** A partial green screen behind the head
   only — full coverage not required.
3. **[02:17]** **Rotoscoping** to isolate the subject where the green screen
   doesn't reach: draw a mask around the subject; **Feathering** effect (feather
   *passes* = iterations, feather *width* = uniform expansion) to soften edges
   before keying.
4. **[03:02]** **Chroma Key (advanced)** — the *Advanced* chroma variant,
   applied **multiple times** to catch uneven green ranges. Per pass: pick a
   mid-range green (color-picker is broken in this Kdenlive build → use *pick
   screen color*), set **color elimination / scale**. Too-aggressive scale eats
   the subject (green spill/wash).
5. **[04:36]** **Key Spill Mop-up.** Designed to *recolor* (not remove) green
   spill on the subject. Pick the spill green, choose **operation =
   Desaturation**, two passes, amounts pushed all the way up.
6. **[06:10]** **Motion Tracker** on the **base layer**. Select a pattern to
   follow (default algorithm = fine; lighter/faster alternatives exist);
   **Analyze** → generates a keyframe per frame. Make a **hard cut** so only the
   keyframes for the hologram window remain.
7. **[07:40]** **Copy all keyframes to clipboard** (hamburger / three-lines
   menu); disable the tracker.
8. **[08:27]** **Transform** on the hologram layer → hamburger → **Import
   keyframes** → **map = Position** (not Geometry). Use **horizontal / vertical
   offset** sliders to re-center the hologram on the tracked point so it "stays
   with" the projector as the subject moves.
9. **[09:12]** **Colorize** — "I like it blue"; set the hologram tint.
10. **[09:12]** **Transparency** — reduce visibility for a translucent look.
11. **[09:12]** **Fade in** — simple opacity fade so the hologram powers on.
12. **[10:00]** **Box Blur** — keyframable, **one axis only** (horizontal *or*
    vertical). One-axis blur gives the "interrupted transmission" futuristic
    look (not an isotropic blur).
13. **[10:00]** **White splotch overlay layers** with heavy transparency — extra
    "projection backing / splashing" weight, each also carrying a **Transform**
    with the **same imported tracking keyframes** so every layer moves together.

## Effects named (exact Kdenlive names)

Rotoscoping; Feathering (passes / width); Chroma Key (Advanced) ×N (color
elimination / scale); Key Spill Mop-up (operation = Desaturation, 2 passes,
amount); Motion Tracker (default algo, Analyze, per-frame keyframes,
copy-all-keyframes); Transform (Import keyframes → map Position, H/V offset);
Colorize; Transparency; Fade in; Box Blur (single-axis, keyframable); white
overlay layers + Transform.

## Capability mapping

| Step | Kdenlive effect | MCP tool | Status | Why |
|---|---|---|---|---|
| Isolate subject (partial GS) | Rotoscoping | `mask_set(type="rotoscoping")` | **partial** | `_spline_json` emits frame-0 spline only; subject moves ⇒ needs animated mask. |
| Soften mask edges | Feathering | `mask_set_shape(feather, feather_passes)` | partial | feather modelled on shapes; standalone feathering-of-roto not first-class. |
| Key green (uneven) | Chroma Key (Advanced) ×N | `effect_chroma_key_advanced` | **exists** | multi-pass = call N times; §1.1 placement risk. |
| Recolor spill | Key Spill Mop-up (desaturate) | — | **missing** | no `mlt_service` for key-spill mop-up in catalog. |
| Track projector | Motion Tracker | — | **missing** | no `opencv.tracker` anywhere (see `compositing-effects.md`). |
| Copy → import keyframes | Transform + import | `effect_keyframe_set_rect` | partial | consumer exists; the *producer* (tracker) is missing → no rects to import. |
| Position offset | Transform H/V offset | `effect_add("affine")` + `effect_keyframe_set_rect` | partial | expressible if tracked rects existed; §1.1. |
| Tint | **Colorize** | `effect_add("frei0r.colorize")` / **`effect_hologram`** | **exists** | shipped as the colorize layer of `effect_hologram`. |
| Translucency | **Transparency** | `effect_frei0r_transparency` / **`effect_hologram`** | **exists** | shipped (`frei0r.transparency`). |
| Power-on fade | **Fade in** | `effect_fade(fade_in_frames=…)` | **exists** | separate tool; not folded into `effect_hologram` (see omissions). |
| Interrupted-transmission blur | **Box Blur** (1-axis) | `effect_add("boxblur")` / **`effect_hologram`** | **exists** | shipped as directional `boxblur` (hori-scaled, vert=1). |
| Scan-line texture (added) | scanline0r | `effect_frei0r_scanline0r` / **`effect_hologram`** | **exists** | `frei0r.scanline0r` (no params). |
| Bloom (added) | Glow | `effect_frei0r_*`/`effect_add("frei0r.glow")` / **`effect_hologram`** | **exists** | `frei0r.glow` Blur param. |
| Flicker (added) | Glitching | `effect_frei0r_glitch0r` / **`effect_hologram`** | **exists** | `frei0r.glitch0r`; animated over the frame window. |
| White overlay layers | solid/white producer + Transform | — | **missing** | no solid-color producer insert; tracked-transform depends on tracker. |

**§1.1 placement (known, not a blocker):** clip filters currently attach at the
MLT root with `track=`/`clip_index=` attrs rather than nesting in the playlist
`<entry>` (§1.1 of `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`).
`effect_hologram` inherits this until the placement-fix agent lands the change;
the tool still writes well-formed filter XML that will relocate correctly once
the serializer reads `position_hint`.

## Bundle tool spec — `effect_hologram` (BUILT)

```
effect_hologram(
  workspace_path: str,
  project_file: str,
  track: int,
  clip: int,
  tint_color: str = "#33ccff",     # hologram cyan/blue (tutorial "I like it blue")
  scanline_intensity: float = 0.5, # gates scanline0r + scales 1-axis box blur
  glow: float = 0.35,              # frei0r.glow bloom
  transparency: float = 0.25,      # fraction of visibility removed (0 = opaque)
  flicker: float = 0.3,            # frei0r.glitch0r; animated over [start,end]
  start_frame: int = 0,
  end_frame: int = -1,             # -1 => end of clip
) -> dict
```

Composed stack (ordered, conditional layers omitted when their intensity is 0),
built by `pipelines/hologram.py::hologram_stack_params` and written filter-by-
filter under a **single snapshot**, mirroring `effect_glitch_stack`:

1. `frei0r.colorize` — hue/saturation derived from `tint_color`.
2. `frei0r.scanline0r` — scan lines (when `scanline_intensity` > 0).
3. `boxblur` — one-axis "interrupted transmission" blur (hori scaled by
   `scanline_intensity`, vert = 1).
4. `frei0r.glow` — bloom (when `glow` > 0).
5. `frei0r.glitch0r` — flicker; Glitch Frequency animated across
   `[start_frame, end_frame]` when a window is given, else static.
6. `frei0r.transparency` — translucency (always emitted; `0 = 1 - transparency`).

### Omitted sub-effects (documented; not built as broken pretend-functionality)

- **Green-screen isolation** (Rotoscoping + Advanced Chroma Key ×N + Key Spill
  Mop-up). `effect_chroma_key_advanced` exists, but the *animated* rotoscoping
  around a **moving** subject is not achievable (frame-0-only spline), and
  **Key Spill Mop-up** has no catalog service. The subject-isolation layer is
  left to the operator; `effect_hologram` applies the look to the whole clip.
- **Motion tracking → tracked Transform.** No `opencv.tracker`; the "hologram
  sticks to the moving watch" trick (the heart of the shot) cannot be produced.
  `effect_hologram` does not track; it applies to the full frame.
- **Fade-in** deliberately **not folded in** — `effect_fade` already ships this
  and folding it would duplicate a keyframed-affine layer the operator may want
  to place/tune independently. Call `effect_fade(fade_in_frames=…)` alongside.
- **White projection-backing overlay layers** — need a solid/white-color
  producer insert (missing) and per-layer tracked transforms (tracker missing).

### New primitives that would complete the tutorial 1:1

Same shared blockers as `compositing-effects.md`: `motion_track`
(`opencv.tracker`) — **critical**; animated/keyframed rotoscoping;
key-spill-mop-up catalog service; solid/white-color producer insert; the §1.1
filter-placement fix (gates rendering of the whole stack).

## Raw summary

- **Effect name:** `effect_hologram` (hologram *look*: tint + scanlines +
  1-axis transmission blur + glow + animated flicker + translucency)
- **Built on:** `pipelines/hologram.py` (pure) → `@mcp.tool effect_hologram`
  (composes existing catalog services via `_build_filter_xml` /
  `patcher.insert_effect_xml`, single snapshot, `_err`/`_ok` conventions).
- **Missing primitives (for full 1:1):** motion_track (opencv.tracker);
  animated rotoscoping; key-spill-mop-up service; solid/white-color producer;
  §1.1 placement fix.
- **§1.1-broken deps:** effect/keyframe root-placement (whole stack) — inherited,
  not a blocker; noted in the tool docstring.
