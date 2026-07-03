---
date: 2026-07-03
topic: "Tutorial → MCP mapping: external motion-graphics pipelines (Blender / Friction / Glaxnimate → Kdenlive)"
transcripts:
  - "Blender, Friction & Kdenlive - Animation Pipeline"
  - "Glaxnimate vs Friction for Motion Graphics"
  - "Kdenlive 25 - Video Editor (promo)"
status: analysis
tags: [kdenlive-mcp, tutorial-analysis, motion-graphics, compositing, external-pipeline]
---

# Motion-Graphics External-Pipeline Analysis

Scope note: both main videos are **external-tool pipeline** tutorials. The bulk of
the work happens in Friction / Blender / Glaxnimate, *not* Kdenlive. Kdenlive's
role in each is narrow and specific, so the MCP mapping concentrates on the
handful of steps where footage actually crosses into Kdenlive: **asset import
(image sequences, transparent video, .rawr animation clips), track/overlay
placement, blend-mode compositing, and alpha rendering.**

Cross-cutting infrastructure facts (verified in source):

- **`media_ingest`** (`edit_mcp/server/tools.py:106`) is a whole-folder pipeline
  (scan→proxy→transcribe→silence). It only scans extensions in
  `DEFAULT_EXTENSIONS` (`adapters/ffmpeg/probe.py:16`):
  `.mp4 .mkv .mov .avi .webm .mts .m2ts .mp3 .wav .flac`. **No image formats
  (`.png/.jpg/.exr/.tga`), no image-sequence globbing, no `.rawr/.json`
  (Glaxnimate/Lottie), no `.svg`.** Image sequences and animation clips are
  invisible to ingest.
- **`clip_insert`** (`tools.py:1034`) takes an arbitrary `media_path`, but
  (a) always inserts into the *first* video playlist — **no track selection
  parameter**, so it cannot target a top overlay track; (b) probes duration via
  ffprobe — a single transparent `.mov/.webm` works, but a PNG *sequence* needs an
  MLT `<producer>` with a `%0Nd`/glob resource, which is not built.
- **`composite_set/pip/wipe`** (`tools.py:4213-4355`, pipeline
  `pipelines/compositing.py`) emit a *well-formed* `<transition mlt_service=...
  a_track b_track in out>` with full blend-mode routing via `frei0r.cairoblend`
  (incl. `hard_light`, `screen`, `multiply`, `overlay`, all HSL modes —
  `compositing.py:38-65`). **However** the patcher appends it as an
  `OpaqueElement(position_hint="after_tractor")` (`patcher.py:773-777`), and per
  plan §1.2 the serializer **captures but never reads `position_hint`
  (serializer.py:344-351)** → the transition lands at MLT root, *outside* the
  `<tractor>`, where MLT ignores transitions. So composite tools are effectively
  **§1.2-broken** (well-formed XML, wrong placement) even though not named in §1.1.
- **Render profiles** (`templates/render/*.yaml`): `preview`, `draft-youtube`,
  `final-youtube`, `vimeo-hq`, `youtube-4k`, `youtube-1080p`, `master-dnxhr`.
  **None carry an alpha/transparent codec** (no `qtrle`/`prores4444`/`yuva420p`/
  `webm+alpha`). "Render video with alpha" — the single most important Kdenlive
  step in Video 1 — has **no profile**.
- Effect wrappers (chroma key, transparency, transform) attach filters at MLT
  root with custom `track=`/`clip_index=` attrs → **§1.1-broken** (may not render
  until filter-placement is fixed).

---

## VIDEO 1 — "Blender, Friction & Kdenlive - Animation Pipeline"

Channel: Nuxttux Creative Studio · 22:13. Recreating an intro (glowing "coming
soon" text, cloudy sky, lightning, 3D text) using stock footage + Friction +
Blender, with **Kdenlive used only as a format bridge**.

### (a) Step-by-step technique breakdown

| Time | Step | Tool used |
|---|---|---|
| [00:00–01:33] | Gather stock: light-leak clips + night-sky/lightning from Pexels | asset sourcing (external) |
| [01:33–05:24] | **Friction** compositing: "coming soon" text object; Transform→opacity keyframed 0→100 (fade-in); noise-fade **raster effect** (shader) for dissolve; shadow raster effect used as glow | Friction (external) |
| [05:24] | **Link/duplicate text object as a mask**; light-leak overlay set to **hard light** blend, masked into the text shape | Friction blend + mask (external) |
| [05:24–08:27] | Cloud background: solid shape + procedural **clouds shader**; color pushed purple; **visibility range** used to time-gate the object; duplicate cloud for a fade in/out intro (opacity 0→55→0) | Friction (external) |
| [08:27–10:00] | Lightning: stock clips renamed, duplicated to 2 layers; **frame remapping** to accelerate/slow the strike | Friction speed (external) |
| [10:00–17:44] | **Blender** 3D text: add Text → extrude/bevel → convert to mesh → Remesh modifier → material (metallic + colored) → purple world → animate drop-in with ease → **render as PNG sequence** | Blender (external) |
| [17:44–19:14] | **KDENLIVE:** import the PNG **image sequence** ("import images, grab first frame, OK"), place on timeline, **Ctrl+Enter → Render → "Video with alpha"** profile → render transparent video | **Kdenlive** |
| [19:14–21:31] | Back to Friction: import the transparent 3D-text video; add brightness + shadow raster effects; frame-remap for timing; deform lightning (rotate/scale + custom four-corner pinch shader) | Friction (external) |

**Why Kdenlive at all** [17:44]: *"Friction does not import image sequences"* — so
Kdenlive is used purely to convert a Blender **PNG sequence → transparent video**
that Friction can ingest. This is the entire Kdenlive footprint of the video.

### (b) Kdenlive features used (exact)

1. **Image-sequence import** — Project Bin → "import images" → pick first frame →
   auto-detects the numbered sequence as one clip.
2. **Render → "Video with alpha"** render preset — alpha/transparent-preserving
   export (option to uncheck audio).

(Everything else named — Transform/opacity keyframes, noise-fade & clouds
*shaders*, hard-light blend, visibility range, frame remapping, shadow-as-glow,
Blender modeling — happens **outside** Kdenlive and is out of MCP scope.)

### (c) Capability mapping — step → MCP tool

| Kdenlive step | Existing tool(s) | Status | Notes |
|---|---|---|---|
| Import PNG image **sequence** as one clip | `media_ingest` / `media_list_assets` / `clip_insert` | **missing** | ingest ignores `.png` and has no sequence globbing; `clip_insert` builds a single-file `<producer>`, no `%0Nd` sequence producer |
| Place sequence clip on timeline | `clip_insert` | **partial** | inserts only into first video playlist; fine here (single track) |
| **Render "Video with alpha"** | `render_final_tool` / `render_list_profiles` | **missing** | no alpha profile in `templates/render/*.yaml`; all profiles are H.264/opaque |
| (Optional) render audio-off | render profiles | **partial** | audio toggle not a documented param |

Net: **the one thing this video needs Kdenlive for — sequence-in / alpha-out — is
exactly what the MCP cannot do today.** Both endpoints are missing.

### (d) Bundle-tool spec

**`sequence_to_alpha_video`** — one-call bridge replicating the entire Kdenlive
role of this tutorial (import PNG/EXR sequence → 1-clip project → render
transparent video).

```
sequence_to_alpha_video(
    workspace_path: str,
    sequence_dir: str,          # dir of numbered frames, or first-frame path
    pattern: str = "auto",      # auto-detect %0Nd from first frame, or explicit
    fps: float = 0.0,           # 0 = inherit project profile
    codec: str = "qtrle",       # qtrle | prores4444 | webm-vp9-alpha | png-in-mov
    out_path: str = "",         # default renders/<slug>_alpha.mov
    include_audio: bool = False,
)
```

Composes primitives: [new] `media_ingest_sequence` → [new] `alpha_render_profile`
+ existing `render_final_tool` melt path.

**NEW primitives needed:**
- `media_ingest_sequence(sequence_dir, pattern, fps)` — build an MLT image-sequence
  `<producer>` (`resource="frames/%05d.png"`, `ttl`, `loop`), register in bin.
  Also extend `DEFAULT_EXTENSIONS`/scan to recognize `.png/.jpg/.exr/.tga`.
- **Alpha render profile(s)** — add `templates/render/alpha-qtrle.yaml`,
  `alpha-prores4444.yaml`, `alpha-webm.yaml` (yuva420p/vp9). Pure config.
- `clip_insert` track-target parameter (shared with Video 2) so the sequence can
  land on a chosen track.

**§1.1/§1.2-broken dependencies:** none on the render path itself (melt render path
works per plan §1.3). The alpha-render feature is *additive* and unblocked.

---

## VIDEO 2 — "Glaxnimate vs Friction for Motion Graphics"

Channel: Kdenlive Tutorial (Nuxttux) · ~15:29. Survey of doing motion graphics
*with* Kdenlive: (1) Kdenlive's own new Transform/on-monitor rotate feature,
(2) native **Glaxnimate** animation-clip integration, (3) the **Friction**
render-reference workaround, (4) faking motion graphics natively (rotoscoping,
solid-color shapes + transform, SVG import).

### (a) Step-by-step technique breakdown

| Time | Step | Tool used |
|---|---|---|
| [01:33–02:19] | Add **Transform** effect to a clip; with **edit mode** on the project monitor, scale + **rotate via the new on-monitor rotate handle** | Kdenlive Transform effect |
| [02:19–02:40] | Settings → enable **"built-in effects"** → get a built-in transform with **flip** controls; enable via the project-monitor transform toggle button | Kdenlive built-in transform |
| [02:40–03:05] | Notes missing feature: **movable pivot / anchor point** — *"on the roadmap"*, crucial for natural rotation | Kdenlive (not yet available) |
| [03:05–04:00] | Configure integration: Settings → Configure Kdenlive → Environment → Default Apps → **Animation editing = Glaxnimate path** (flatpak caveat; use AppImage) | Kdenlive config |
| [04:00–04:38] | Project Bin → dropdown by play button → **"Create animation"** → choose save path + **duration** (matches footage, ~6 s) → creates a **Glaxnimate (.rawr) clip** in the bin | Kdenlive native Glaxnimate clip |
| [04:38–05:23] | Drag animation clip to timeline; **double-click opens it in Glaxnimate** with the underlying video already loaded as reference | Kdenlive↔Glaxnimate round-trip |
| [05:23–06:53] | In Glaxnimate: draw shape (thought bubble), Transform→Position **keyframes** (record-keyframes toggle), keyframed **fill** color; save → clip animates live back in Kdenlive | Glaxnimate (external, but MLT-native clip) |
| [06:53–07:38] | **Friction workaround**: at picture lock, **render the segment / a low-res reference** from Kdenlive → import into Friction as motion-graphics reference | Kdenlive **range/segment render** |
| [10:43–11:30] | "Fake" motion graphics natively in Kdenlive: **rotoscoping** effect; **solid-color clips** shaped into bubbles then animated with a **Transform**; import graphics from **Inkscape/Photoshop (SVG/PNG)** | Kdenlive rotoscoping + transform + import |
| [13:16–14:02] | Final pipeline reality: animate in Friction, **import the animation into Kdenlive for sound design / assembly / final render** | Kdenlive assembly + audio |

### (b) Kdenlive features used (exact)

1. **Transform** effect (`qtblend`/`affine`-family) with on-monitor edit mode +
   new **rotate handle**.
2. **Built-in effects** (Settings toggle) → built-in transform with **flip H/V**.
3. **Pivot/anchor point** — *named as missing / roadmap*.
4. **Glaxnimate native integration**: default-app config → **Create animation**
   → `.rawr` animation producer (`mlt_service` = glaxnimate/`webvfx`-style animation
   clip) → double-click round-trip editing.
5. **Range / low-res reference render** (render a timeline zone/segment).
6. **Rotoscoping** effect (spline mask).
7. **Solid-color clip** producer (`color:` producer) shaped + transformed.
8. **SVG / PNG import** from Inkscape.

### (c) Capability mapping — step → MCP tool

| Kdenlive step | Existing tool(s) | Status | Notes |
|---|---|---|---|
| Transform effect (scale/rotate) | `effect_add`, `effect_keyframe_set_rect` | **partial** | wrapper exists but filters attach at MLT root → **§1.1-broken** placement; static-only unless keyframe string passed |
| On-monitor rotate / flip / **pivot** | — | **missing** | UI-only; pivot not even in Kdenlive yet |
| Built-in transform flip | `effect_add` | **partial** | no dedicated flip wrapper; frei0r `mirr0r`/`flippo` not wrapped |
| **Create Glaxnimate `.rawr` animation clip** | — | **missing** | no tool builds/registers a glaxnimate animation producer; ingest ignores `.rawr` |
| Import existing `.rawr`/Lottie animation | `media_ingest`, `clip_insert` | **missing** | not in `DEFAULT_EXTENSIONS`; no animation producer builder |
| Place animation on **overlay/top track** | `clip_insert` + `track_add` | **partial** | `track_add` works; `clip_insert` has **no track param** (first-playlist only) |
| **Render segment / low-res reference** | `render_final_tool`, `render_preview` | **partial** | whole-timeline only; no in/out-zone or guide-zone range render (plan §3 Medium) |
| Rotoscoping shape mask | `mask_set_shape`, `effect_object_mask`, `mask_apply` | **partial→broken** | `roto-spline` ParamType missing (plan §1.3) → excluded from catalog; can't be saved in presets; filter placement §1.1 |
| Solid-color clip as shape | — | **missing** | no `color:` producer builder tool |
| Import SVG/PNG graphic | `media_ingest`, `clip_insert` | **missing** | `.svg/.png` not scanned; single-image producer not built |
| Composite animation over footage (blend) | `composite_set`, `composite_pip` | **partial→broken** | blend modes exist incl `hard_light`, but placed at root via `position_hint` → **§1.2-broken** |
| Final assembly + sound design of imported animation | `assembly_build`, `clip_insert`, `audio_*` | **exists** | audio tools operate on standalone files, not timeline-attached (plan §3) |

### (d) Bundle-tool spec

**`mograph_import`** — ingest a motion-graphics asset (transparent video, image
sequence, `.rawr`/Lottie animation, or SVG/PNG), place it on a dedicated top
video track at a timestamp, and composite it over the base layer with a blend
mode. This is the "motion-graphics asset import" workflow the project direction
calls for (overlay_insert / mograph_import).

```
mograph_import(
    workspace_path: str,
    project_file: str,
    asset_path: str,             # .mov/.webm(alpha) | seq dir | .rawr/.json | .svg/.png
    at_seconds: float,
    duration_seconds: float = 0.0,   # 0 = asset native / clip length
    track: int = -1,             # -1 = create/ use top overlay track
    blend_mode: str = "normal",  # normal|screen|hard_light|... (maps composite_set)
    key: str = "",               # "" | chroma:<hexcolor> | luma  (pre-key opaque overlays)
    fit: str = "contain",        # contain|cover|stretch|none (geometry)
    fade_in: float = 0.0,
    fade_out: float = 0.0,
)
```

Composes primitives: [new] asset-type dispatch (`media_ingest_sequence` /
`animation_clip_create` / single-image producer / alpha-video passthrough) →
[new] `track_add`-or-reuse top track → `clip_insert` **with new track param** →
optional `effect_chroma_key` → `composite_set(blend_mode)` → `effect_fade`.

**Companion authoring tool** `animation_clip_create` (mirrors Kdenlive "Create
animation") for the Glaxnimate round-trip:

```
animation_clip_create(workspace_path, out_path, duration_seconds, width=0, height=0)
    -> registers a glaxnimate .rawr producer in the bin + returns path to open externally
```

**NEW primitives needed:**
- `clip_insert` **track-target parameter** (also needed by Video 1) — remove the
  first-playlist-only limitation.
- Single-image producer builder (`.png/.jpg/.svg` → `<producer mlt_service=
  qimage/pixbuf>`); extend scanned extensions.
- `.rawr`/animation producer builder (`animation_clip_create` + ingest recognition).
- `media_ingest_sequence` (shared with Video 1).
- Solid-`color:` producer builder (for "shape from solid color" native mograph).
- Flip wrapper (`effect_flip` → frei0r mirror/mirr0r) — minor.
- Range/zone render option on `render_final_tool` (in/out seconds or guide zone) —
  for the Friction low-res-reference workaround.
- `roto-spline` ParamType (plan §1.3) to unblock rotoscoping.

**§1.1/§1.2-broken dependencies (must be fixed for this bundle to actually render):**
- `composite_set` blend placement — **§1.2** (`position_hint` never read →
  transition escapes the tractor). Hard blocker: blend compositing is the core of
  overlaying motion graphics.
- Transform / chroma-key / fade filter placement at MLT root — **§1.1** (effect
  stack may not associate with clips).
- `effect_fade` `affine`/`rect` property mismatch — **§1.1**.
- Rotoscoping `roto-spline` gap — **§1.3**.
- `clip_speed` no-op (relevant if the bundle ever exposes frame-remap/speed on the
  imported animation) — **§1.1**.

---

## VIDEO 3 — "Kdenlive 25 - Video Editor" (promo, 1:30)

Music-bed promo/montage. **No editing features are named or demonstrated** — the
only spoken content is a storytelling aphorism ("better to focus on storytelling
versus beautiful pictures"). No name-drops of tools, effects, or Kdenlive 25
features. Nothing to map. (The title implies Kdenlive 25.x, whose relevant new
features — SAM2 object mask, on-monitor rotate, built-in effects — surface in
Video 2, not here.)

---

## RAW DATA SUMMARY

### Video 1 — Blender/Friction/Kdenlive Animation Pipeline
- **workflow_name:** `sequence_to_alpha_video` (image-sequence in → transparent video out)
- **missing_primitives:**
  - `media_ingest_sequence` (PNG/EXR/TGA/JPG numbered-sequence MLT producer + extension scan)
  - alpha render profiles (`alpha-qtrle.yaml`, `alpha-prores4444.yaml`, `alpha-webm.yaml`)
  - `clip_insert` track-target param
  - render `include_audio=false` toggle
- **proposed_bundle_tool:** `sequence_to_alpha_video(workspace_path, sequence_dir, pattern="auto", fps=0.0, codec="qtrle", out_path="", include_audio=False)`
- **§1.1/§1.2-broken_dependencies:** none blocking (additive; melt render path is sound)

### Video 2 — Glaxnimate vs Friction for Motion Graphics
- **workflow_name:** `mograph_import` (overlay_insert) + companion `animation_clip_create`
- **missing_primitives:**
  - `clip_insert` track-target param (first-playlist-only today)
  - single-image producer builder (.png/.jpg/.svg) + extension scan
  - `.rawr`/Lottie animation producer builder (`animation_clip_create`)
  - `media_ingest_sequence` (shared w/ Video 1)
  - solid-`color:` producer builder
  - `effect_flip` wrapper (frei0r mirror)
  - range/zone render option on `render_final_tool`
  - `roto-spline` ParamType (unblock rotoscoping)
- **proposed_bundle_tool:** `mograph_import(workspace_path, project_file, asset_path, at_seconds, duration_seconds=0.0, track=-1, blend_mode="normal", key="", fit="contain", fade_in=0.0, fade_out=0.0)`
- **§1.1/§1.2-broken_dependencies:**
  - `composite_set` blend placement — **§1.2** (position_hint unread → transition at root, not in tractor) — HARD BLOCKER
  - effect filter placement at MLT root (transform, chroma_key, fade) — **§1.1**
  - `effect_fade` affine/rect mismatch — **§1.1**
  - rotoscoping `roto-spline` — **§1.3**
  - `clip_speed` no-op — **§1.1** (only if speed exposed)

### Video 3 — Kdenlive 25 promo
- **workflow_name:** n/a
- **missing_primitives:** none (no features named)
- **proposed_bundle_tool:** none
- **§1.1-broken_dependencies:** none
</content>
</invoke>
