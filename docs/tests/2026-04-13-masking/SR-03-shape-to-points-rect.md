---
scenario_id: "SR-03"
title: "shape_to_points — rect returns 4 clockwise corners"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-03: shape_to_points — rect returns 4 clockwise corners

## Description
Verifies [BEHAVIORAL] rect conversion: `MaskShape(kind="rect", bounds=(0.1, 0.1, 0.5, 0.5))` yields exactly 4 points in clockwise order.

## Preconditions
- Module importable.

## Steps
1. Call `shape_to_points(MaskShape(kind="rect", bounds=(0.1, 0.1, 0.5, 0.5)))`.
2. Inspect returned list/tuple.

## Expected Results
- Exactly 4 points returned.
- Points correspond to rectangle corners starting at top-left and proceeding clockwise: `(0.1, 0.1)`, `(0.6, 0.1)`, `(0.6, 0.6)`, `(0.1, 0.6)` (bounds interpreted as `(x, y, w, h)`).
- Float comparison within 1e-9 tolerance.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_shape_to_points_rect -v`

## Pass / Fail Criteria
- **Pass:** 4 CW corners returned as specified.
- **Fail:** wrong count, wrong order, or wrong coordinates.
