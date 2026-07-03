---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: camera shake + drop shadow"
author: analysis agent
tags: [kdenlive-mcp, research, camera-shake, drop-shadow, keyframes, transform]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Smooth Transitions, Camera Shake, Drop Shadow - Kdenlive Tutorial.md"
video: V0_yp-ziqvI
channel: Nuxttux Creative Studio
built_tools: [effect_camera_shake, effect_drop_shadow]
---

# Camera-Shake + Drop-Shadow Tutorial → MCP Tool Surface Mapping

Nuxttux Creative Studio's *"Smooth Transitions, Camera Shake, Drop Shadow"*
(`V0_yp-ziqvI`, 4:08) analysed against the workshop-video-brain MCP surface
(`edit_mcp/server/tools.py`, `edit_mcp/server/bundles/`,
`pipelines/keyframes.py`, `pipelines/effect_catalog.py`,
`pipelines/hologram.py`, `pipelines/effect_presets.py`).

This is **tutorial #17** in
`vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md` ("Keyframed
transform (shake), drop-shadow effect wrapper"). Unlike the VFX-build tutorials
(hologram, teleport), this is a **preset-showcase** video: the author publishes
downloadable Kdenlive effect-stack presets (transitions, "camera Shake medium",
"drop shadow", glitch, LM color series) and demonstrates *applying* them, never
opening their internals. The mechanics below are therefore **reconstructed** from
the named presets + existing MLT primitives, not transcribed keystroke-by-
keystroke. Both effects are fully buildable today; there are **no hard blockers**.

## Technique breakdown (steps, [mm:ss])

1. **[00:00]** Presets are distributed via the Effects-tab **download** button
   (search "Nuxttux"); "custom templates" appear under the star-with-pencil.
2. **[01:32]** **Transition presets** (zoom in/out, spin CCW, corner wipes) are
   drag-dropped onto short cuts (8–14 frames); the author hand-tunes the last
   keyframe of the gaussian-blur / transform / lens-correction sub-effects to
   stretch the transition to the desired frame length. (Transitions are out of
   scope for this build — see omissions.)
3. **[03:03]** A **wipe transition** with `method = cloud`, softness ≈ 70, is
   dropped between two clips to blend them.
4. **[03:36]** **Camera Shake.** After joining three clip pieces into a
   sequence, the author applies **"camera Shake medium"** — and explicitly notes
   the **"r for rotation"** variant ("camera Shake medium r r for rotation").
   This is a keyframed **Transform** jitter on an otherwise static tripod shot.
5. **[03:50]** The **drop shadow** preset (and glitch transition, LM color
   grade) are name-dropped as further downloads and deferred to the linked
   playlist.

## Effects named (exact preset / effect names)

Zoom transition in/out; simple zoom in/out; spin transition CCW; wipe transition
(method = cloud, softness); corner transitions (TR/BR/TL/BL); **camera Shake
medium (+ r rotation)**; **drop shadow**; glitch transition; LM color-correction
series. Presets are numbered `<n>F` (frames) and paired `1`/`2` (out/in halves).

## Existing machinery surveyed

* **`effect_keyframe_set_rect` pipeline** (`pipelines/keyframes.py` +
  `_keyframe_tool_impl`): builds MLT keyframe animation strings
  (`HH:MM:SS.mmm[op]=value`) for `scalar` / `rect` / `color` kinds, with the
  same `build_keyframe_string` used by `effect_fade` (an `affine`/`transform`
  filter carrying a keyframed `rect`). Camera shake is exactly this pipeline
  driven by a **seeded RNG**.
* **Effect catalog** (`pipelines/effect_catalog.py`, generated from
  `/usr/share/kdenlive/effects/`): searched for shadow/glow/blur services —
  * **`dropshadow`** (mlt_service `dropshadow`, "Create a shadow effect from the
    alpha channel"; params `radius`, `x`, `y`, `color` default `#b4636363`).
    **This is a clean, dedicated shadow filter** — no recipe needed.
  * `frei0r.glow`, `movit.glow`, `avfilter.gblur` / `avfilter.dblur` /
    `boxblur` / `avfilter.avgblur` — blur services (used elsewhere, e.g.
    hologram).
  * `frei0r.alpha0ps_*`, `frei0r.alphagrad`, `frei0r.alphaspot` — alpha ops
    (would be the building blocks for a manual duplicate-darken-blur recipe, but
    `dropshadow` makes them unnecessary).
* **Transform service.** `effect_fade` writes `affine`/`transform` with a
  keyframed `rect`. For shake-with-**rotation** the cleaner single-filter service
  is **`qtblend`** (modern Kdenlive "Transform": one `rect` *plus* a keyframable
  `rotation` degrees property). `qtblend` is a valid MLT/Kdenlive service (it is
  the `mask_apply` default `transition`) though it is not emitted into the
  generated `effect_catalog` — like `effect_fade`, the bundle builds the filter
  XML directly via `_build_filter_xml`, so catalog presence is **not** required.

## Capability mapping

| Step | Kdenlive effect | MCP tool | Status | Why |
|---|---|---|---|---|
| Camera shake (position) | camera Shake medium | **`effect_camera_shake`** | **BUILT** | seeded keyframed `qtblend` `rect` jitter via the keyframe pipeline. |
| Camera shake (roll) | "r for rotation" | **`effect_camera_shake(rotation=True)`** | **BUILT** | keyframed `rotation` scalar on the same `qtblend` filter. |
| Hide overscan edges | (implicit in preset) | `effect_camera_shake` overscan | **BUILT** | `zoom = 1 + 0.12·intensity`; every offset clamped to the overscan margin → no black edges. |
| Drop shadow (PiP/title) | drop shadow | **`effect_drop_shadow`** | **BUILT** | dedicated `dropshadow` MLT service (shadow from alpha channel). |
| Zoom / spin / corner / wipe transitions | numbered transition presets | `transitions_apply*`, `composite_wipe`, `effect_fade` | **partial / out of scope** | transitions already have their own tools; not folded into this build (see omissions). |
| Glitch transition | glitch preset | `effect_glitch_stack` | **exists** | separate bundle. |
| LM color series | color presets | `color_*`, `effect_tcolor`, LUT tools | **exists** | separate tools. |

**§1.1 placement (known, not a blocker):** clip filters currently attach at the
MLT root with `track=` / `clip_index=` attrs rather than nesting in the playlist
`<entry>` (§1.1 of `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`). Both
new tools inherit this until the placement-fix agent lands the change; they still
write well-formed filter XML that will relocate correctly once the serializer
honours the placement hint. Same posture as `effect_hologram` /
`effect_glitch_stack`.

## Bundle tool specs (BUILT)

New module `edit_mcp/server/bundles/shake_shadow.py` (auto-discovered by the
`bundles` package; `from workshop_video_brain.server import mcp`); pure math in
`edit_mcp/pipelines/shake_shadow.py`.

```
effect_camera_shake(
  workspace_path, project_file, track, clip_index,
  start_frame, end_frame,          # end_frame = -1 => end of clip
  intensity=0.5,                   # [0,1]; 0.5 ~= preset "medium"
  frequency_hz=8.0,                # shakes/sec; keyframe step = round(fps/freq)
  seed=None,                       # RNG seed; None => fixed default (still reproducible)
  rotation=False,                  # "r" variant: also jitter roll
) -> dict
```

```
effect_drop_shadow(
  workspace_path, project_file, track, clip_index,
  blur_radius=6, offset_x=8, offset_y=8,
  color="#b4000000",               # Kdenlive #AARRGGBB (alpha first); 70% black
) -> dict
```

### Camera-shake algorithm (`pipelines/shake_shadow.camera_shake_keyframes`)

1. Overscan the clip: `zoom = 1 + 0.12·intensity`; enlarge `rect` to
   `(round(W·zoom), round(H·zoom))`, centred at `(-margin_x, -margin_y)`.
2. Keyframe grid: `step = max(1, round(fps/frequency_hz))` frames across
   `[start_frame, end_frame]` (last frame always included).
3. `rng = random.Random(seed if seed is not None else 0)`. For each keyframe
   (except the first, anchored at rest to avoid a pop-in) draw
   `dx, dy ∈ [-0.9·margin, 0.9·margin]`, `angle ∈ [-2.5·intensity, +2.5·intensity]°`
   when `rotation`. Every offset is **clamped into the margin** so the enlarged
   rect always covers `[0,W]×[0,H]` — the edge-coverage invariant is unit-tested.
4. Emit the `rect` (and optional `rotation`) as MLT keyframe strings via
   `build_keyframe_string`. **Determinism:** identical inputs (incl. `seed`) →
   byte-identical strings. (The `Date.now()`-style randomness ban from §1.1 does
   not apply — this is seeded Python `random.Random`, fully reproducible.)

### Drop-shadow approach — **VERDICT: clean dedicated service, no recipe needed**

The MLT `dropshadow` filter derives the shadow directly from the layer's alpha
channel and exposes exactly the classic controls (blur `radius`, `x`/`y` offset,
`color` with alpha). It is the correct single-filter path for PiP / title layers
that already carry transparency. The fallback **duplicate-darken-offset-blur**
recipe (which would need a solid-color producer insert + alpha ops +
`avfilter.gblur` + a second composited layer) was therefore **not** built — it
would be strictly worse and more fragile. `effect_drop_shadow` ships the
dedicated service.

### Omitted / out of scope (documented; not built as pretend-functionality)

- **Transition presets** (zoom/spin/corner/wipe). These are the bulk of the
  video but are (a) already served by `transitions_apply*` / `composite_wipe` /
  `effect_fade`, and (b) distributed as opaque downloadable `.json` preset files
  whose internal keyframe values are never shown. Reproducing them 1:1 would be
  guesswork; deferred to the existing transition tools.
- **Preset download / install workflow** — out of scope (Kdenlive UI feature,
  not a project-file edit).
- **Glitch transition, LM color series** — separate, already-covered surfaces
  (`effect_glitch_stack`, color tools).

## Raw summary

- **Tools built:** `effect_camera_shake` (seeded keyframed `qtblend` position +
  optional rotation jitter, overscan edge-safe) and `effect_drop_shadow`
  (dedicated `dropshadow` MLT service).
- **Built on:** new `pipelines/shake_shadow.py` (pure: `camera_shake_keyframes`,
  `drop_shadow_params`, `shake_step_frames`, `_clamp_offset`) →
  `bundles/shake_shadow.py` (`@mcp.tool`, single snapshot before write, `_err`/
  `_ok` contract, `_build_filter_xml` / `patcher.insert_effect_xml`).
- **Shadow verdict:** dedicated `dropshadow` service exists and is clean — used
  directly; duplicate-darken-offset-blur recipe intentionally not built.
- **Missing primitives:** none required for these two effects. (A solid-color
  producer insert + the §1.1 placement fix would be needed only for the
  *manual* shadow recipe, which we avoided.)
- **§1.1-broken deps:** clip-filter root-placement (inherited, not a blocker;
  noted in both tool docstrings).
- **Determinism:** seeded `random.Random`; unit-tested per-seed reproducibility,
  frequency/intensity math, and the overscan edge-coverage (bounds-clamping)
  invariant.
