---
scenario_id: "SR-05"
title: "shape_to_points — polygon passes through unchanged"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-1
---

# Scenario SR-05: shape_to_points — polygon passes through unchanged

## Description
Verifies [BEHAVIORAL] polygon passthrough: supplied points are returned as-is with no reordering, deduplication, or augmentation.

## Preconditions
- Module importable.

## Steps
1. Call `shape_to_points(MaskShape(kind="polygon", points=((0.1, 0.1), (0.5, 0.1), (0.3, 0.5))))`.
2. Compare against the input tuple.

## Expected Results
- Returned points equal `((0.1, 0.1), (0.5, 0.1), (0.3, 0.5))` exactly.
- Order preserved; no implicit closing point added.

## Execution Tool
bash — `uv run pytest tests/unit/test_masking_pipeline.py::test_shape_to_points_polygon_passthrough -v`

## Pass / Fail Criteria
- **Pass:** identical tuple returned.
- **Fail:** any reordering, insertion, or count change.
