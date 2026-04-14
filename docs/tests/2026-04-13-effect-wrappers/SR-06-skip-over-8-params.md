---
scenario_id: "SR-06"
title: "Effects with more than 8 params are skipped"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - generator
  - heuristic
sequential: false
---

# Scenario SR-06: Effects with >8 params are skipped

## Steps
1. Build a synthetic `EffectDef` with 9 params (or pick real one from catalog).
2. Pass to `select_wrappable_effects` within a minimal mock catalog.
3. Assert the 9-param effect is excluded.
4. Assert an otherwise-identical 8-param variant is included.

## Expected Results
- 9-param excluded; 8-param included.

## Execution Tool
bash -- `uv run pytest tests/unit/test_effect_wrapper_gen.py::test_skip_over_8_params -v`

## Pass / Fail Criteria
- **Pass:** filter boundary at 8 exact.
- **Fail:** wrong cutoff.
