---
scenario_id: "SR-28"
title: "move_up at index 0 is no-op"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - no-op
sequential: false
---

# Scenario SR-28: `move_up(effect_index=0)` no-op with note

## Steps
1. Call `move_up(track=2, clip=0, effect_index=0)`.
2. Assert return is `_ok` shape.
3. Assert `data.effect_index_before == 0 == data.effect_index_after`.
4. Assert response contains a `note` (or similar) equal to "already at top".
5. Assert snapshot was still created OR no snapshot created (document which per implementation — spec says "Each write call returns a snapshot_id"; if no-op is not a write, document in result).
6. Assert project bytes unchanged.

## Expected Results
- No-op, state preserved, clarifying note.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_up_at_top_noop -v`

## Pass / Fail Criteria
- **Pass:** note present, indices equal, project unchanged.
- **Fail:** reorder happened or wrong note.
