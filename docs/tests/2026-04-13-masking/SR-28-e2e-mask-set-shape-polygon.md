---
scenario_id: "SR-28"
title: "End-to-end: mask_set_shape(polygon) writes exactly the supplied points"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-28: End-to-end: mask_set_shape(polygon) writes exactly the supplied points

## Description
Verifies [BEHAVIORAL] that `mask_set_shape(shape="polygon", points="[[0.1,0.1],[0.5,0.1],[0.3,0.5]]")` inserts a rotoscoping filter whose points property contains exactly those 3 points in order.

## Preconditions
- Fresh workspace + project fixture.

## Steps
1. Call `mask_set_shape(..., shape="polygon", points="[[0.1,0.1],[0.5,0.1],[0.3,0.5]]")`.
2. Re-read project from disk.
3. Parse the rotoscoping filter's points.
4. Assert exactly 3 points in order: `(0.1, 0.1), (0.5, 0.1), (0.3, 0.5)`.

## Expected Results
- 3 points, exact values, original order.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_mask_set_shape_polygon -v`

## Pass / Fail Criteria
- **Pass:** 3 points match.
- **Fail:** any mismatch.
