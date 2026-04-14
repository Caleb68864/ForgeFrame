---
scenario_id: "SR-29"
title: "move_down at last index is no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - no-op
sequential: false
---

# Scenario SR-29: `move_down` at last index no-op with note

## Steps
1. Given 4-filter stack, call `move_down(track=2, clip=0, effect_index=3)`.
2. Assert `_ok` with note "already at bottom".
3. Assert indices equal before == after.
4. Assert project bytes unchanged.

## Expected Results
- No-op, note present.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_down_at_bottom_noop -v`

## Pass / Fail Criteria
- **Pass:** note "already at bottom".
- **Fail:** reorder happened.
