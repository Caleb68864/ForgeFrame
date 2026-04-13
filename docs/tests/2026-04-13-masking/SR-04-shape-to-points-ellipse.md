---
scenario_id: "SR-04"
title: "shape_to_points — ellipse returns sample_count points starting at 3 o'clock"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-04: shape_to_points — ellipse returns sample_count points starting at 3 o'clock

## Description
Verifies [BEHAVIORAL] ellipse sampling: 32 points on the perimeter of `bounds=(0,0,1,1)`; first point at `(1, 0.5)` in ellipse-local space (3 o'clock, angle 0).

## Preconditions
- Module importable.

## Steps
1. Call `shape_to_points(MaskShape(kind="ellipse", bounds=(0,0,1,1), sample_count=32))`.
2. Assert `len(points) == 32`.
3. Assert `points[0] == (1.0, 0.5)` within 1e-9 tolerance (3 o'clock in unit-square ellipse).
4. Also confirm custom `sample_count=8` returns exactly 8 points.
5. Confirm `sample_count=3` raises `ValueError` (degenerate, per Edge Cases).

## Expected Results
- Default returns 32 points, first at `(1.0, 0.5)`.
- `sample_count=8` returns 8 points.
- `sample_count < 4` raises `ValueError`.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_shape_to_points_ellipse -v`

## Pass / Fail Criteria
- **Pass:** all three assertions hold.
- **Fail:** wrong count, wrong first point, or missing degeneracy check.
