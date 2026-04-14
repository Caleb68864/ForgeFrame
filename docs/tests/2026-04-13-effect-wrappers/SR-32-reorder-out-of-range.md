---
scenario_id: "SR-32"
title: "Reorder out-of-range effect_index returns _err with stack length"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - error
sequential: false
---

# Scenario SR-32: Out-of-range `effect_index` error

## Steps
1. Given 4-filter stack, for each reorder tool (`move_to_top`, `move_to_bottom`, `move_up`, `move_down`):
   a. Call with `effect_index=99`.
   b. Assert return is `_err`.
   c. Assert error message contains the current stack length (e.g., "stack has 4 effects").
2. Repeat with `effect_index=-1` — also `_err`.
3. Assert project bytes unchanged after each failing call.

## Expected Results
- `_err` with informative message, no state change, for all four tools.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_out_of_range -v`

## Pass / Fail Criteria
- **Pass:** all four tools error with stack length mentioned.
- **Fail:** crash, silent no-op, or wrong message.
