---
scenario_id: "OP-10"
title: "apply_preset writes correct number of filters (verified via list_effects)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-10: apply_preset filter count

## Description
Verifies `[BEHAVIORAL]` -- post-apply, the target clip's filter count equals the documented arithmetic for each mode.

## Preconditions
- Preset with N=3 effects.
- Target clip with M=2 existing filters.

## Steps
1. Append: post-count == M+N (5). Returned `effects_applied == 3`.
2. Prepend: post-count == M+N (5). Returned `effects_applied == 3`.
3. Replace: post-count == N (3). Returned `effects_applied == 3`.
4. Each verified via `len(patcher.list_effects(project, target_ref)) == expected`.

## Expected Results
- Counts match per mode.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_apply_filter_counts -v`

## Pass / Fail Criteria
- **Pass:** All counts match.
- **Fail:** Otherwise.
