---
date: 2026-07-03
topic: "Kdenlive tutorial → MCP capability mapping: split / quad screen"
author: analysis agent
tags: [kdenlive-mcp, research, compositing, split-screen, quad-screen, transform]
source_plan: docs/plans/2026-07-03-kdenlive-mcp-improvements.md
source_transcript: "vault/Transcripts/Kdenlive Tutorials/Kdenlive Two Ways To Create Split Or Quad Screen Videos.md"
video: https://www.youtube.com/watch?v=7C2oP2z0m3Y
---

# Split / Quad-Screen Tutorial → MCP Tool Surface Mapping

Tutorial #15 from `vault/Research/Kdenlive Tutorial Landscape - Uncovered
Effects.md`: **"Two Ways To Create Split / Quad Screen Videos"** (Grep Haxs,
8:55, Kdenlive 19.12.3 → 24.1). Analysed against the workshop-video-brain MCP
surface (`edit_mcp/server/tools.py`, `pipelines/compositing.py`). The closest
existing machinery is `composite_pip` / `apply_pip` (frei0r.cairoblend +
`geometry` string) — this bundle reuses it.

## What the video actually teaches

Two hand workflows that produce the *same* layout — several sources scaled into
a grid — differing only in the tool used to scale/place each source:

1. **Position and Zoom effect** (`Position and Zoom`, aka `qtblend`/`pan-zoom`
   family). Type "zoom" in the effects list, drop it on the clip, set **height =
   540** (half of 1080). The scaled video then does not span the cell width, so
   tick the **"distort"** box to stretch it to fill (breaking aspect ratio).
   Adjust **axis X / axis Y** for placement.
2. **Composite and Transform transition** (`qtblend`, "Composite and
   Transform"). Right-click the clip → **Insert composition → Composite and
   Transform**. Same size/position fields as Position-and-Zoom **plus rotation
   and opacity**. Set **height = 540**, **axis Y = 540**, tick **distort**.

Layouts demonstrated:

- **Split screen** (2 sources): one on top half, one on bottom (a `2v` layout in
  this bundle's vocabulary). The transcript uses height 540 + Y 540 for the
  second source.
- **Quad screen** (4 sources): "must have four video tracks available". Each
  cell is **height 540, width 960**, positioned via **axis X** and **axis Y =
  540** for the lower row. Explicit tutorial values: `540h × 960w`, `Y=540`.

Key takeaways that shaped the tool design:

- Geometry is trivial arithmetic off the profile: halve width and/or height,
  place at the half offsets. Deterministic → pure function.
- "distort" = **stretch to fill the cell** (aspect broken). Not ticking it =
  the source keeps aspect and sits smaller inside the cell (letterboxed). These
  are exactly the two crop modes the bundle exposes (`stretch` vs `fit`).
- Nothing in the video crops-to-fill (cover). Cover would need a per-clip crop
  effect; it is **not** in scope for a composite-geometry-only tool.
- The video's mechanism is the **qtblend** "Composite and Transform" service;
  this bundle instead reuses the **cairoblend + geometry** `apply_pip` path for
  code reuse. Functionally both scale+place `b_track`; the placement-render
  caveat (§1.1/§1.2) applies either way.

## Features / effects named

Position and Zoom effect (height, axis X, axis Y, **distort** checkbox);
Composite and Transform transition (`Insert composition`; height, width, axis
X/Y, **rotation**, **opacity**, distort); multiple video tracks (≥4 for quad);
project-monitor full-screen QC; render.

## Capability mapping

| Step | MCP tool | Status | Why |
|---|---|---|---|
| Position-and-Zoom scale to half (height 540) | `effect_add("qtblend"/"pan-zoom")` + `effect_keyframe_set_rect` | partial | scale expressible via rect; no "half-cell" helper; static; §1.1 placement. |
| "distort" fill-cell (break aspect) | `composite_split_screen(crop="stretch")` | **exists (new)** | this bundle. |
| Keep-aspect (letterbox) placement | `composite_split_screen(crop="fit")` | **exists (new)** | this bundle. |
| Composite and Transform (scale+place) | `composite_set(geometry=…)` / `composite_pip` | exists | cairoblend/qtblend + geometry present. |
| …with **rotation** | — | **missing** | neither `composite_set` nor this bundle sets a rotation angle; qtblend `rotation` unmodelled. |
| …with **opacity** | `composite_split_screen` (opacity in geometry) | partial | opacity encoded in geometry string; per-cell override not surfaced as an arg. |
| 2-up split (top/bottom or side/side) | `composite_split_screen(layout="2v"/"2h")` | **exists (new)** | — |
| Quad (2×2, 4 tracks) | `composite_split_screen(layout="4")` | **exists (new)** | — |
| Gap / gutter between cells | `composite_split_screen(gap_px=…)` | **exists (new)** | background shows through; not shown in video but common. |
| Colored border/frame | `composite_split_screen(border_px=…, border_color=…)` | partial | `border_px` insets cells (geometric); painting a colour needs a colour clip on the base track — advisory only. |
| Full-screen QC / render | `render_preview` / `render_final_tool` | exists | — |

## Honest subsets / omissions

- **Rotation** (a headline feature of the Composite-and-Transform path) is not
  implemented — cells are axis-aligned rectangles.
- **crop="cover"** (center-crop-to-fill, no distortion + no letterbox) is not
  implemented: a single composite/qtblend geometry cannot hard-clip its source.
  It would require a per-clip crop effect (`avfilter.crop` / `frei0r.crop0r`).
  Only `fit` (letterbox) and `stretch` (distort) are offered.
- **border_color** is advisory: the composite path renders whatever is on the
  `base_track`; a coloured border/gutter requires a colour clip on that track.
- **No auto track provisioning**: the caller must already have the background +
  cell tracks (the video notes "must have four video tracks" for quad); the
  tool composites onto existing tracks, it does not create them.
- **§1.1 / §1.2 placement caveat** (`docs/plans/2026-07-03-kdenlive-mcp-improvements.md`):
  the composition is appended at the MLT root via the shared patcher; whether
  Kdenlive renders it in place is subject to the composition-placement work.
  Noted, **not** a blocker — this matches every other composite tool in the repo.

## Bundle tool spec — `composite_split_screen`

```
composite_split_screen(
  workspace_path: str,
  project_file: str,
  layout: str,             # "2h" side-by-side | "2v" top-bottom | "4" quad
  tracks: str,             # comma-separated cell tracks in layout order
                           #   2h: left,right  2v: top,bottom  4: TL,TR,BL,BR
  start_frame: int,
  end_frame: int,
  base_track: int = 0,     # background track each cell composites over
  crop: str = "fit",       # "fit" (letterbox) | "stretch" (distort, = "distort")
  gap_px: int = 0,         # gutter between cells (background shows through)
  border_px: int = 0,      # uniform inset on every cell edge
  border_color: str = "#000000",  # advisory (needs colour clip on base_track)
)
```

Pure functions in `edit_mcp/pipelines/split_screen.py`:
`compute_cells(layout, width, height, gap_px, border_px, crop) -> list[Cell]`
(geometry math off the profile) and `apply_split_screen(project, layout,
tracks, start_frame, end_frame, …)` which reuses
`compositing.apply_composite(blend_mode="cairoblend", geometry=cell.geometry())`
once per cell over `base_track` — the same machinery as `apply_pip`.

**NEW primitives that would deepen this later:** qtblend `rotation` param;
per-clip crop effect for true `cover`; colour-clip producer for real borders;
auto track-add for the required background + cell tracks.

## Raw summary

- **Effect name:** `composite_split_screen` (split / quad-screen grid layout)
- **Existing machinery reused:** `pipelines/compositing.apply_composite`
  (frei0r.cairoblend + `geometry`), the `apply_pip` path.
- **Layouts:** `2h` (side-by-side), `2v` (top-bottom), `4` (quad 2×2).
- **Crop modes:** `fit` (aspect-preserving letterbox), `stretch` (the video's
  "distort" fill).
- **Missing / omitted:** rotation; `cover` crop; painted borders; auto track
  provisioning.
- **§1.1/§1.2 deps:** composition root-placement (shared with all composites).
