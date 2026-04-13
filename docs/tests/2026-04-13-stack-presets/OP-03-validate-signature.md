---
scenario_id: "OP-03"
title: "validate_against_catalog signature: list return + strict raise"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - ops
  - structural
---

# Scenario OP-03: validate_against_catalog signature

## Description
Verifies `[STRUCTURAL]` -- `validate_against_catalog(preset, strict=True)` returns `list[str]` of warnings/errors when strict=False; raises `ValueError` when strict=True and any unknown service is present.

## Preconditions
- Module importable; `effect_catalog` available.

## Steps
1. Inspect signature; assert `strict` default is `True`.
2. Build preset with one known and one unknown `mlt_service`.
3. Call `validate_against_catalog(p, strict=False)` -- assert returns a `list` containing at least one string mentioning the unknown service.
4. Call `validate_against_catalog(p, strict=True)` -- assert raises `ValueError`.

## Expected Results
- Behavior split per `strict` flag as documented.

## Execution Tool
bash -- `uv run pytest tests/unit/test_stack_presets_ops.py::test_validate_signature -v`

## Pass / Fail Criteria
- **Pass:** Both modes behave correctly.
- **Fail:** Otherwise.
