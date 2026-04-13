---
scenario_id: "SR-10"
title: "Case-sensitive rejection (Screen, SCREEN)"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] case sensitivity edge case"]
tags: [test-scenario, pipeline, behavioral, edge-case]
---

# Scenario SR-10: Case-sensitive rejection

## Description
Spec Edge Case: only lowercase abstract names are accepted. `"Screen"` and `"SCREEN"` must raise `ValueError`, ideally with a hint to use lowercase.

## Preconditions
- Module implemented.

## Steps
1. For input in `["Screen", "SCREEN", "DestinationIn", "Source_Over"]`:
   - Call `apply_composite(..., blend_mode=input)` inside `pytest.raises(ValueError)`.
2. Assert the error message for `"Screen"` mentions the input value.
3. Optional (preference): assert message contains `"lowercase"` or suggests `"screen"`.

## Expected Results
- All uppercase / mixed-case inputs rejected.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_case_sensitive -v`

## Pass / Fail Criteria
- **Pass:** All four inputs raise ValueError.
- **Fail:** Any input silently accepted or normalized.
