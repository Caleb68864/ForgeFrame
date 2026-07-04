---
name: ff-effect-cookbook
description: >
  Pick and apply the right effect, composite, keying, masking, or motion tool for
  a look. Covers the one-call bundle tools (hologram, color grade/wash,
  greenscreen, masked wipes, camera shake, pan/zoom, subject zoom + tracking, AI
  masks, split-screen, light leaks) plus the low-level effect stack. Use when user
  says 'add an effect', 'how do I do X effect', 'color grade this', 'green screen',
  'key out the background', 'mask the subject', 'ken burns', 'camera shake',
  'hologram', 'glitch', 'which effect tool', or names a VFX look.
---

# Skill: ff-effect-cookbook

You are the effects reference. The MCP ships ~30 one-call **bundle tools** that
each stamp a complete tutorial look onto a clip in a single snapshot, plus the
low-level effect stack for hand-building. Your job is to map what the user wants
to the right tool, apply it, and know when to reach for the primitives instead.

**The old caveats are gone.** Earlier notes warned that composite/effect XML got
relocated to the project root, so effects wouldn't nest correctly, transitions
wouldn't render, and projects wouldn't open cleanly in Kdenlive (the §1.1/§1.2
placement bug). **That is fixed.** Effect and composite tools now write
well-formed XML — filters nest inside their playlist `<entry>`, transitions land
inside the `<tractor>`. Everything renders (melt-proven) and the resulting
projects open in the Kdenlive GUI. Apply these tools with confidence; you no
longer need to warn the user that a look "won't render" or "will break the file".

---

## When to invoke this skill

Trigger on any of these:
- "add an effect" / "which effect tool for X"
- "color grade this" / "apply a LUT" / "color wash" / "day to night"
- "green screen" / "key out the background" / "chroma key" / "luma key"
- "mask the subject" / "AI mask" / "rotoscope" / "isolate the person"
- "ken burns" / "pan and zoom" / "punch in" / "follow zoom" / "track the subject"
- "camera shake" / "drop shadow" / "hologram" / "glitch" / "light leak" / "rewind"
- "split screen" / "picture in picture" / "masked wipe" / "zoom transition"
- Any named VFX look from the Kdenlive tutorial world.

---

## How to pick a tool

1. **Is there a bundle for this exact look?** Prefer the one-call bundle — it
   applies a proven, correctly-ordered stack in one snapshot. See the catalog
   below.
2. **Need a single named filter?** Use `effect_add` (add by name),
   `effect_list_common` (browse), `effect_info` / `effect_find` (schema / locate
   an applied filter's index).
3. **Reusing a look across clips?** `effects_copy` / `effects_paste`, or save a
   `effect_stack_preset` (workspace tier) and `effect_stack_promote` it to the
   vault; apply with `effect_stack_apply`, browse with `effect_stack_list`.
4. **Animating a parameter?** Set keyframe strings directly:
   `effect_keyframe_set_scalar` / `_rect` / `_color`, or reorder with
   `move_up`/`move_down`/`move_to_top`/`move_to_bottom` / `effect_reorder`.

Every apply snapshots first — back out any look with `snapshot_restore`.

---

## The bundle catalog (what to reach for)

### Color & grade
- `effect_color_grade` — correction + grade chain in one snapshot.
- `effect_color_wash` — light-wash cinematic colour stack.
- `effect_day_to_night` — grade day → night (optional sky overlay).
- `color_apply_lut` — apply a `.cube`/LUT file to a clip.
- `color_analyze` — read a clip's colour metadata before grading.
- `effect_tcolor` — Technicolor-style oversaturation.

### Keying / greenscreen
- `effect_chroma_key` — basic `chroma` key.
- `effect_chroma_key_advanced` — `avfilter.hsvkey` advanced key.
- `effect_scifi_greenscreen` — the full sci-fi keying stack in one call.
- `effect_luma_key` — luminance → alpha (key on brightness).

### Masking (incl. AI / rotoscoping)
- `mask_generate` / `mask_generate_and_apply` — generate a black/white **matte
  video** with a local segmenter (AI) and wire it onto a clip's alpha.
- `mask_set_from_file` — consume an external matte (e.g. a SAM2/app-plugin mask).
- `mask_set_shape` — rotoscoping mask from a shape-derived spline (supports
  keyframed splines + luma mode — animated roto works now).
- `effect_object_mask` — parametric SPOT-SHAPE alpha mask (not AI).
- `mask_set` / `mask_apply` — insert / sandwich a mask filter manually.

### Compositing & layers
- `composite_pip` — picture-in-picture.
- `composite_split_screen` — split / quad-screen from several tracks.
- `composite_set` — composite transition with a named blend mode.
- `composite_wipe` — wipe / dissolve between two tracks.
- `overlay_insert` — place a single still (PNG/JPG/SVG) on a track.
- `watermark_apply` — full-duration corner watermark.

### Signature looks
- `effect_hologram` — full hologram look in one snapshot.
- `effect_glitch_stack` — 5-filter glitch stack.
- `effect_light_leak` — additive light-leak overlay above the footage.
- `effect_rewind` — VHS-style reversed/sped-up segment.
- `flash_cut_montage` — split a clip into N cuts with rotating directional blur.
- `effect_camera_shake` — deterministic keyframed `qtblend` shake.
- `effect_drop_shadow` — dropshadow (PiP / title layers / lower-thirds).
- `transition_paper_cutout` — torn-paper cutout filter stack.
- Old-film / analog: `effect_oldfilm`, `effect_grain`, `effect_dust`,
  `effect_scratchlines`, and the `effect_frei0r_*` family (glitch0r, cartoon,
  edgeglow, mirr0r, scanline0r, letterb0xed, …) for one-off analog textures.

### Motion, Ken Burns & tracking
- `effect_pan_zoom` — keyframed pan/zoom (Ken Burns).
- `subject_zoom` — tracked follow-zoom **or** static punch-in.
- `subject_locate_frames` → `subject_track` — extract a frame, supply a subject
  bbox, then track that rectangle across the clip (saves keyframes) so
  `subject_zoom` can follow it. This is the motion-tracking path.
- `speed_ramp` — keyframed speed ramp / time remap.
- `effect_fade` — keyframed opacity fade.

### Transitions between clips/tracks
- `transition_masked_wipe` — masked / custom-luma wipe between two tracks.
- `transition_zoom_whip` — zoom / whip-pan across a cut on one track.
- `transitions_apply_between` / `transitions_apply_at` — generic transition at a
  clip boundary or timestamp.

---

## Manual method vs. tool — the guide notes (cross-reference)

Each bundle was reverse-engineered from a specific Kdenlive tutorial. When a user
asks "how would I do this by hand" or wants to tweak beyond the bundle's
parameters, point them at the matching **manual-vs-tool analysis note** in the
Video Production research folder — each note documents the tutorial's manual
steps, the `built_tool` that replaces them, and what the tool deliberately omits:

| Tool | Guide note (`docs/research/2026-07-03-tutorial-effect-analysis/`) |
|---|---|
| `effect_hologram` | `hologram-effect.md` |
| `effect_color_grade` | `color-correction-grading.md` |
| `effect_color_wash` | `color-wash-vfx.md` |
| `color_apply_lut` | `color-correction-grading.md` |
| `effect_scifi_greenscreen` / chroma keys | `scifi-chroma-key.md` |
| `effect_light_leak` / `effect_day_to_night` | `lightleak-daynight.md` |
| `effect_pan_zoom` | `keyframes-panzoom.md` |
| `subject_zoom` / `subject_track` | `motion-graphics-pipeline.md` |
| `speed_ramp` | `speed-ramping.md` |
| `effect_camera_shake` / `effect_drop_shadow` | `shake-shadow.md` |
| `composite_split_screen` | `split-screen.md` |
| `composite_pip` | `validation-existing-tools.md` |
| `transition_masked_wipe` | `masked-wipe-transitions.md` |
| `transition_zoom_whip` | `zoom-whip-transition.md` |
| `transition_paper_cutout` | `paper-cutout-transition.md` |
| `effect_rewind` | `rewind-effect.md` |
| `effect_object_mask` / `mask_set_from_file` | `validation-existing-tools.md` |
| AI masks (`mask_generate*`) | `vault/Research/Local AI Mask Generation.md` |
| `media_stabilize` | `stabilization.md` |

`SYNTHESIS.md` in that folder is the overview of the whole tutorial → tool
mapping. The source tutorial transcripts live in
`vault/Transcripts/Kdenlive Tutorials/`.

---

## Rendering effects with transparency

Looks that produce an alpha layer (keyed greenscreen element, animated overlay,
masked subject to composite elsewhere) must be rendered with an **alpha profile**
so the transparency survives export. List profiles with `render_list_profiles`;
the alpha ones are `prores-4444-alpha`, `mov-alpha`, `webm-alpha`, `ffv1-alpha`.
Render with `render_final_tool(profile="...")`. Deliver the flattened master with
a normal profile (`final-youtube`, `draft-youtube`).

---

## Quality guidelines

- Prefer a bundle over hand-stacking filters — the bundle's filter order is the
  proven one.
- Confirm the clip/track index with `project_summary` before applying; an
  out-of-range index is the most common error here.
- Motion tracking and AI masks need optional deps (`opencv`, `rembg`). If a tool
  reports `missing_dependency`, pass a lighter engine (`engine='rembg'` /
  `engine='opencv'`) or install per the suggestion.
- **Failure contract:** every tool returns a structured error dict carrying
  `error_type` + a plain `suggestion` (never a traceback). `not_found` on an
  effect → `effect_list_common`; missing dep → install per the `suggestion`.
  Full taxonomy: the vault's [[MCP Error Catalog]].

---

## Handoff

After applying a look:
- Say which tool + snapshot you used (so it's reversible via `snapshot_restore`).
- If it's part of a finishing pass, hand off to `/ff-finishing`.
- Offer to save a reusable look with `effect_stack_preset` /
  `effect_stack_promote`.
