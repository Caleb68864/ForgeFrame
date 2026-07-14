---
sub_spec_id: SS-07
phase: run
depends_on: ['SS-01']
dispatch: factory
wave: 2
---

# SS-07 — Local frame quality scoring

## Context
`FrameScorer` computes independently-inspectable metrics on `FrameVisualMetrics`. FFmpeg-cheap
metrics (brightness/black/overexposure) always; pixel metrics (sharpness=variance-of-Laplacian,
entropy, text-density) via numpy+Pillow **lazily/guarded** — absent → fields `None`, debug log,
no raise. Weights + per-mode profiles (`software_ui`, `slide_deck`, `physical_demo`) drive a
derived `rank`, never collapsed into one stored number.

## Implementation Steps (TDD)
1. **Failing test** `tests/unit/test_frame_scoring.py`: a near-black PIL image scores low brightness
   and is rejected by the quality gate; a sharp image out-scores its Gaussian-blurred copy on
   sharpness; when numpy/Pillow are simulated-absent (monkeypatch import), `score` returns metrics
   with pixel fields `None` and does not raise.
2. **Run to fail:** `uv run pytest tests/unit/test_frame_scoring.py -q`.
3. **Implement** `pipelines/visual_research/scoring.py`: `class FrameScorer` with
   `score(candidate, config) -> FrameVisualMetrics` and `rank(candidates, config)`; guarded
   `import numpy`, `import PIL` inside functions.
4. **Run to pass.**
5. **Commit:** `factory(SS-07): local frame quality scoring [factory-managed]`

## Interface Contracts
- **Owner** of `FrameScorer.score`/`rank`. Consumed by SS-08 (rank_key), SS-10.
- **Requires:** `FrameCandidate`, `FrameVisualMetrics`, `ResearchConfig` (SS-01).

## Verification Commands
- `uv run pytest tests/unit/test_frame_scoring.py -q`

## Checks
| Criterion | Type | Command |
|-----------|------|---------|
| scoring.py defines FrameScorer | [STRUCTURAL] | `grep -q "class FrameScorer" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/scoring.py \|\| (echo "FAIL: FrameScorer missing" && exit 1)` |
| numpy/Pillow imports are guarded (not top-level) | [STRUCTURAL] | `! grep -Eq "^(import numpy\|import PIL\|from PIL)" workshop-video-brain/src/workshop_video_brain/edit_mcp/pipelines/visual_research/scoring.py \|\| (echo "FAIL: unguarded image-lib import" && exit 1)` |
| unit tests pass | [MECHANICAL] | `uv run pytest tests/unit/test_frame_scoring.py -q 2>&1 \| tail -1; [ ${PIPESTATUS[0]} -eq 0 ] \|\| (echo "FAIL: scoring tests" && exit 1)` |
