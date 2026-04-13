---
scenario_id: "SR-09"
title: "Unknown blend_mode raises ValueError listing valid modes"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] unknown mode error"]
tags: [test-scenario, pipeline, behavioral, critical, error-path]
---

# Scenario SR-09: Unknown blend_mode raises ValueError listing valid modes

## Description
Unknown `blend_mode` values must raise `ValueError`, and the error message must name the offending mode AND list all 11 valid modes (per spec Requirement 8 and Sub-Spec 1 BEHAVIORAL criterion).

## Preconditions
- Module implemented.

## Steps
1. Build a project.
2. Call `apply_composite(..., blend_mode="not_a_mode")` inside `pytest.raises(ValueError)`.
3. Capture `str(exc.value)`.
4. Assert `"not_a_mode"` appears in the message.
5. Assert every member of `BLEND_MODES` appears in the message.

## Expected Results
- `ValueError` raised.
- Message contains the offending value and all 11 valid modes.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_unknown_mode -v`

## Pass / Fail Criteria
- **Pass:** ValueError raised with compliant message.
- **Fail:** No exception, wrong exception type, or missing identifiers in message.
