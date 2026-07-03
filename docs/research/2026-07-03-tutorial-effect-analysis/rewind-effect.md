---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: VHS Rewind (reverse clip)"
author: analysis agent
tags: [kdenlive-mcp, research, reverse, speed, vhs, glitch, ffmpeg]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Rewind effect (VHS style) in Kdenlive.md"
video: "https://www.youtube.com/watch?v=MnErqP9iIWU"
channel: Romain Pellerin
duration: "3:57"
bundle_tool: effect_rewind
---

# "Rewind effect (VHS style) in Kdenlive" → MCP Tool Surface Mapping

Romain Pellerin's short tutorial (video id `MnErqP9iIWU`, 3:57) builds a **VHS
cassette-rewind** effect: a snippet of footage is duplicated, sped up ~3x,
**played in reverse**, dressed with a rewinding-cassette sound and a blinking
"rewind" icon, and finished with a four-effect VHS look (glitch bars, RGB
split, grain, sepia). It is the classic **play → rewind → resume** beat.

Analysed against the workshop-video-brain MCP surface (`edit_mcp/server/tools.py`,
`pipelines/effect_presets.py`, `pipelines/effect_wrappers/`,
`adapters/ffmpeg/`, `adapters/kdenlive/patcher.py`) and against the improvement
plan, where **reverse clip is §3-Low** and **`clip_speed` is a §1.1 no-op**
(MLT speed needs a `timewarp:`/`timeremap` producer, not a `<filter>`).

## a) Technique breakdown (steps, times, exact names)

| Time | Action |
|---|---|
| [00:00] | Goal: a **very short VHS-style rewind** effect. |
| [00:12] | **Duplicate** the clip (copy the left-hand clip to the right-hand side) — the rewind is a *second* copy placed after the original, so the original keeps playing forward, then the copy rewinds. |
| [00:20] | On the copy, **change the speed** and **speed it up 3×**, then **reverse the clip**. (In Kdenlive: clip Speed dialog, negative/reverse.) |
| [00:38] | **Remove the audio** track of the reversed copy. |
| [00:45] | Replace it with the **sound of a rewinding cassette** (a royalty-free clip from pixabay.com). |
| [00:52] | Add a **blinking "rewind" icon** — a random SVG made to blink: **5-frame** icon duration, **5-frame** gap between icons. Scaled to **40%** with the **Transform** effect. |
| [01:30] | Now the **four effects** (author disables all, then enables one at a time). |
| [01:35] | **1. Glitch** — the horizontal bars common to old cassettes. Params: frequency, count, size, intensity. Recommends **block height = 0 px** so it looks natural. |
| [02:17] | **2. RGB split** ("LGB split") — splits red/green/blue channels and separates them; **distance ≈ 0.54** works well. |
| [02:44] | **3. Grain / noise** — recommends **not above 50** or it is too much. |
| [03:04] | **4. Sepia via "car" (tcolor / Technicolor) effect** — avoid the built-in Sepia (too strong, no control); the tcolor effect exposes presets, and the **"CPR"** and **"old photo"** options look good. |
| [03:51] | Done. |

## b) Kdenlive effects used (exact names → MLT service)

| Tutorial step | Kdenlive name | MLT service | In catalog |
|---|---|---|---|
| Speed up 3× + reverse | **Speed** (reverse) | needs `timewarp:`/`timeremap` producer | ❌ `clip_speed` is a **no-op** (§1.1); **not** a `<filter>` |
| Glitch bars | **Glitch** | `frei0r.glitch0r` | ✅ `frei0r_glitch0r` (wrapper) + inside `effect_glitch_stack` |
| RGB split | **RGB split** | `frei0r.rgbsplit0r` | ✅ inside `effect_glitch_stack` |
| Grain / noise | **Grain** | `grain` (MLT) | ✅ `grain` (wrapper `effect_grain`) |
| Sepia | **Technicolor** | `tcolor` | ✅ `tcolor` (wrapper `effect_tcolor`) |
| (VHS extras) | Old Film / Scanlines | `oldfilm`, `frei0r.scanline0r` | ✅ `effect_oldfilm`, `effect_frei0r_scanline0r` |
| Blinking icon | SVG + **Transform** | `qtblend`/producer | ⚠️ no image-overlay insertion primitive |

## c) Capability mapping (tutorial step → MCP status)

| Capability | MCP tool(s) | Status | Notes |
|---|---|---|---|
| **Reverse the clip segment** | **`effect_rewind`** (new) | **exists (ffmpeg route)** | MLT reverse needs a timewarp producer or pre-reversed media; the reliable route today is **ffmpeg** — render the segment reversed to `media/processed/` and insert it. Fully additive. |
| Speed up (3×) | **`effect_rewind`** `speed=` param | **exists (ffmpeg route)** | Applied in the same ffmpeg pass (`setpts` + `atempo` chain). `clip_speed` (the filter) stays a §1.1 no-op. |
| Duplicate clip after original (play→rewind→resume) | **`effect_rewind`** insertion | **exists** | Reversed file registered as a producer and inserted at `clip_index+1` on the same track via the existing `AddClip` / `patch_project` path. |
| Remove audio on the copy | ffmpeg `-an` in `effect_rewind` | **partial** | When the source has no audio the reverse pass drops it; a source **with** audio keeps a reversed track (the tutorial swaps in cassette SFX manually). |
| Rewinding-cassette SFX | `audio_*` tools + `clip_insert` | **manual follow-up** | Not automated; add the SFX to `media/raw`, enhance, and place it. Out of scope for the bundle. |
| Blinking rewind icon (SVG, 5f on/5f off, 40%) | — | **missing** | No PNG/SVG overlay-insertion primitive (`png_overlay_insert` is listed future work in §3-Low). Would also need a blink (flash) keyframe pattern + Transform scale. |
| **Glitch bars** | `effect_glitch_stack` / `effect_frei0r_glitch0r` | **exists** | `effect_rewind(vhs_overlay=True)` layers the glitch stack automatically. |
| **RGB split** | inside `effect_glitch_stack` (`frei0r.rgbsplit0r`) | **exists** | Bundled into the glitch stack. |
| **Grain / noise** | `effect_grain` | **exists** | Available as a follow-up wrapper; the glitch stack also carries an exposure/grade filter. |
| **Sepia (tcolor)** | `effect_tcolor` | **exists** | Available as a follow-up wrapper. |
| Old-film / scanline VHS dressing | `effect_oldfilm`, `effect_frei0r_scanline0r` | **exists** | Layered by `effect_rewind(vhs_overlay=True)` alongside the glitch stack. |
| Filter placement renders in Kdenlive | (all effect tools) | **known issue (§1.1/§1.2)** | Effect-stack filters attach at the MLT root with `track=`/`clip_index=` rather than nesting in the `<entry>`; may not render. **Shared by every effect tool; noted, not a blocker.** |

## d) Bundle tool — `effect_rewind`

Produces the **reversed, sped-up copy** of a clip segment and inserts it right
after the segment (the play → rewind → resume pattern), optionally layering the
VHS look. Reverse/speed run through **ffmpeg** (the reliable route), never
touching `media/raw` originals.

```
effect_rewind(
    workspace_path: str,
    project_file: str,
    track: int,             # playlist / track index
    clip_index: int,        # real-clip index on that track
    start_seconds: float,   # segment start within the source media
    end_seconds: float,     # segment end (> start)
    speed: float = 2.0,     # rewind speed multiplier (atempo chaining for >2×)
    vhs_overlay: bool = True # layer glitch stack + oldfilm + scanlines
) -> dict
```

Pipeline: `edit_mcp/pipelines/rewind.py` (pure: `segment_duration`,
`reversed_duration`, `reversed_frame_count`, `atempo_factors`/`atempo_chain`,
`build_video_filter`/`build_audio_filter`, `build_reverse_args`,
`reversed_clip_name`). Registration: `edit_mcp/server/bundles/rewind.py`
(`from workshop_video_brain.server import mcp`; auto-discovered).

Flow:

1. Resolve `(track, clip_index)` → the clip's producer **resource** (source
   media) + its playlist entry position.
2. **ffmpeg** renders the `[start, end]` window reversed and `speed`× faster to
   `media/processed/<stem>_rewind_<start>-<end>_x<speed>.mp4`. The filtergraph
   **trims before reversing** so only the segment is buffered:
   video `trim,setpts,reverse,setpts=PTS/speed`; audio (when present)
   `atrim,asetpts,areverse,<atempo chain>`; `-an` when the source has no audio.
   `media/raw` originals are only ever **read**; a guard refuses any output path
   under `media/raw`.
3. **Snapshot** (`before_effect_rewind`), then register the reversed file as a
   producer and insert it at `clip_index+1` on the same track via `AddClip` /
   `patch_project`, and serialize.
4. If `vhs_overlay`, best-effort layer `effect_glitch_stack` + `effect_oldfilm`
   + `effect_frei0r_scanline0r` on the reversed clip (failures reported in
   `overlay_errors`, never fail the tool).

Returns `{reversed_media, producer_id, inserted_position, new_clip_index,
source_media, include_audio, speed, expected_duration_seconds, expected_frames,
vhs_overlay, effects_applied, overlay_errors, ffmpeg_command, snapshot_id}`.
Error-result convention throughout (missing project/clip, inverted window,
non-positive speed, unresolvable source media, ffmpeg failure, snapshot failure).

## e) Honest omissions (implemented subset only)

`effect_rewind` reproduces the **reverse + speed + VHS look + timeline
insertion** — the mechanical core — but not the full showcase:

1. **Rewinding-cassette SFX** — the tutorial mutes the copy and drops in a
   cassette-rewind sound. `effect_rewind` reverses whatever audio the segment
   has (or `-an` if none); it does **not** fetch/insert an SFX. Add it manually
   via `media/raw` + `audio_*` + `clip_insert`.
2. **Blinking rewind icon** — the SVG overlay (5-frame blink cycle, 40% scale
   via Transform) is **not built**: there is no image/SVG overlay-insertion
   primitive (`png_overlay_insert` remains §3-Low future work), and no
   flash/blink keyframe helper.
3. **Exact VHS parameters** — the tutorial's specific values (glitch block
   height 0 px, RGB-split distance 0.54, grain ≤ 50, tcolor "CPR"/"old photo")
   are **not** dialed in; the overlay applies the existing `effect_glitch_stack`
   defaults plus oldfilm/scanlines. Tune afterwards with the wrapper tools /
   `effect_keyframe_*`.
4. **Speed via a real timewarp producer** — `effect_rewind` sidesteps the §1.1
   `clip_speed` no-op by baking speed into the ffmpeg render, so the result is a
   normal-rate producer. This is deliberate (the reliable route) but means the
   speed is **not** editable as a live Kdenlive speed property afterwards.
5. **§1.1/§1.2 filter placement** — the overlay effects attach at the MLT root
   (shared open issue affecting every effect tool); noted, not a blocker.

## f) Follow-up primitives that would complete the effect

- `png_overlay_insert` / SVG overlay insertion + a **blink/flash keyframe**
  helper (the rewind icon; also useful for lower-thirds and callouts).
- A real **timewarp / timeremap** producer path (§3 "Working speed control") so
  speed/reverse become live, editable Kdenlive properties instead of baked media.
- A small **SFX-library / one-shot sound insert** helper (cassette rewind, whooshes).
- Keyframable VHS-wrapper params so the tutorial's exact glitch/RGB/grain/tcolor
  values can be emitted directly rather than tuned after the fact.
