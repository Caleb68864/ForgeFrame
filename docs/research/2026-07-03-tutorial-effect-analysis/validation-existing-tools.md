---
title: "Validation — Existing-Tool Tutorials (SAM2 Object Mask, PiP, LUT grading)"
date: 2026-07-03
type: research
tags: [kdenlive, tutorials, validation, masking, compositing, color]
---

# Validation: tutorials whose techniques we already cover

Three tutorials picked from
`vault/Research/Kdenlive Tutorial Landscape - Uncovered Effects.md` (items #7,
#14, #25) — all flagged **REINFORCE**, i.e. we ship a primitive already, so the
job is to *confirm coverage*, surface parameter/workflow gaps, and propose (not
build) fixes. One small additive gap (SAM2 mask-file consumption) was
implementable without touching existing files and **was** built (see §1).

Transcripts (in the ForgeFrame vault):

- `vault/Transcripts/Kdenlive Tutorials/Object Mask - Kdenlive Tutorial.md`
- `vault/Transcripts/Kdenlive Tutorials/2024 Kdenlive Tutorial - Picture in Picture Effect.md`
- `vault/Transcripts/Kdenlive Tutorials/How to Apply LUTs for Color Grading in Kdenlive 2025.md`

**Coverage verdicts (one line each):**

1. **SAM2 Object Mask** — PARTIAL → improved. Our `object_mask` is a parametric
   shape spot, not SAM2; the app plugin emits a **Shape Alpha (`shape`) effect +
   a mask video file** we previously could not consume. Built `mask_set_from_file`
   to consume any such matte. Running SAM2 itself stays out of scope (app plugin).
2. **Picture in Picture** — COVERED (different technique). `composite_pip` gets
   the same on-screen result via a composite transition; the tutorial's Transform
   route exposes opacity / rotation / keyframed motion / borders we don't. Propose
   params only (would touch existing files).
3. **LUT grading 2025** — COVERED. Matches `color_apply_lut` exactly; the only new
   delta is the **interpolation mode** control (`av.interp`), which we don't expose.
   Propose param only. Delta appended to the existing LUTs guide.

---

## 1. SAM2 Object Mask (Kdenlive 25.04) — #7

**Video:** [Object Mask - Kdenlive Tutorial](https://www.youtube.com/watch?v=4Pw9b6xhO_k)
(Nuxttux Creative Studio, 2025-06-02)

### What the tutorial teaches

Kdenlive 25.04's local-AI **Object Mask** (SAM2 / Segment Anything v2):

1. Install via *Settings → Configure Kdenlive → Plugins → Object detection →
   Install*, then download a model (tiny/small/…), pick CPU or GPU.
2. In the **project bin** clip monitor, set a tight in/out (masking a whole clip
   is slow), open the **Create Object Mask** panel from the effects/composition
   stack, click **Create new mask**. Left-click a point on the subject (shift-click
   adds points, ctrl-click subtracts); scrub and add points over time to follow the
   subject; **Generate mask**.
3. The plugin exports the mask (frame extraction → generate → "export the frames")
   and stores a **mask video file inside a Kdenlive folder**. Options: preview /
   edit / **apply** / delete / **import** mask.
4. **Apply mask** inserts a **Shape Alpha** effect referencing that mask file →
   the clip now has an alpha cutout of the subject (used here to place text
   *behind* the presenter, with a duplicated clip restoring the background).
5. Bonus: the **Shape Alpha (Mask)** + **Mask Apply** "mask sandwich" restricts
   *other* effects to the subject (or its inverse), and an **Alpha operations**
   filter (shave / grow-soft / shrink-soft / blur / invert) refines the edge.

### What the app-side workflow produces in the project file (web-researched)

SAM2 runs as a **Kdenlive application plugin with its own Python venv, not an MLT
filter**, so it is *not* directly scriptable through our file-based integration
(confirmed by the release notes and the MCP improvements plan §5). Its persistent,
file-consumable output is:

- a **generated mask media file** (a video/image matte) written to a Kdenlive
  working folder — re-usable across projects via *Import mask*; and
- an inserted **Shape Alpha** effect. Verified against
  `/usr/share/kdenlive/effects/shape.xml` and `mask_start_shape.xml`, and via
  `melt -query filter=shape`, this is the MLT **`shape`** filter with:
  `resource` (the matte file), `mix` (threshold %), `softness`, `invert`,
  `use_luminance` (read the matte's luma instead of alpha), `use_mix` (apply the
  threshold at all), `in`/`out` (matte offset/end). The masked-effect form is
  `mask_start` / `kdenlive_id=mask_start-shape` (`filter=shape`, `filter.*`
  props) closed by `mask_apply`.

**So yes — our file-based tools can consume the SAM2 output**: point a `shape`
filter's `resource` at the exported mask file. That is exactly the `image_alpha`
mask type `server/tools.py::mask_set` rejects as "not yet implemented", and the
deferred "feed our own SAM/YOLO segmentation output in as luma-matte video" item
in the plan §5.

### Coverage verdict

| Capability | Tutorial | Our tools (before) | Verdict |
|---|---|---|---|
| AI subject segmentation (SAM2) | ✅ app plugin | ❌ not scriptable | Out of scope — app plugin, own venv. Propose our own YOLO/SAM per §5 |
| Parametric shape → alpha | (n/a here) | ✅ `object_mask` = `frei0r.alpha0ps_alphaspot` | Note: our `object_mask` is a *spot shape*, NOT SAM2 — naming is misleading |
| **Consume an external matte file as alpha** | ✅ Shape Alpha (`shape`, `resource=`) | ❌ `image_alpha` unimplemented | **GAP → built** `mask_set_from_file` |
| Mask sandwich (restrict effects to subject) | ✅ Shape Alpha (Mask)+Mask Apply | ✅ `apply_mask_to_effect` / `mask_apply` | Covered (see bug note) |
| Edge refine (shave/grow/blur/invert) | ✅ Alpha operations | ⚠️ partial (`invert`, feather on roto) | Propose an `alpha_operations` wrapper |

### Built (additive, no existing files touched)

- `edit_mcp/pipelines/shape_alpha.py` — pure builders `build_shape_alpha_xml`
  and `build_mask_start_shape_xml` (schema-anchored to the stock effect XML).
- `edit_mcp/server/bundles/shape_alpha_mask.py` — MCP tool **`mask_set_from_file`**
  (workspace, project, track, clip, `mask_file`, `mix`, `softness`, `invert`,
  `use_luminance`, `use_threshold`, `mask_in`, `mask_out`). Inserts a Shape Alpha
  at the top of the clip stack referencing the matte; snapshots first; returns
  `type="image_alpha"`, `mlt_service="shape"`. Auto-discovered by
  `server/bundles/__init__.py`.
- Tests: `tests/unit/test_shape_alpha.py` (9), `tests/integration/test_shape_alpha_mask_tool.py`
  (4) — all green. `melt -query filter=shape` confirms the MLT service exists with
  matching properties in this build.

### Proposed (NOT built)

- **`object_mask` naming/behavior**: our `object_mask` is a `frei0r.alpha0ps_alphaspot`
  spot, unrelated to SAM2. Consider renaming to `shape_spot_mask` (or documenting
  loudly) to avoid implying AI segmentation.
- **Latent bug in existing `masking.py`** (do not fix here — flagged for a spec):
  `_build_mask_start_from_existing` maps a `shape` service to
  `_OBJECT_MASK_INNER_PROPS = ("0".."7")`, but Shape Alpha uses *named* props
  (`resource`, `mix`, …). Wrapping a real `shape` filter with `apply_mask_to_effect`
  would drop all its properties. `build_mask_start_shape_xml` in the new module is
  the correct construction and can seed the fix.
- **Own segmentation** (`subject_locate_frames` → YOLO/SAM → mask video →
  `mask_set_from_file`) to fully automate the SAM2 use case headlessly (plan §5).
- **`alpha_operations` wrapper** for edge shave/grow-soft/shrink-soft/blur.

---

## 2. Picture in Picture — #14

**Video:** [2024 Kdenlive Tutorial - Picture in Picture Effect](https://www.youtube.com/watch?v=q8zp9tKkoPs)
(Victoriano de Jesus, 2024-01-23)

### What the tutorial teaches

PiP via the **Transform effect** (not a composite transition):

1. Two video tracks; background on V1, the inset clip on V2 (ungroup + delete the
   empty audio container).
2. Drag **Transform** onto the top clip. Resize/reposition with the on-monitor red
   handles, or via params: **X / Y** (position), **Width / Height** (with optional
   **lock aspect ratio**), **Size %**, **Opacity**, **Rotation** (degrees).
3. Keyframing is available (mentioned, not demonstrated) for animated PiP moves.

### Coverage verdict

| Capability | Tutorial (Transform) | `composite_pip` | Verdict |
|---|---|---|---|
| Inset a clip in a corner/center | ✅ | ✅ presets `top/bottom_left/right`, `center`, `custom` | Covered |
| Size the inset | ✅ width/height/size % | ✅ `scale` (uniform) | Covered (uniform only) |
| **Opacity / transparency** | ✅ | ❌ hardcoded `:100` in geometry | **Gap — propose param** |
| **Rotation** | ✅ degrees | ❌ | **Gap — propose param** |
| **Keyframed PiP movement** | ✅ (Transform keyframes) | ❌ static geometry only | **Gap — propose** |
| Non-uniform / aspect-unlock size | ✅ | ❌ single `scale` | Minor gap |
| Border / drop shadow on inset | (not in this video) | ❌ | Covered elsewhere: `effect_drop_shadow` bundle exists (shake-shadow) |

`composite_pip` reaches the same *result* through a different mechanism (a
`frei0r.cairoblend` composite transition with a `geometry` rect), so basic PiP is
**covered**. The tutorial's richer controls are the gaps.

### Proposed (NOT built — all require editing `pipelines/compositing.py` or `tools.py`)

- Add **`opacity`** (0–100) to `composite_pip`/`apply_pip` — the geometry string
  already ends in an opacity field (`x/y:wxh:OPACITY`); today it is fixed at `100`.
- Add **`rotation`** — needs a `transform`/`qtblend`-based path (cairoblend
  geometry has no rotation); or a distinct `composite_pip_transform` that emits a
  Transform (`qtblend`/`affine`) effect on the overlay clip instead of a transition.
- **Keyframed movement**: expose start/end rects (or reuse
  `effect_keyframe_set_rect` against a Transform-based PiP) for animated insets.
- Non-uniform sizing (separate width/height) and an aspect-lock flag.

None are additive-without-touching-existing-files, so none were built.

---

## 3. LUT grading (Kdenlive 2025) — #25

**Video:** [How to Apply LUTs for Color Grading in Kdenlive 2025?](https://www.youtube.com/watch?v=fh3qETbfx_8)
(EditingBasics, 2025-07-08, ~1 min)

### What the tutorial teaches

Minimal, exactly matches our tool: select clip → Effects → search **Apply LUT** →
drag on → in the Effect Stack click the **LUT file** dropdown to load a `.cube` →
grade appears instantly; repeat to try different LUTs. **New detail:** "You can
also change the **interpolation mode** to adjust how the LUT is applied."

### Coverage verdict

| Capability | Tutorial | `color_apply_lut` | Verdict |
|---|---|---|---|
| Apply a `.cube`/`.3dl` LUT to a clip | ✅ | ✅ `avfilter.lut3d`, sets `av.file` | Covered |
| Stack multiple LUTs | ✅ repeat | ✅ appends (call twice) | Covered |
| **Interpolation mode** (near/tri/tetra) | ✅ | ❌ not exposed | **Gap — propose param** |

Everything else the video shows is already documented in the existing guide
`Using LUTs in Kdenlive.md` (conversion vs creative, order, opacity for intensity,
`avfilter.lut3d` vs `frei0r.lut3d`). Only the interpolation delta is new.

### Proposed (NOT built — would edit `pipelines/color_tools.py`)

- Add an optional **`interp`** param to `color_apply_lut`/`apply_lut_to_project`
  setting `avfilter.lut3d`'s `av.interp` (`nearest` / `trilinear` / `tetrahedral`;
  tetrahedral = smoothest, default). Additive, but `apply_lut_to_project` is an
  existing file, so out of scope for building here.

Delta appended as a "2025 LUT workflow deltas" section to
`/home/caleb/Documents/Notes/Video Production/Research/Using LUTs in Kdenlive.md`.

---

## Files

- Guide notes:
  `…/Research/Kdenlive Tutorials/Object Mask (SAM2) - Kdenlive Tutorial.md`,
  `…/Research/Kdenlive Tutorials/Picture in Picture - Kdenlive Tutorial.md`
- LUT delta appended to `…/Research/Using LUTs in Kdenlive.md`
- Built: `edit_mcp/pipelines/shape_alpha.py`,
  `edit_mcp/server/bundles/shape_alpha_mask.py`,
  `tests/unit/test_shape_alpha.py`, `tests/integration/test_shape_alpha_mask_tool.py`
