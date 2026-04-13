---
scenario_id: "PAT-05"
title: "get/set raise clear errors on missing clip/effect/property"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - patcher
  - behavioral
  - edge-case
---

# Scenario PAT-05: get/set raise clear errors on missing clip/effect/property

## Description
Verifies [BEHAVIORAL] Sub-Spec 1 error contract -- non-existent property returns `None`; non-existent effect_index or clip raises `IndexError` (or equivalent) with an actionable message.

## Preconditions
- Fixture project parsed; a valid clip at `(2, 0)` with one filter.

## Steps
1. Call `get_effect_property((2, 0), 0, "does_not_exist")` -- assert returns `None`.
2. Call `get_effect_property((2, 0), 99, "rect")` -- assert `IndexError` raised; assert message mentions available effect indices or effect count.
3. Call `get_effect_property((99, 99), 0, "rect")` -- assert `IndexError`/`LookupError`; assert message identifies the missing clip reference.
4. Repeat equivalents for `set_effect_property`.

## Expected Results
- Missing property -> `None`.
- Missing effect_index -> raises with list/count of effects on that clip.
- Missing clip -> raises naming the clip_ref.

## Execution Tool
bash -- `uv run pytest tests/unit/test_patcher_effect_properties.py::test_error_contract -v`

## Pass / Fail Criteria
- **Pass:** Returns/raises per contract; messages are actionable.
- **Fail:** Silent failure, wrong exception type, or bare message without context.
