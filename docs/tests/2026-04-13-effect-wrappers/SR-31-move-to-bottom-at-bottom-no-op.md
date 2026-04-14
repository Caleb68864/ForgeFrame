---
scenario_id: "SR-31"
title: "move_to_bottom at last index is no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - no-op
sequential: false
---

# Scenario SR-31: `move_to_bottom` at last index no-op

## Steps
1. Given 4-filter stack, call `move_to_bottom(track=2, clip=0, effect_index=3)`.
2. Assert `_ok`, before == after == 3.
3. Assert filter order unchanged.

## Expected Results
- Idempotent no-op.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_to_bottom_at_bottom_noop -v`

## Pass / Fail Criteria
- **Pass:** no reorder.
- **Fail:** filter order changed.
