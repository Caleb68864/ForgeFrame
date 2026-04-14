---
scenario_id: "SR-26"
title: "move_up happy path (index 2 → 1)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
sequential: true
---

# Scenario SR-26: `move_up(effect_index=2)` → index 1

## Steps
1. Record service id at index 2 as `svc`.
2. Call `move_up(track=2, clip=0, effect_index=2)`.
3. Assert index 1 now holds `svc`.
4. Assert return `data.effect_index_after == 1`, `effect_index_before == 2`.

## Expected Results
- Filter shifted up by one.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_up_happy -v`

## Pass / Fail Criteria
- **Pass:** index 1 holds `svc`.
- **Fail:** wrong position.
