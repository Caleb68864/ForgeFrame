---
scenario_id: "SR-18"
title: "effect_fade errors when both fade_in and fade_out are zero"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - presets
  - fade
  - error
sequential: false
---

# Scenario SR-18: Fade both-zero error

## Steps
1. Call `effect_fade(..., fade_in_frames=0, fade_out_frames=0)`.
2. Assert return is `_err` shape.
3. Assert message indicates at least one fade must be non-zero.
4. Assert no filter inserted, no snapshot taken.

## Expected Results
- `_err` returned without side effects.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_presets.py::test_fade_both_zero_err -v`

## Pass / Fail Criteria
- **Pass:** error, no state change.
- **Fail:** silently inserts filter.
