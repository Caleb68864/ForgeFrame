---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: timelapse / slideshow from images"
author: analysis agent
tags: [kdenlive-mcp, research, slideshow, timelapse, image-sequence, producers]
source_plan: docs/research/2026-07-03-tutorial-effect-analysis/SYNTHESIS.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/13 - Timelapse - Slideshow Effect - Kdenlive 2020 Tutorial.md"
video: dxHC_BzryuA
channel: Victoriano de Jesus
built_tool: media_slideshow
synthesis_gap: 9  # Producers: image sequence (%04d)
---

# Timelapse / Slideshow Tutorial → MCP Tool Surface Mapping

Victoriano de Jesus's *"Timelapse / Slideshow Effect — Kdenlive 2020 Tutorial"*
(`dxHC_BzryuA`, 9:09) analysed against the workshop-video-brain MCP surface
(`edit_mcp/server/tools.py` `media_ingest`/`media_list_assets`,
`adapters/ffmpeg/probe.py`, and the new `edit_mcp/pipelines/slideshow.py` +
`server/bundles/slideshow.py`).

This is landscape tutorial **#21** ("REINFORCE") and maps to **SYNTHESIS gap #9**
(*Producers: solid color, single image, image sequence `%04d`*). The tutorial is
a single, self-contained workflow: **turn a folder of stills into one clip** with
a per-image duration, optional dissolve and optional pan/zoom. Kdenlive does this
natively via the **"Add Slideshow Clip"** project-bin producer. That native path
is an **image-sequence producer** — the exact primitive gap #9 flags as missing —
so it cannot be built today without a producer builder + an ingest/probe
extension. This report ships the **additive route** (`media_slideshow`: images →
`.mp4` in `media/processed/` via FFmpeg, then a normal ingestable clip) and
documents what a native MLT producer would require.

## Technique breakdown (steps, options, [mm:ss])

1. **[01:32]** **Goal:** timelapse of ~329 sequential photos (a skydiving burst).
   Also frames the "how many images can Kdenlive handle" stress-test.
2. **[02:20]** **Add Slideshow Clip.** Project Bin → *Add slideshow clip* → point
   at the photo folder → loads *all* images as **one clip**.
3. **[03:06]** **Options on the slideshow producer:**
   - **Frame duration** — on-screen time per image, expressed
     `HH:MM:SS:FF`. The **FF ("ffs")** field is **frames**, capped at the
     project fps (24fps project ⇒ FF max 24; setting FF=fps ⇒ no net change).
     So per-image time = `seconds + FF/fps`.
   - **Loop**, **Center crop**, **Add dissolve** (crossfade between images),
     **Animation** (pan / pan-and-zoom = Ken Burns).
4. **[03:52]** 329 images @ 5 s ⇒ ~27 min clip. Scaled preview to 360p for
   smooth scrubbing (quality vs performance).
5. **[04:40]** **Retime** via *Clip Properties* → change frame duration to 1 s ⇒
   5 min 29 s; to 12 fps-per-image ⇒ 2 min 44 s.
6. **[05:25]** Clarifies the **FF = frames** semantics (the confusing part).
7. **[06:57]** **Add dissolve** ⇒ each transition cross-dissolves.
8. **[07:00]** **Animation: pan / pan-and-zoom** ⇒ Ken Burns drift (nice for
   slideshows, off for a straight timelapse).
9. **[07:45]** Straight timelapse = **no dissolve, no animation**; pushed to
   **1 frame per image** (329 imgs / 25 fps ≈ 13 s) — deliberately extreme.
10. **[08:32]** Render out to the final video.

## Options named (exact Kdenlive controls)

Add Slideshow Clip; Frame duration (`HH:MM:SS:FF`, FF = frames-per-image capped
at project fps); Loop; Center crop; Add dissolve; Animation (pan / pan-and-zoom);
Clip Properties (retime after the fact); Render.

## Capability mapping

| Step | Kdenlive control | MCP tool | Status | Why |
|---|---|---|---|---|
| Folder of stills → one clip | Add Slideshow Clip (image-seq producer) | **`media_slideshow`** (additive) | **built (additive)** | native producer (gap #9) missing; tool builds an `.mp4` from the folder instead |
| Per-image time (seconds) | Frame duration `SS` | `media_slideshow(duration_per_image_seconds=…)` | **built** | direct seconds override |
| Per-image time (frames) | Frame duration `FF` ("ffs") | `media_slideshow(fps_per_image=…)` | **built** | frames-per-image ÷ project fps ⇒ seconds |
| Scale/fit to project | (Center crop / project profile) | `media_slideshow` scale+pad (crop under Ken Burns) | **built** | letterbox to profile; Ken Burns fills+crops |
| Dissolve between images | Add dissolve | `media_slideshow(crossfade_frames=…)` | **built (small sets)** | FFmpeg `xfade`; per-image filter_complex ⇒ bounded count |
| Pan / pan-and-zoom | Animation | `media_slideshow(kenburns=True)` | **built (simple)** | per-image `zoompan` slow centred zoom (not the full pan-direction menu) |
| Import folder as images | media_ingest / media_list_assets | — | **missing** | `DEFAULT_EXTENSIONS` (`probe.py:16`) excludes `.png/.jpg/...`; no sequence globbing |
| Resulting clip is editable | (normal clip) | `media_ingest` / `clip_insert` | **exists (downstream)** | the produced `.mp4` is an ordinary video and ingests normally |
| Loop | Loop | — | **omitted** | slideshow plays once; loop is a producer property, not modelled |
| Retime after building | Clip Properties | re-run `media_slideshow` | **workaround** | additive route re-renders; native producer would edit `ttl` in place |

## Key constraint: `media_ingest` cannot see images (probe.py:16)

`adapters/ffmpeg/probe.py` `DEFAULT_EXTENSIONS` (line 16) is video/audio only
(`.mp4/.mkv/.mov/.avi/.webm/.mts/.m2ts/.mp3/.wav/.flac`) — **no image
extensions**, and `scan_directory`/`media_ingest` have no `%0Nd` sequence
globbing. So a raw image folder is invisible to ingest (same finding as
`motion-graphics-pipeline.md` §"`media_ingest`"). `media_slideshow` sidesteps
this entirely: it consumes the image folder directly and emits an `.mp4` whose
extension *is* in `DEFAULT_EXTENSIONS`, so the result ingests like any clip.

## Bundle tool spec — `media_slideshow` (BUILT)

```
media_slideshow(
  workspace_path: str,
  image_folder: str,                       # abs, or relative to workspace
  fps_per_image: float = 6.0,              # frames-per-image (the "FF" field)
  duration_per_image_seconds: float|None = None,  # seconds override
  resolution: str|None = None,             # "WIDTHxHEIGHT"; else project profile → 1920x1080
  output_name: str|None = None,            # default slideshow_<folder>.mp4
  kenburns: bool = False,                  # simple per-image zoompan
  crossfade_frames: int = 0,               # xfade dissolve (small sets)
) -> dict
```

Pure logic in `pipelines/slideshow.py`; workspace/profile resolution, FFmpeg
execution and `_ok`/`_err` dicts in `server/bundles/slideshow.py`. Follows
audio-tools conventions: **never touches `media/raw`**, writes to
`media/processed/`, returns a structured dict (output path, image count,
resolution, backend, expected + probed duration, `ingestable: true`).

### Two FFmpeg backends (auto-selected by `choose_backend`)

1. **pattern** (`-framerate F/N -i prefix%0Nd.ext`) — when the folder is a
   uniform, contiguous, single-extension numbered sequence *and* no crossfade /
   Ken Burns. Input rate `fps / frames_per_image` holds each image exactly
   `round(per_image_seconds·fps)` frames. **Scales to thousands** (the 329-image
   timelapse case). Empirically exact (5 imgs @ 0.24 s ⇒ 30 frames / 1.20 s).
2. **filter_complex** (one `-loop 1 -t` / single-frame input per image) — for
   **mixed filenames/extensions/sizes**, `xfade` dissolves, and `zoompan` Ken
   Burns. Bounded by `MAX_FILTERGRAPH_IMAGES=300`; very large *mixed-name* sets
   should be renamed into a uniform sequence to take the pattern backend.

Every backend scales+pads (Ken Burns scales+crops) to the project profile and
emits CFR `yuv420p` H.264, so `ffprobe` yields a predictable duration/resolution
(verified in `tests/integration/test_slideshow_mcp_tool.py`).

### Duration math

`total = n·per_image − (n−1)·crossfade` (each dissolve overlaps two stills).
`per_image = duration_per_image_seconds` if given, else `fps_per_image / fps`.

### Omitted / simplified (documented, not faked)

- **Loop** — the produced clip plays once; loop is a producer property with no
  additive analogue.
- **Full pan menu** — Kdenlive's animation offers directional pans; `kenburns`
  ships a single simple centred slow-zoom, not the pan-direction catalogue.
- **In-place retime** — the native producer edits `ttl` live; the additive route
  re-renders. Acceptable because the output is a normal clip.
- **Native `media_ingest` of images** — left to gap #9's producer path
  (below); `media_slideshow` does not extend `DEFAULT_EXTENSIONS`.

## What a native MLT image-sequence producer would need (analysis only)

The editor-native alternative (SYNTHESIS gap #9, the `%04d` producer) — NOT
built here — would give per-image `ttl` editable inside Kdenlive with no
intermediate video, but is blocked on:

1. **Image-sequence `<producer>` builder.** Emit
   `mlt_service="qimage"` (or `pixbuf`) on a `<producer>` whose
   `resource` is a `.all.<ext>` glob or an FFmpeg-style `%0Nd` pattern; carry a
   **`ttl`** property (frames-per-image = the tutorial's FF field) and optional
   **`loop`**. Register it in the project bin (mirrors the single-file producer
   that `clip_insert` builds today; see `motion-graphics-pipeline.md` §"Import
   PNG image sequence").
2. **Extension scan.** Add `.png/.jpg/.jpeg/.exr/.tga/.webp` to
   `DEFAULT_EXTENSIONS` (`probe.py:16`) plus `%0Nd`/glob detection in
   `scan_directory`, so a sequence is scannable/ingestable and appears in
   `media_list_assets`. (Shared with `sequence_to_alpha_video` and
   `mograph_import`.)
3. **Profile-aware placement.** The producer needs the project profile
   dimensions and an SAR/aspect policy (Kdenlive's *center crop* toggle) so the
   still fits the timeline frame — `set_project_profile` already exists to
   supply width/height/fps.
4. **Optional dissolve/animation as filters**, not baked pixels — a `luma`/mix
   transition between playlist entries (dissolve) and a keyframed
   `qtblend`/affine (pan-zoom), which depend on the same **§1.1 filter/transition
   placement fix** every bundle waits on.
5. **Native vs additive trade-off.** Native = live `ttl` retime, no re-encode,
   smaller project; additive (`media_slideshow`) = **unblocked today**, one
   portable clip, no §1.1 dependency, but a re-render to retime. `media_slideshow`
   is the pragmatic ship; the native producer is the future upgrade that closes
   gap #9 fully.

## Raw summary

- **Tool name:** `media_slideshow` (image folder → timelapse/slideshow `.mp4`).
- **Built on:** `pipelines/slideshow.py` (pure: image listing, timing math,
  numbered-sequence detection, pattern + filter_complex command builders) →
  `@mcp.tool media_slideshow` in `server/bundles/slideshow.py` (profile
  resolution, FFmpeg run, `_ok`/`_err`, writes `media/processed/`).
- **Backends:** pattern (`%0Nd`, scales to thousands) / filter_complex (mixed
  names, `xfade` dissolve, `zoompan` Ken Burns, ≤300 imgs).
- **Missing primitives (for native 1:1):** image-sequence MLT producer
  (`qimage`/`pixbuf`, `ttl`, `loop`); `DEFAULT_EXTENSIONS`+glob scan
  (`probe.py:16`); dissolve/animation-as-filters (needs §1.1 placement fix).
- **§1.1 status:** additive route has **no §1.1 dependency** (renders pixels,
  not MLT filters). The native producer path would inherit §1.1 for
  dissolve/pan.
