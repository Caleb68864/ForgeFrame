---
scenario_id: "OP-08"
title: "validate_against_catalog(strict=True) raises ValueError naming bad service"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - behavioral
---

# Scenario OP-08: validate_against_catalog strict raise message

## Description
Verifies `[BEHAVIORAL]` -- with an unknown `mlt_service`, strict validation raises `ValueError` whose message names the offending service AND suggests checking `effect_list_common`.

## Preconditions
- Build preset containing `PresetEffect(mlt_service="nonexistent.fake_service", ..., xml="...")`.

## Steps
1. Call `validate_against_catalog(preset, strict=True)` inside `pytest.raises(ValueError) as exc`.
2. Assert `"nonexistent.fake_service"` is a substring of `str(exc.value)`.
3. Assert `"effect_list_common"` (case-insensitive) is a substring of `str(exc.value)`.

## Expected Results
- ValueError with offending service and tool hint in message.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_validate_strict_raises -v`

## Pass / Fail Criteria
- **Pass:** Raises with both substrings.
- **Fail:** Wrong exception, missing substring, or no raise.
