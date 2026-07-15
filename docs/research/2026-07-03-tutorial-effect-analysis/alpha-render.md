---
date: 2026-07-03
topic: "Tutorial → MCP mapping: Render Video with Transparent Background (alpha render)"
transcripts:
  - "Render Video with Transparent Background - Kdenlive Tutorial"
status: implemented
tags: [kdenlive-mcp, tutorial-analysis, render, alpha, transparency, compositing]
---

# Alpha-Render Analysis — "Render Video with Transparent Background"

Channel: Nuxttux Creative Studio · 2:09. Companion/payoff to the
motion-graphics pipeline videos: it teaches the single Kdenlive step those
workflows depend on — **exporting a clip with a transparent background** so a
cutout / logo / lower-third / rotoscoped element can be composited elsewhere.

This closes **gap #10** ("Alpha render profile") from `SYNTHESIS.md` and the
alpha half of the `sequence_to_alpha_video` bundle proposed in Video 1 of
`motion-graphics-pipeline.md`. The image-sequence-ingest half of that bundle is
still deferred (see Omissions).

---

## (a) What the tutorial actually configures

The tutorial is **render-window only**. There is *no* special project setting,
no dedicated "transparent background" project profile, and no effect applied
for the sake of alpha. The recipe is:

| Time | Step | Notes |
|---|---|---|
| [00:00] | Establish a clip that already has alpha — an object-selection/SAM mask, a rotoscoped element, or a logo/lower-third animation | alpha comes from the *content*, not a render toggle |
| [00:10] | **Disable the track(s) behind the cutout** so the background is genuinely empty (transparent), not black | the only "project-side" action, and it's just track visibility |
| [00:20] | `Ctrl+Enter` → Render window → **Presets → "Video with alpha"** | the category that carries alpha-capable codecs |
| [00:30] | Pick one of **4 presets** (see below) | preset = codec + pixel format |
| [01:00] | Choose destination/name; render **Selected Zone** → Render to File | zone render is optional/orthogonal |

**The "Video with alpha" presets the video names:**

1. **Alpha MOV** — "somewhat generic, a basic one." → QuickTime Animation (**qtrle**) in a `.mov`, `argb` pixel format.
2. **Alpha VP8** — "lossy and not as widely supported." → `libvpx` VP8 in `.webm`, `yuva420p`.
3. **Alpha VP9** — "successor to VP8, more recent, better support, can be used for web." → `libvpx-vp9` in `.webm`, `yuva420p`.
4. **FFmpeg FFV1** — "lossless, decent compression, overall good choice." → `ffv1` in a matroska/mov, `yuva420p`.

Verdict on the transparent-background mechanism: alpha is preserved **entirely by
the render preset's codec + pixel format**; the only project-side requirement is
that the tracks behind the subject be empty/hidden so nothing fills the alpha.

---

## (b) Mapping to the MCP render machinery

### Render code paths (as found)

- **Profile loader** — `adapters/render/profiles.py`: `RenderProfile` pydantic
  model + `load_profile`/`list_profiles` glob over `templates/render/*.yaml`.
  Adding a YAML file makes a profile discoverable automatically.
- **Melt executor** — `adapters/render/executor.py::_build_melt_command` is the
  **real Kdenlive render path** (a `.kdenlive` project is MLT XML, rendered with
  `melt <proj> -consumer avformat:<out> ...`). Reached via
  `pipelines/render_pipeline.py::run_render` → `execute_render`, which is what
  the `render_preview` MCP tool drives.
- **ffmpeg pipeline** — `pipelines/render_final.py` (used by
  `render_final_tool`) shells `ffmpeg -i <project.kdenlive>`; ffmpeg cannot parse
  a Kdenlive/MLT project, so this path does not actually render timelines. The
  melt path is authoritative for alpha and is what was wired/verified.

### The two blocking bugs for alpha (both in `adapters/render/`)

1. **`_build_melt_command` dropped every advanced consumer property.** It only
   emitted `vcodec/vb/acodec/ab/width/height/frame_rate*` — no `pix_fmt`, no way
   to pass melt properties. Even requesting `pix_fmt=yuva420p` is **not enough on
   its own**: MLT flattens frames onto black before the consumer unless
   `mlt_image_format=rgba` is set, so the alpha channel is lost. Verified
   empirically: VP9 with `pix_fmt=yuva420p` but **without** `mlt_image_format=rgba`
   → output `yuv420p`, no alpha.
2. **`create_render_job` hard-coded a `.mp4` extension.** Alpha needs
   `.webm`/`.mov`/`.mkv` containers; an `.mp4` name with a VP9/qtrle/ffv1 stream
   is wrong.

### Fixes (all within `adapters/render/` + `templates/`, per constraints)

- `profiles.py`: added `pix_fmt`, `mlt_image_format`, `melt_args` (raw
  `key=value` consumer props), `container`, and `disable_audio` fields to
  `RenderProfile` (additive, backward-compatible).
- `executor.py::_build_melt_command`: now emits `mlt_image_format=…`,
  `pix_fmt=…`, `an=1` (when `disable_audio`), and appends `melt_args`
  (e.g. `f=webm`, `vprofile=4`). Non-alpha profiles are untouched (no new flags).
- `jobs.py::create_render_job`: derives the output extension from the profile's
  `container` (falls back to `.mp4`), so alpha jobs land in the right container.

### Profiles added (`templates/render/`)

| Profile | Codec | pix_fmt (encoded) | Container | Tutorial preset |
|---|---|---|---|---|
| `webm-alpha` | libvpx-vp9 | yuva420p (alpha via WebM `alpha_mode=1`) | webm | Alpha VP9 |
| `prores-4444-alpha` | prores_ks (vprofile=4) | yuva444p10le → yuva444p12le | mov | (master-grade addition) |
| `mov-alpha` | qtrle | argb | mov | Alpha MOV |
| `ffv1-alpha` | ffv1 | yuva420p | mkv | FFmpeg FFV1 |

All disable audio (alpha exports are cutouts/logos; AAC-in-WebM is invalid
anyway). Task-required minimum (`webm-alpha` + `prores-4444-alpha`) plus the two
extra tutorial presets. VP8 intentionally skipped (the video itself calls it
superseded by VP9).

They flow through the existing MCP with **no new tool registration**:
`render_list_profiles` globs them automatically, and `render_preview` /
`run_render` render them via the fixed melt executor.

---

## (c) Project-side setting

None required beyond track visibility. The tutorial's only project action is
"disable the track behind the cutout." That is plain track-visibility state and
is *not* implemented here because toggling it in the project XML would require
`patcher.py`/`serializer.py` edits, which are out of scope for this change (and
the existing `track_visibility` MCP tool already covers it). For a clip that is
already the top/only layer over an empty background, no action is needed — MLT
emits transparent pixels where nothing is composited.

---

## (d) Empirical verification (melt + ffprobe)

Rendered a transparent `color:#00000000` MLT project through the real
`execute_render` path for each profile; `ffprobe` confirmed alpha:

```
webm-alpha        -> vp9,   yuv420p   + container tag alpha_mode=1   (VP9/WebM alpha)
prores-4444-alpha -> prores,yuva444p12le                            (alpha channel)
mov-alpha         -> qtrle, argb                                    (alpha channel)
ffv1-alpha        -> ffv1,  yuva420p                                (alpha channel)
```

Note on VP9: WebM stores alpha as a hidden secondary stream flagged by the
container tag `alpha_mode=1`; the *primary* stream still reports `yuv420p`. This
matches how ffmpeg's own `libvpx-vp9 -pix_fmt yuva420p` reference output behaves,
so `alpha_mode=1` is the correct alpha assertion for VP9 (not the stream pix_fmt).

Covered by `tests/integration/test_alpha_render.py` (4 tests, gated on
melt+ffprobe availability) and 9 unit tests in
`tests/unit/test_render_profiles.py`.

---

## RAW DATA SUMMARY

- **workflow_name:** alpha render / "Video with alpha" export
- **project_setting_for_transparency:** none (hide tracks behind the subject;
  alpha comes from the clip's own mask/roto/logo content)
- **render_presets_taught:** Alpha MOV (qtrle/argb), Alpha VP8 (vp8/yuva420p),
  Alpha VP9 (vp9/yuva420p), FFV1 (ffv1/yuva420p)
- **profiles_added:** `webm-alpha`, `prores-4444-alpha`, `mov-alpha`,
  `ffv1-alpha`
- **required_melt_consumer_args:** `mlt_image_format=rgba` (critical — preserves
  alpha), `pix_fmt=<alpha fmt>`, `f=<container>`, `an=1`; ProRes 4444 also
  `vprofile=4`
- **code_touched:** `adapters/render/profiles.py` (fields),
  `adapters/render/executor.py` (`_build_melt_command`),
  `adapters/render/jobs.py` (container-aware extension), `templates/render/*`
- **new_tool_registration:** none (flows through `render_list_profiles` /
  `render_preview` / `run_render`)
- **ffprobe_evidence:** webm-alpha `alpha_mode=1`; prores `yuva444p12le`;
  mov-alpha `argb`; ffv1 `yuva420p`
- **still_deferred:** image-sequence ingest half of `sequence_to_alpha_video`
  (PNG/EXR `%0Nd` producer + extension scan); zone/selected-zone range render;
  a one-call `render_alpha` convenience tool (not needed — profiles suffice)
