---
scenario_id: "SR-21"
title: "flash_cut_montage errors on n_cuts < 2"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - montage
  - error
sequential: false
---

# Scenario SR-21: Montage n_cuts=1 error

## Steps
1. Call `flash_cut_montage(..., n_cuts=1)`.
2. Assert return is `_err` shape.
3. Assert message indicates at least 2 cuts required.
4. Assert no splits and no filters added.

## Expected Results
- `_err` with no side effects.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_montage_n_cuts_too_low -v`

## Pass / Fail Criteria
- **Pass:** error, state unchanged.
- **Fail:** proceeds anyway.
