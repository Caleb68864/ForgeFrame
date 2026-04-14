---
scenario_id: "SR-30"
title: "move_to_top at index 0 is no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - no-op
sequential: false
---

# Scenario SR-30: `move_to_top(effect_index=0)` no-op

## Steps
1. Call `move_to_top(track=2, clip=0, effect_index=0)`.
2. Assert `_ok` returned.
3. Assert before == after == 0.
4. Assert project bytes unchanged (or at minimum filter order unchanged).

## Expected Results
- Idempotent no-op.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_to_top_at_top_noop -v`

## Pass / Fail Criteria
- **Pass:** no reorder.
- **Fail:** filter order changed.
