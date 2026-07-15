---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: keyframes & Ken Burns pan/zoom"
author: analysis agent
tags: [kdenlive-mcp, research, keyframes, pan-zoom, ken-burns, transform]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/2024 Kdenlive Tutorial - How to Use Keyframes.md"
video: 0DdfHgIuS-4
channel: Victoriano de Jesus
built_tool: effect_pan_zoom
---

# Keyframes / Pan-Zoom Tutorial → MCP Tool Surface Mapping

*"2024 Kdenlive Tutorial - How to Use Keyframes"* (`0DdfHgIuS-4`, 10:02)
analysed against the workshop-video-brain MCP surface
(`edit_mcp/pipelines/keyframes.py`, `pipelines/pan_zoom.py`,
`edit_mcp/server/tools.py::effect_keyframe_set_rect`,
`edit_mcp/adapters/kdenlive/patcher.py`, `docs/reference/mlt/keyframe-operators.md`).

This is landscape entry **#23** (REINFORCE): keyframe fundamentals demonstrated
via the **Transform** effect (move / scale / rotate an image) plus interpolation
types (linear / discrete / smooth) and a second **Crop, Scale and Tilt**
"cinematic reveal" example. The core keyframe machinery already ships
(`effect_keyframe_set_rect/scalar/color`); what was **missing** was an
ergonomic, profile-aware *pan/zoom* front door that a caller can drive with a
preset instead of hand-authoring rect keyframe JSON. This report ships that as
`effect_pan_zoom` — the **static cousin of `subject_zoom`** (plan §5): same
keyframed-transform output, but with hand-/preset-chosen rects instead of
tracked, smoothed ones.

> **Note on attribution:** the landscape lists this as *TJ Free*; the fetched
> transcript's channel metadata is *Victoriano de Jesus* and the runtime is
> 10:02 (landscape said ~14m). The technique content is as expected either way.

## Technique breakdown (steps, effects, [mm:ss])

1. **[00:46]** Import a still (a tractor on a black background) and drop it on
   the timeline (~4 s). A static image does nothing on play — keyframes are what
   animate it.
2. **[01:33]** Search effects for **Transform**, drag it onto the clip. The
   *diamond* on the effect's mini-timeline marks it as **keyframeable**. The
   keyframe playhead tracks the project playhead.
3. **[02:19]** Set the first keyframe: scale to ~60%, place lower-left. Add a
   keyframe at the start and another near the 3-second mark with the image moved
   to the right → the image **pans left→right** on play.
4. **[03:08]** Retiming: drag a keyframe earlier (2 s) to make the move faster;
   add a **middle keyframe** raised to the top so the path arcs up-then-down.
5. **[03:54]** Delete a keyframe: the currently-selected keyframe is red; select
   and delete → path returns to a straight line.
6. **[04:42]** **Interpolation types.** Default is **linear** (constant motion).
   Switch all to **discrete** → value jumps at each keyframe, no motion between.
   Switch to **smooth** → curved, eased path. Types are per-keyframe and can be
   mixed.
7. **[06:15]** **Combine properties.** On a middle keyframe also change
   **rotation** and **size** — position, rotation and scale animate together
   from one keyframe set.
8. **[07:03]** **Auto-keyframing**: with ≥2 keyframes active, moving the image at
   a new playhead position auto-creates a keyframe.
9. **[07:50]** Second example — a **cinematic reveal** on a walking-lady clip
   using **Crop, Scale and Tilt**: keyframe top/bottom crop = 200 px (fully
   cropped), then a later keyframe with crop = 0 → the frame is **revealed** over
   time.

## Effects named (exact Kdenlive names)

Transform (position / scale / rotation, keyframeable); keyframe interpolation
types **Linear / Discrete / Smooth**; Crop, Scale and Tilt (keyframeable crop).

## Capability mapping

| Step | Kdenlive effect | MCP tool | Status | Why |
|---|---|---|---|---|
| Keyframeable Transform (move/scale) | Transform (`affine`) | `effect_keyframe_set_rect` + **`effect_pan_zoom`** | **exists / shipped** | rect pipeline exists; `effect_pan_zoom` is the preset front door. |
| Linear / discrete / smooth interpolation | keyframe type | `keyframes.py` easing operators | **exists** | `linear`/`hold`(discrete)/`smooth` + full ease families → operator chars (`docs/reference/mlt/keyframe-operators.md`). |
| Left→right / arc pan | multi-keyframe move | **`effect_pan_zoom`** (presets) | **shipped** | `pan_left_to_right`, `kenburns_*`; 2-keyframe eased move (arc needs a 3rd keyframe — see omissions). |
| Zoom in / out (Ken Burns) | scale keyframes | **`effect_pan_zoom`** (`zoom_in`/`zoom_out`) | **shipped** | profile-computed centered zoom region. |
| Combined rotation + scale + position | Transform (rotation) | `effect_keyframe_set_scalar` on `rotation` | **partial** | rect is shipped; rotation is a separate scalar property, not folded into `effect_pan_zoom`. |
| Auto-keyframing (UI convenience) | GUI-only | — | **n/a** | interactive editor affordance; not an MCP concept. |
| Cinematic reveal (crop) | Crop, Scale and Tilt | `effect_keyframe_set_scalar` on crop props | **partial** | expressible as scalar keyframes on `crop`/`tilt`; no dedicated wrapper. |

**§1.1 placement (known, not a blocker):** clip filters currently attach at the
MLT root with `track=`/`clip_index=` attrs rather than nesting in the playlist
`<entry>` (§1.1 of `docs/plans/2026-07-03-kdenlive-mcp-improvements.md`).
`effect_pan_zoom` inherits this — it writes well-formed `<filter>` XML (same
shape as the existing `affine`/`transform` filter and `effect_keyframe_set_rect`
consumers) that will relocate correctly once the serializer honours
`position_hint`.

## Bundle tool spec — `effect_pan_zoom` (BUILT)

```
effect_pan_zoom(
    project_file: str,                 # absolute path to the .kdenlive file
    track: int,
    clip_index: int,
    start_rect: list[float] | None = None,   # [x, y, w, h] source region
    end_rect: list[float] | None = None,     # [x, y, w, h] source region
    preset: str | None = None,               # see PRESETS below
    duration_frames: int | None = None,      # default: clip length
    easing: str = "cubic_in_out",            # any resolve_easing name
    hold_frames: int = 0,                    # lead-in hold on start_rect
) -> dict
```

**Rect convention.** A rect `(x, y, w, h)` names the **source region** (in
frame pixels) that the transform scales to fill the frame — a *smaller* region
zooms in, translating the region pans. All rects are **clamped to
`[0, 0, W, H]`** (plan §5: "pad the subject rect … clamp to frame bounds"). This
is the deliberate, clamp-friendly reading of the transform rect and is why
zoom-in is a *shrinking* region rather than an over-scaled negative-origin one.
**§1.1 caveat / semantic note:** whether MLT `affine` reads the rect as
source-crop vs destination-placement is the same class of ambiguity flagged in
§1.1; `effect_pan_zoom` commits to the source-region reading, keeps every emitted
rect inside the frame, and is internally consistent — noted, not a blocker.

**Presets** (computed entirely from the project profile, so they scale across
1080p / 4K / vertical): `zoom_in`, `zoom_out`, `pan_left_to_right`,
`pan_right_to_left`, `pan_top_to_bottom`, `pan_bottom_to_top`,
`kenburns_tl_br`, `kenburns_br_tl`, `kenburns_tr_bl`, `kenburns_bl_tr`.
Zoom presets use a centered 0.6× region; pan/ken-burns presets travel a 0.7×
region between edges/corners.

**Composition.** `preset` and explicit rects compose: a rect overrides the
matching side of the preset (e.g. `preset="zoom_in", end_rect=[…]` keeps the
preset start, overrides the end). Either a preset or *both* rects are required.

**Pipeline.** Pure geometry lives in `pipelines/pan_zoom.py`
(`preset_rects`, `clamp_rect`, `build_pan_zoom_keyframes`); the keyframe string
is emitted through the **existing** `pipelines/keyframes.py::build_keyframe_string`
(`kind="rect"`), identical to `effect_keyframe_set_rect`. The move is a
2-keyframe eased segment `start → end`; `hold_frames > 0` inserts a lead-in hold
(3 keyframes: `0=start`, `hold=start` with easing, `hold+duration=end`). The
registration module `edit_mcp/server/bundles/pan_zoom.py` parses the project,
resolves fps/width/height/clip-length from the profile, snapshots
(`before_pan_zoom`) before writing, appends the `affine`/`transform` filter via
`patcher.insert_effect_xml`, re-serializes, and returns `_ok`/`_err` dicts.

### Omitted / not-folded-in (documented, not faked)

- **Arc / multi-waypoint paths** (the up-then-down move at [03:08]) — `effect_pan_zoom`
  ships the common 2-point move (+ optional hold). A general N-waypoint path is
  already served by calling `effect_keyframe_set_rect` directly with explicit
  keyframe JSON; folding a waypoint list into this tool was left out to keep the
  preset surface small.
- **Rotation / combined-property keyframing** [06:15] — rotation is a separate
  Transform scalar (`rotation`), reachable via `effect_keyframe_set_scalar`.
  `effect_pan_zoom` is position+scale only.
- **Crop "cinematic reveal"** (Crop, Scale and Tilt) [07:03] — expressible today
  as scalar keyframes on the crop/tilt properties; no dedicated wrapper built.
- **Per-keyframe mixed interpolation** (discrete start + smooth tail) — the
  low-level `effect_keyframe_set_rect` supports per-keyframe easing; `effect_pan_zoom`
  exposes a single `easing` for the whole move by design.

### New primitives that would extend this 1:1

None required — the keyframe machinery is complete. Natural follow-ons: a
`waypoints=[...]` parameter for arc paths, an optional `rotation` sweep, and the
§1.1 filter-placement fix (gates on-timeline rendering of the emitted filter).

## Raw summary

- **Effect name:** `effect_pan_zoom` (Ken Burns pan/zoom: profile-computed
  presets or explicit clamped rects → keyframed `affine`/`transform`).
- **Built on:** `pipelines/pan_zoom.py` (pure: `preset_rects`, `clamp_rect`,
  `build_pan_zoom_keyframes`) → `@mcp.tool effect_pan_zoom` in
  `edit_mcp/server/bundles/pan_zoom.py` (auto-imported; single snapshot;
  `patcher.insert_effect_xml`; `_ok`/`_err`), reusing
  `pipelines/keyframes.py::build_keyframe_string`.
- **Missing primitives (for full 1:1):** none — arc waypoints and rotation
  sweeps are extensions, not blockers.
- **§1.1-broken deps:** effect/keyframe root-placement (inherited, not a blocker;
  noted in the tool docstring).
