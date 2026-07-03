---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: sci-fi chroma keying"
author: analysis agent
tags: [kdenlive-mcp, research, chroma-key, greenscreen, compositing]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Sci-Fi Effects - Mastering Chroma Keying in KDEnlive.md"
---

# Sci-Fi Chroma Keying Tutorial → MCP Tool Surface Mapping

Photolearningism, *"Sci-Fi Effects | Mastering Chroma Keying in KDEnlive"*
(video `uqge5McjO7E`, 11:01), analysed against the workshop-video-brain MCP
surface (`edit_mcp/server/tools.py`, `pipelines/masking.py`,
`pipelines/effect_catalog.py`, `pipelines/compositing.py`).

## What the tutorial actually teaches

Despite the "Sci-Fi Effects" framing, this video is **not** a scene-compositing
walkthrough. It teaches one thing well: a robust **green-screen key on a single
clip** (a hand in front of a browser-fullscreen green page, `[00:00]`–`[01:33]`),
built from a deliberately ordered stack of **three stock Kdenlive effects**. The
"background" is only present so the viewer can watch the key work
(`[02:20]`: "I'm going to take away the background here because that's just there
so you can see it working") — it is revealed by keying, never placed or graded.
The value to extract is the **stack order and the three-effect recipe** wrapped
around the existing advanced-key primitive.

## Technique breakdown (with [mm:ss] refs and exact effect names)

1. **[00:00]–[01:33] Shoot the plate.** Any reasonably-uniform green surface
   (a fullscreen green web page for small subjects; canvas/poster board for
   larger). Minor aberration is fine "because it still falls within a reasonable
   range of green for chroma keying".
2. **[02:20] Chroma Key: Advanced** (`avfilter.hsvkey`, "the advanced version
   for selection"). Pick the key color from the monitor/swatch. `[03:07]` **you
   must check *invert*** (otherwise it masks the wrong way); keep **Edge mode =
   Slope** ("the best edge method"); the key **can be keyframed** for changing
   light but the tutorial "just do[es] the one key" (static). `[03:53]` the
   color-range controls fine-tune what is removed; `[04:38]` **soften/feather**
   sparingly ("very easy to accidentally over-feather"). This alone "gets you
   most of the way there".
3. **[05:24] Key Spill Mop-Up** (`frei0r.keyspillm0pup`). Corrects the green
   light that **bounces onto the subject** ("light bounces… it will reflect the
   color onto your object"). Tell it the spill **key color** range and a
   **target color** "borrowed [as] a hue from my hand" to repaint the spill.
   `[06:12]` important controls: **key color** (what you key out) and what it is
   **translated to**; **Mask type = Color distance** ("the best mask type… that
   worked in these conditions"); **Tolerance** (intensity); **Slope**
   (transition). `[06:57]` **two passes**, "both as keys", is "really useful".
4. **[07:42] Stack order is load-bearing.** "The stack of effects is important
   because it processes them in that order. I am putting the correct effect
   [Key-Spill Mop-Up] **first** to translate key from my hand, then it passes
   into the next effect which is the **key** effect… so it gives it that
   opportunity not to wash out my hand." So processing order is **Key-Spill
   Mop-Up → Chroma Key Advanced → …**.
5. **[08:28] De-Spill** (`avfilter.despill`), **last**. Restores the brightness
   and detail the key stripped off, "to bring back those details of my hand that
   make it look real". `[09:15]` it "refers back to the chroma, so you only have
   two options green and blue"; you "restore the brightness and bring back the
   detail without playing with the chroma effect".
6. **([03:53]) Position and Zoom** — the tutorial also leaves a **crop** on to
   remove a sliver of the green page at the bottom of frame. This is clip-
   specific framing, not part of the reusable key recipe.

Final stack (top-to-bottom = processing order):
**Key Spill Mop-Up → Chroma Key: Advanced → De-Spill** (+ a Position-and-Zoom
crop specific to the shot).

## Capability mapping

| Step | Kdenlive effect | MCP status | Notes |
|---|---|---|---|
| Advanced key | `avfilter.hsvkey` | **exists** | `effect_chroma_key_advanced` / `masking.build_chroma_key_advanced_xml`. Reused by the new bundle. `av.hue/av.sat/av.val/av.similarity/av.blend`. |
| Key-Spill Mop-Up | `frei0r.keyspillm0pup` | **exists (catalog)** | `frei0r_keyspillm0pup` in `effect_catalog.py`: Key color, Target color, Mask type (0=Color distance), Tolerance, Slope, Operation 1/2 (1=De-Key), Amount 1/2. |
| De-Spill | `avfilter.despill` | **exists (catalog)** | `avfilter_despill`: `av.type` (green/blue), `av.mix`, `av.expand`, `av.brightness`. |
| Correct stack ordering | (order matters) | **exists** | `patcher.insert_effect_xml(position=…)` places filters deterministically; the bundle inserts in the tutorial's order. |
| `invert` on the key | hsvkey invert | **NOT exposed** | `build_chroma_key_advanced_xml` emits no invert property; the tool inherits its default keying behaviour. Documented omission. |
| Slope edge mode on the key | hsvkey edge method | **NOT exposed** | The existing builder does not surface an edge-mode selector. |
| Keyframed key (changing light) | animated hsvkey | **missing** | The tutorial itself uses a static key; keyframable wrappers are a separate gap (§3). |
| Position-and-Zoom crop | Transform/crop | partial / out of scope | An `affine`/crop could be added via `effect_add`, but the crop is shot-specific framing, deliberately excluded. |
| Background replacement | track ordering | **N/A here** | The tutorial reveals the track below by keying; no plate is placed or graded. `composite_set` exists separately if a caller wants an explicit composite. |

**Everything the recipe needs already exists as a primitive.** Unlike the four
motion-tracking-heavy tutorials in this folder, this one has **no hard blocker**:
its three effects are all in the catalog, and the only "missing" pieces (the
`invert`/`slope`/keyframe key knobs) are refinements of an existing, shipping key
filter.

## §1.1/§1.2 placement — known issue, not a blocker

Clip filters currently attach at the MLT **root** with `track=`/`clip_index=`
attributes rather than nesting inside the playlist `<entry>` (§1.1 of
docs/plans/2026-07-03-kdenlive-mcp-improvements.md). On reparse the serializer
logs *"Unknown element `<filter>` preserved as opaque node"*; the filters round-
trip and `patcher.list_effects` still reports them in order, but Kdenlive may not
render them until the placement fix lands. The new bundle inherits this exactly
like `effect_chroma_key_advanced`, `effect_hologram`, and every other clip-filter
tool. Noted, not blocking.

## Bundle tool spec — `effect_scifi_greenscreen` (BUILT)

A one-call bundle that applies the tutorial's full three-effect keying stack to a
clip, in the correct processing order, under a single snapshot. It **reuses**
`masking.build_chroma_key_advanced_xml` (the same pipeline function backing
`effect_chroma_key_advanced`) for the key, and builds the Key-Spill-Mop-Up and
De-Spill filters from catalog services via the shared `_build_filter_xml` +
`patcher.insert_effect_xml` machinery — the same architecture as
`effect_glitch_stack` / `effect_hologram`.

```
effect_scifi_greenscreen(
    workspace_path, project_file,
    track, clip,
    key_color="#00FF00",           # green screen to key out (drives all 3 filters)
    tolerance_near=0.10,           # hsvkey av.similarity
    tolerance_far=0.20,            # must be >= tolerance_near
    edge_smooth=0.05,              # hsvkey av.blend
    spill_correction=True,         # prepend frei0r.keyspillm0pup
    spill_target_color="#C87F65",  # hue "borrowed from the hand" to repaint spill
    spill_tolerance=0.24,          # keyspillm0pup Tolerance
    spill_slope=0.4,               # keyspillm0pup Slope
    spill_two_pass=True,           # second De-Key pass ("really useful")
    despill=True,                  # append avfilter.despill
    despill_amount=0.05,           # despill av.mix
    despill_brightness=0.0,        # despill av.brightness (restore luma)
)
```

Inserts, in tutorial order (toggled parts skipped), after any pre-existing
filters: `frei0r.keyspillm0pup` (Mask type = Color distance, two De-Key passes) →
`avfilter.hsvkey` (key, reusing the masking builder) → `avfilter.despill` (screen
type inferred green/blue from `key_color`). Returns `first_effect_index`,
`filter_count`, `services`, `key_color`, `screen_type`, `snapshot_id`.

### Omitted sub-effects (with reasons)

- **Background-plate replacement / compositing** — the tutorial never places or
  grades a replacement plate; the backdrop is revealed purely by keying. Layer a
  plate on a lower track + `composite_set` if wanted. *Honest to the transcript.*
- **Plate grading, glow, atmosphere** — absent from *this* video (the task brief
  speculated a fuller sci-fi comp; the transcript does not contain one).
- **`invert` / `slope` edge-mode / keyframed key** — refinements the existing
  `build_chroma_key_advanced_xml` does not surface; the tutorial demonstrates a
  static key anyway. Left to a future hsvkey-wrapper upgrade.
- **Position-and-Zoom crop** — shot-specific framing, not part of the reusable
  key recipe.

### Files

- Pipeline (new): `workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/scifi_greenscreen.py`
- Tool (appended): `effect_scifi_greenscreen` at the end of `edit_mcp/server/tools.py`
- Unit tests: `tests/unit/test_scifi_greenscreen_pipeline.py`
- Integration test: `tests/integration/test_scifi_greenscreen_mcp_tool.py`

## Raw summary

- **Effect name:** `effect_scifi_greenscreen` (three-effect green-screen keying recipe)
- **Reused primitive:** `masking.build_chroma_key_advanced_xml` (`avfilter.hsvkey`)
- **New catalog services wired:** `frei0r.keyspillm0pup`, `avfilter.despill`
- **Stack order (processing):** Key-Spill Mop-Up → Chroma Key Advanced → De-Spill
- **Hard blockers:** none (all three effects exist in the catalog)
- **Omitted:** background compositing/grading/glow (not in this tutorial), key `invert`/`slope`/keyframes (hsvkey builder does not expose them), Position-and-Zoom crop (shot-specific)
- **§1.1/§1.2 deps:** clip-filter root-placement (inherited, not blocking)
