---
scenario_id: "SR-03"
title: "remove_effect at start, middle, and end indices"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario SR-03: remove_effect at start, middle, end

## Description
Verifies `[BEHAVIORAL]` removal: removing index 0, middle, and last index each shrinks the target clip's stack by one with stable order on the remaining entries.

## Preconditions
- Clip with at least 3 filters in known order.

## Steps
1. Capture `list_effects((2,0))` baseline -- list of (kdenlive_id, mlt_service) tuples L of length N.
2. Reload fixture; `remove_effect(project, (2,0), 0)`; assert resulting list equals `L[1:]`.
3. Reload; `remove_effect(... 1)`; assert resulting list equals `L[:1] + L[2:]`.
4. Reload; `remove_effect(... N-1)`; assert resulting list equals `L[:-1]`.
5. Verify other clips' stacks unchanged after each removal.

## Expected Results
- Length always N-1.
- Remaining entries preserve relative order.
- No collateral mutation.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_remove_indices -v`

## Pass / Fail Criteria
- **Pass:** All three indices verified.
- **Fail:** Wrong filter removed, wrong length, side effects.
