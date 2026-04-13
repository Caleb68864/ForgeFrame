---
scenario_id: "SR-05"
title: "Out-of-range indices raise IndexError naming stack length"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
  - error-path
---

# Scenario SR-05: Out-of-range index errors

## Description
Verifies `[BEHAVIORAL]` error path -- invalid `effect_index` in `remove_effect`, invalid `position` in `insert_effect_xml`, or invalid `from_index`/`to_index` in `reorder_effects` raise `IndexError` whose message names the current stack length.

## Preconditions
- Clip (2,0) with N filters.

## Steps
1. `pytest.raises(IndexError, match=str(N))` on `remove_effect(project, (2,0), N)`.
2. Same with `remove_effect(... -1)` (if negative not supported by spec).
3. `insert_effect_xml(... position=N+1)` raises `IndexError` mentioning N.
4. `reorder_effects(... from_index=N)` raises with stack length in message.
5. `reorder_effects(... to_index=N+5)` raises with stack length in message.
6. Assert message string contains the integer length value.

## Expected Results
- Each out-of-range call raises `IndexError` whose `str()` includes the current stack length.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_stack_ops.py::test_out_of_range -v`

## Pass / Fail Criteria
- **Pass:** All raise `IndexError` with length in message.
- **Fail:** Wrong exception type, no exception, or message lacks length.
