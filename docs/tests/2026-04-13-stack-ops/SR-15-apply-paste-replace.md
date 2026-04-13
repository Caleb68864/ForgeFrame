---
scenario_id: "SR-15"
title: "apply_paste mode=replace clears target then inserts incoming"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
---

# Scenario SR-15: apply_paste replace mode

## Description
Verifies `[BEHAVIORAL]` -- `replace` mode clears target's pre-existing filters first; final stack equals incoming filters in source order.

## Preconditions
- Source clip with 2 filters [s0, s1], target with 3 filters [t0, t1, t2].

## Steps
1. `stack = serialize_stack(project, source_ref)`.
2. `apply_paste(project, target_ref, stack, mode="replace")`.
3. `result = list_effects(target_ref)` -- assert length 2.
4. Assert order matches `[s0, s1]`.
5. Assert no trace of `[t0, t1, t2]` remains in `project.opaque_elements` for target_ref.

## Expected Results
- Target stack equals exactly `[s0, s1]`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_replace -v`

## Pass / Fail Criteria
- **Pass:** Target stack replaced cleanly.
- **Fail:** Old filters retained or wrong contents.
