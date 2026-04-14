---
scenario_id: "SR-25"
title: "move_to_bottom happy path"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
sequential: true
---

# Scenario SR-25: `move_to_bottom(effect_index=0)` on 4-filter stack → index 3

## Steps
1. Record service id at index 0 as `svc`.
2. Call `move_to_bottom(track=2, clip=0, effect_index=0)`.
3. Re-parse, list filters.
4. Assert filter at last index (3) has service id `svc`.
5. Assert return `data.effect_index_before == 0`, `data.effect_index_after == 3`.

## Expected Results
- Filter moved to bottom.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_to_bottom_happy -v`

## Pass / Fail Criteria
- **Pass:** last index is `svc`.
- **Fail:** wrong position.
