---
scenario_id: "SR-27"
title: "End-to-end: mask_set_shape(ellipse) produces 32-point spline"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-27: End-to-end: mask_set_shape(ellipse) produces 32-point spline

## Description
Verifies [BEHAVIORAL] that `mask_set_shape(shape="ellipse")` produces a rotoscoping filter whose spline property contains exactly 32 points (default `sample_count`).

## Preconditions
- Fresh workspace + project fixture, clip at track=2/clip=0.

## Steps
1. Call `mask_set_shape(..., shape="ellipse", bounds="[0,0,1,1]")`.
2. Re-read project from disk, parse MLT XML.
3. Locate the newly inserted rotoscoping filter.
4. Parse its points-list property and count entries.

## Expected Results
- Exactly 32 points.
- First point corresponds to 3 o'clock in ellipse-local space (angle 0).

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_mask_set_shape_ellipse -v`

## Pass / Fail Criteria
- **Pass:** 32 points, first at 3 o'clock.
- **Fail:** wrong count or wrong starting angle.
