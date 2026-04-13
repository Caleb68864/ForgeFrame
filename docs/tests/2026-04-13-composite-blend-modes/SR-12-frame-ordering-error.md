---
scenario_id: "SR-12"
title: "end_frame <= start_frame raises ValueError"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] frame ordering / zero-length rejection"]
tags: [test-scenario, pipeline, behavioral, critical, error-path]
---

# Scenario SR-12: end_frame <= start_frame raises ValueError

## Description
Both zero-length (`start == end`) and inverted (`end < start`) frame ranges must raise `ValueError` (spec Requirement 10; Edge Case "zero-length composition").

## Preconditions
- Module implemented.

## Steps
1. Build a project.
2. Parametrize over `(start, end)` in `[(10, 10), (20, 10), (0, 0)]`.
3. For each, call `apply_composite(project, 1, 2, start, end, blend_mode="screen")` inside `pytest.raises(ValueError)`.

## Expected Results
- All three cases raise `ValueError`.

## Execution Tool
bash -- `uv run pytest tests/unit/test_compositing_blend_modes.py::test_apply_composite_frame_ordering -v`

## Pass / Fail Criteria
- **Pass:** Every parametrized case raises ValueError.
- **Fail:** Any case accepted.
