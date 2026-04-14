---
scenario_id: "SR-22"
title: "flash_cut_montage errors when n_cuts exceeds clip duration"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - montage
  - error
sequential: false
---

# Scenario SR-22: Montage n_cuts > duration error

## Steps
1. Given clip of 3 frames, call `flash_cut_montage(..., n_cuts=10)`.
2. Assert return is `_err`.
3. Assert message contains clip duration hint (e.g., "clip is 3 frames").
4. Assert no splits performed.

## Expected Results
- `_err` with duration mentioned.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_montage_over_duration -v`

## Pass / Fail Criteria
- **Pass:** error mentions duration.
- **Fail:** crashes or proceeds.
