---
scenario_id: "SR-04"
title: "reorder_effects moves filter; list_effects verifies order"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario SR-04: reorder_effects within a stack

## Description
Verifies `[BEHAVIORAL]` reorder: moving the third filter to position 0 (`reorder_effects(project, (2,0), 2, 0)`) puts it on top; bidirectional moves (top->middle, middle->bottom) verified via `list_effects`.

## Preconditions
- Clip with at least 3 filters in known order L = [f0, f1, f2].

## Steps
1. `reorder_effects(project, (2,0), 2, 0)`; assert `list_effects` order = [f2, f0, f1].
2. Reload; `reorder_effects(... 0, 2)`; assert order = [f1, f2, f0].
3. Reload; `reorder_effects(... 1, 2)`; assert order = [f0, f2, f1].
4. Confirm all moves leave unrelated clips untouched.

## Expected Results
- Each reorder moves exactly the named filter to the new index, shifting others.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_reorder_within_stack -v`

## Pass / Fail Criteria
- **Pass:** Listed orders match expected for all three cases.
- **Fail:** Wrong filter moved or order corrupted.
