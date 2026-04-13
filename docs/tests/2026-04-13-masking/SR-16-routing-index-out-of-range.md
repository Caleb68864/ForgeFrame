---
scenario_id: "SR-16"
title: "Out-of-range index raises IndexError naming stack length"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-2
---

# Scenario SR-16: Out-of-range index raises IndexError naming stack length

## Description
Verifies [BEHAVIORAL] that out-of-range `mask_effect_index` or `target_effect_index` raises `IndexError` whose message names the current stack length.

## Preconditions
- Fixture clip with exactly 2 filters on the stack.

## Steps
1. Call `apply_mask_to_effect(..., mask_effect_index=5, target_effect_index=0)` → assert `IndexError`.
2. Call `apply_mask_to_effect(..., mask_effect_index=0, target_effect_index=99)` → assert `IndexError`.
3. Call `apply_mask_to_effect(..., mask_effect_index=-1, target_effect_index=0)` → assert `IndexError`.
4. Assert the error message contains the string `2` (stack length) in each case.

## Expected Results
- All three cases raise `IndexError`.
- Message includes the stack length.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_alpha_routing.py::test_out_of_range_index -v`

## Pass / Fail Criteria
- **Pass:** all three raise with informative message.
- **Fail:** wrong exception or missing stack-length info.
