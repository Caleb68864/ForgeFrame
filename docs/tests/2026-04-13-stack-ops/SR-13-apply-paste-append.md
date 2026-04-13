---
scenario_id: "SR-13"
title: "apply_paste mode=append preserves order, appends to end"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - pipeline
  - behavioral
---

# Scenario SR-13: apply_paste append mode

## Description
Verifies `[BEHAVIORAL]` -- pasting a 2-filter stack onto a 2-filter target clip in `append` mode yields a 4-filter clip with target's pre-existing filters first (order preserved) and incoming filters appended in source order.

## Preconditions
- Source clip with 2 filters [s0, s1].
- Target clip with 2 filters [t0, t1].

## Steps
1. `stack = serialize_stack(project, source_ref)`.
2. `apply_paste(project, target_ref, stack, mode="append")`.
3. `result = list_effects(target_ref)` -- assert length 4.
4. Assert order matches `[t0, t1, s0, s1]` by `kdenlive_id`/`mlt_service`.

## Expected Results
- Target stack length 4, ordering exactly `[t0, t1, s0, s1]`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_ops_pipeline.py::test_paste_append -v`

## Pass / Fail Criteria
- **Pass:** Length and order correct.
- **Fail:** Wrong length, missing/duplicate filters, wrong order.
