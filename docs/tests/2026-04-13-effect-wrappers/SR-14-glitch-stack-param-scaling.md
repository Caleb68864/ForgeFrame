---
scenario_id: "SR-14"
title: "effect_glitch_stack scales params with intensity"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - glitch
sequential: true
---

# Scenario SR-14: Glitch stack intensity param scaling (0.0 vs 1.0)

## Preconditions
- Two separate workspace projects or sequential runs with snapshot restore.

## Steps
1. Run `effect_glitch_stack(..., intensity=0.0)` on a fresh clip; capture filter property values (e.g., pixeliz0r `block_size`, glitch0r shift, rgbsplit0r amount).
2. Restore / start fresh. Run `effect_glitch_stack(..., intensity=1.0)`.
3. Capture the same property values.
4. Assert at least `pixeliz0r` block size differs between the two runs.
5. Assert scaling is monotonic -- the `intensity=1.0` params are consistently higher (or lower) than `intensity=0.0` where spec dictates direction.
6. Call `glitch_stack_params(0.5)` directly and assert returned dict has keys for all 5 filters.

## Expected Results
- Different intensity produces different concrete filter params.
- Helper `glitch_stack_params` returns spec-shaped dict.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_glitch_stack_param_scaling -v`

## Pass / Fail Criteria
- **Pass:** params differ and helper shape correct.
- **Fail:** identical params across intensities.
