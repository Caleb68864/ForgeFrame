---
title: Local AI Mask Generation
date: 2026-07-03
type: reference
tags: [kdenlive, masking, segmentation, sam2, rembg, yolo, ai, matte, forgeframe]
---

# Local AI Mask Generation

How to produce a **black/white matte video** locally on a workstation so our
file-based Kdenlive tools can consume it as a clip's alpha. This is the
**producing** half of the SAM2 story; the **consuming** half already ships as
`mask_set_from_file` (`edit_mcp/pipelines/shape_alpha.py` +
`edit_mcp/server/bundles/shape_alpha_mask.py`), which applies any matte video
via the MLT `shape` filter.

Context: Kdenlive 25.04's built-in **Object Mask** runs SAM2 as an *application*
plugin with its own Python venv — not scriptable, and it leaves behind a mask
video + a Shape Alpha effect. We want the same *output* (a matte video)
generated **headlessly** by our own pipeline so an agent can mask a subject
without the GUI. See `docs/plans/2026-07-03-kdenlive-mcp-improvements.md` §5 and
`docs/research/2026-07-03-tutorial-effect-analysis/validation-existing-tools.md`
§1.

## The question

Given a source clip and a subject ("person", "the guitar", a box, a point),
generate a matte video (white = keep, black = drop) matching the source's
fps/resolution/duration, using only **locally installed** models. Which
segmentation route is the right *default*, and what is the upgrade path?

## Routes compared

| Route | pip install | Footprint | Torch? | CPU? | Temporal | Targeting | Quality |
|---|---|---|---|---|---|---|---|
| **rembg** (u2net / isnet / birefnet) | `pip install rembg` | ~20–50 MB runtime (onnxruntime CPU ~18 MB) + model 4–176 MB | **No** (onnxruntime) | **Yes, great** | Per-frame (no propagation) | Salient object; `u2net_human_seg` biases to people | Low→High by model |
| **YOLOv8/11-seg** | `pip install ultralytics` | torch stack ~1.5–3 GB + model 6–119 MB | **Yes** | Yes, ~50–800 ms/frame | Per-frame (tracker keeps IDs, not the mask) | **Class-prompted** (COCO: `person`=0) | Medium (coarser) |
| **SAM2** (facebook/sam2 or ultralytics) | `pip install ultralytics` / git | torch stack ~1.5–3 GB + checkpoint ~150–900 MB | **Yes** | Runs but ~tens of s/frame; wants GPU | **Best — true propagation** (memory bank) | Click / box / point on one frame → propagates | **Highest** |
| **ffmpeg chroma/luma key** | (installed) | zero | No | Trivial | Per-frame, deterministic | Color/luma threshold only | Baseline (non-AI) |

### rembg — the lightweight CPU default
onnxruntime only, **no PyTorch** (~50× smaller install than a torch stack).
Models auto-download to `~/.u2net/`: `u2netp` ~4 MB (tiny/preview), `u2net`
~176 MB (general), `isnet-general-use` ~43 MB (better edges),
`birefnet-general-lite` ~12 MB and `birefnet-general` ~43 MB (highest rembg
tier). It does **salient-object / background removal** — it segments *the*
prominent foreground automatically, with **no click/box targeting** (use
`u2net_human_seg` to bias toward people). Strictly **per-frame**: no temporal
awareness. `onnxruntime-gpu` exists if you want acceleration. `remove(...,
only_mask=True)` returns exactly the grayscale matte we need.

### YOLOv8/11-seg — class-prompted middle tier
Request a *category* ("person" = COCO class 0) rather than "whatever is
salient." Small, fast models (YOLO11n-seg 6 MB up to x-seg 119 MB), CPU-usable,
but pulls the **same multi-GB torch stack as SAM2**. Mask edges are coarser
(derived from detection prototypes). Per-frame; its tracker preserves object IDs
across frames but recomputes the mask each frame.

### SAM2 — the quality + temporal ceiling
The only route with a genuine **video predictor**: prompt an object once (click,
box, or mask on a single frame) and its memory-attention mechanism re-segments
it across every frame — temporally coherent mattes with no downstream smoothing.
Hard-depends on PyTorch (multi-GB), and on CPU it is impractically slow (tens of
seconds per frame on tiny); it effectively wants CUDA. Checkpoints tiny (38.9M
params) → large (224.4M).

### ffmpeg chroma/luma — the non-AI fallback
Already covered by existing ForgeFrame tools (`effect_chroma_key`,
`effect_chroma_key_advanced`, frei0r). Instant and flicker-free, but understands
only color/luminance thresholds — needs a green screen or high-contrast subject
and cannot isolate "the person" from a busy natural background. Out of scope for
this note; listed for completeness.

## Temporal flicker — the per-frame caveat

rembg and YOLO-seg process each frame **independently**, so mattes can shimmer at
edges (hair, motion blur, thin structures) frame-to-frame even for a static
subject. Mitigations downstream: temporal smoothing (blend alpha across N
adjacent frames), morphological open/close to stabilize edges, optical-flow mask
warping — or simply accept per-frame jitter for rough mattes. SAM2 sidesteps
this via propagation, which is its core advantage for video.

## Recommendation

**Default: rembg.** It is the lightest viable engine that runs on CPU with **no
torch** (onnxruntime-only, ~20 MB runtime). Ship `u2netp` (~4 MB) as the
zero-friction default with `isnet-general-use` / `birefnet-general` as
better-edge upgrades, all CPU-friendly and auto-downloaded on first use.

**Upgrade path: SAM2** for best quality *and* temporal consistency (single-prompt
propagation), gated behind a documented "heavy/GPU" tier because it drags in the
multi-GB torch stack and wants a GPU — not installed by default. **YOLO-seg**
sits between them as the *class-prompted* option ("just the person") when you
want a named subject rather than "the salient object" (rembg) or an interactive
click (SAM2); it also needs torch, so it lives in the same optional heavy tier.

Tiering: **rembg (default) → YOLO-seg (class-targeted, optional torch) → SAM2
(best/temporal, GPU-recommended)**, with ffmpeg keying as the always-available
non-AI fallback.

## What we build on top (ForgeFrame)

- Optional dependency group `ai-mask = ["rembg", "onnxruntime", "pillow",
  "numpy"]` in `workshop-video-brain/pyproject.toml` (torch/SAM2 documented as a
  second, uninstalled tier).
- `edit_mcp/pipelines/ai_mask.py` — pure planning/param logic + an ffmpeg-based
  engine adapter: extract frames → run the segmenter per frame → encode a
  black/white matte video matching source fps/resolution/duration into
  `media/derived_masks/` (never touches `media/raw`). Missing engine → a clear
  `pip install …` error, never a crash.
- `edit_mcp/server/bundles/ai_mask.py` — `mask_generate(...)` (matte path +
  metadata) and `mask_generate_and_apply(...)` which chains straight into the
  existing `shape_alpha` pipeline (reuse, don't duplicate).

## Sources

- SAM 2 — Ultralytics Docs (docs.ultralytics.com/models/sam-2/)
- rembg — PyPI / github.com/danielgatis/rembg; models: DeepWiki rembg 5.1
- Instance Segmentation / YOLO11 — Ultralytics Docs
- ONNX Runtime install docs; onnxruntime & torch on PyPI
