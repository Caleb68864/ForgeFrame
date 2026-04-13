---
scenario_id: "OP-09"
title: "apply_preset mode_override=None uses preset.apply_hints.stack_order; 'replace' overrides"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-09: apply_preset mode override behavior

## Description
Verifies `[BEHAVIORAL]` -- when `mode_override=None`, apply uses `preset.apply_hints.stack_order`; when `mode_override="replace"`, it overrides the preset's hint.

## Preconditions
- A preset with `apply_hints.stack_order="prepend"` and 2 effects.
- A target clip with 1 pre-existing filter.

## Steps
1. Apply with `mode_override=None`. Assert returned `mode == "prepend"`. Verify via `patcher.list_effects` that target now has 3 filters with the 2 preset filters at the front.
2. Reset target. Apply with `mode_override="replace"`. Assert returned `mode == "replace"`. Verify via `list_effects` that target now has only the 2 preset filters (pre-existing cleared).
3. Reset target. Apply with `mode_override="append"`. Assert returned `mode == "append"`; pre-existing first, preset filters at the end.

## Expected Results
- mode_override controls placement; preset hint is the default.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_apply_mode_override -v`

## Pass / Fail Criteria
- **Pass:** All three branches behave correctly.
- **Fail:** Any branch wrong.
