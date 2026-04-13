---
scenario_id: "SR-06"
title: "shape_to_points — polygon with <3 points raises ValueError"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-06: shape_to_points — polygon with <3 points raises ValueError

## Description
Verifies [BEHAVIORAL] polygon minimum arity: fewer than 3 points raises `ValueError` whose message names the minimum (3).

## Preconditions
- Module importable.

## Steps
1. Call `shape_to_points(MaskShape(kind="polygon", points=((0.1, 0.1), (0.5, 0.1))))`.
2. Assert `ValueError` is raised.
3. Assert the error message contains the numeral `3` or the word "minimum".
4. Repeat with `points=()` and `points=((0.1, 0.1),)`.

## Expected Results
- All three cases raise `ValueError`.
- Message references the minimum (3).

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_shape_to_points_polygon_min_points -v`

## Pass / Fail Criteria
- **Pass:** every sub-case raises `ValueError` with informative message.
- **Fail:** silently produces output, wrong exception, or uninformative message.
