---
scenario_id: "SR-24"
title: "move_to_top happy path"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - reorder
sequential: true
---

# Scenario SR-24: `move_to_top(effect_index=3)` on 4-filter stack → index 0

## Preconditions
- Clip at track=2 clip=0 with a 4-filter stack at indices 0..3 with distinguishable services.

## Steps
1. Record the service id at index 3 as `svc`.
2. Call `move_to_top(track=2, clip=0, effect_index=3)`.
3. Re-parse project; list filters.
4. Assert filter at index 0 has service id `svc`.
5. Assert stack length still 4.
6. Assert return `data.effect_index_before == 3` and `data.effect_index_after == 0`.
7. Assert `data.snapshot_id` exists in snapshot list.

## Expected Results
- Filter moved to top, rest shifted down.

## Execution Tool
bash -- `uv run pytest tests/integration/test_reorder_wrappers.py::test_move_to_top_happy -v`

## Pass / Fail Criteria
- **Pass:** index 0 is `svc`, shape correct.
- **Fail:** wrong position or shape.
