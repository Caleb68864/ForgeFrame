---
scenario_id: "SR-27"
title: "move_down happy path (index 0 → 1)"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
sequential: true
---

# Scenario SR-27: `move_down(effect_index=0)` → index 1

## Steps
1. Record service id at index 0 as `svc`.
2. Call `move_down(track=2, clip=0, effect_index=0)`.
3. Assert index 1 now holds `svc`.
4. Assert return `data.effect_index_after == 1`.

## Expected Results
- Filter shifted down by one.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_down_happy -v`

## Pass / Fail Criteria
- **Pass:** index 1 holds `svc`.
- **Fail:** wrong position.
