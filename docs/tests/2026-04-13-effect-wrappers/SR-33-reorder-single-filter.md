---
scenario_id: "SR-33"
title: "Reorder on single-filter stack — all four are no-ops"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
  - no-op
sequential: false
---

# Scenario SR-33: Single-filter stack all reorder tools no-op

## Steps
1. Build a fixture with exactly 1 filter at index 0 on target clip.
2. For each of `move_to_top`, `move_to_bottom`, `move_up`, `move_down` with `effect_index=0`:
   a. Call tool.
   b. Assert `_ok` with clarifying note.
   c. Assert filter order unchanged.

## Expected Results
- All four no-op with notes.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_single_filter_all_noop -v`

## Pass / Fail Criteria
- **Pass:** all four report no-op.
- **Fail:** crash or unintended mutation.
