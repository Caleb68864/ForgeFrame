---
scenario_id: "SR-14"
title: "apply_paste mode=prepend places incoming at top"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
---

# Scenario SR-14: apply_paste prepend mode

## Description
Verifies `[BEHAVIORAL]` -- pasting in `prepend` mode places incoming filters at the top of the target's stack while preserving target's pre-existing filters after them.

## Preconditions
- Source clip with [s0, s1], target with [t0, t1].

## Steps
1. `stack = serialize_stack(project, source_ref)`.
2. `apply_paste(project, target_ref, stack, mode="prepend")`.
3. `result = list_effects(target_ref)` -- assert length 4.
4. Assert order matches `[s0, s1, t0, t1]`.

## Expected Results
- Final order is `[s0, s1, t0, t1]`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_prepend -v`

## Pass / Fail Criteria
- **Pass:** Length 4 with prepend order correct.
- **Fail:** Wrong order or length.
