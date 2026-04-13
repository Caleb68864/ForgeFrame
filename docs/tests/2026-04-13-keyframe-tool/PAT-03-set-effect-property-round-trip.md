---
scenario_id: "PAT-03"
title: "set_effect_property mutates tree; round-trips via get"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
---

# Scenario PAT-03: set_effect_property mutates tree; get round-trips

## Description
Verifies [BEHAVIORAL] Sub-Spec 1 -- setting a property mutates the in-memory project tree and a subsequent `get_effect_property` returns the new value.

## Preconditions
- Fixture project parsed into memory.
- Transform filter present at clip `(2, 0)`, effect_index `0`.

## Steps
1. Call `patcher.set_effect_property((2, 0), 0, "rect", "00:00:00.000=0 0 1920 1080 1")`.
2. Call `patcher.get_effect_property((2, 0), 0, "rect")` and assert the return equals the value just set.
3. Inspect the underlying XML element directly to confirm the `<property name="rect">` text matches.
4. Assert no other properties on the same filter have changed.

## Expected Results
- Written value round-trips exactly through get.
- XML element text matches.
- Other filter properties unchanged.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_effect_properties.py::test_set_rect_round_trip -v`

## Pass / Fail Criteria
- **Pass:** Round-trip identical and sibling properties untouched.
- **Fail:** Value mismatch, XML not updated, or side effects on other properties.
