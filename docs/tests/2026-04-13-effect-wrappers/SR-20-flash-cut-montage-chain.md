---
scenario_id: "SR-20"
title: "flash_cut_montage splits clip and applies effect chain"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - montage
sequential: true
---

# Scenario SR-20: `flash_cut_montage` split + effect chain

## Preconditions
- Workspace clip with duration >> n_cuts frames (e.g., 240 frames).

## Steps
1. Call `flash_cut_montage(track=2, clip=0, n_cuts=4, blur_amount=30, invert_alt=True)`.
2. Re-parse project.
3. Assert the single clip became 4 sequential sub-clips via `clip_split` (check producer IDs + in/out frames).
4. Assert each sub-clip has `frei0r.directional_blur` with amount=30.
5. Assert alternating sub-clips (indices 1, 3) additionally carry `avfilter.negate`.
6. Assert return: `split_clip_indices: list[int]` (length 4), `filter_count: int` (>= 4 blurs + 2 negates = 6), `snapshot_id: str`.
7. Call `montage_split_offsets(4, 240)` — returns 3 split offsets (to produce 4 pieces), evenly spaced.

## Expected Results
- 4 sub-clips, blur on each, negate on alternating.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_flash_cut_montage -v`

## Pass / Fail Criteria
- **Pass:** splits and filter chain correct.
- **Fail:** wrong split count or missing effects.
