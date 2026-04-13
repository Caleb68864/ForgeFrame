---
scenario_id: "SR-26"
title: "End-to-end: mask_set_shape(rect) persists rotoscoping filter on disk"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
  - sequential
---

# Scenario SR-26: End-to-end: mask_set_shape(rect) persists rotoscoping filter on disk

## Description
Verifies [BEHAVIORAL] end-to-end that `mask_set_shape(rect, bounds=[0.2, 0.2, 0.6, 0.6])` inserts a rotoscoping filter at `effect_index=0` on the target clip, and the filter is readable back from disk with expected properties.

## Preconditions
- Fresh workspace + .kdenlive project fixture with at least one clip on track 2.
- Clip initially has zero filters.

## Steps
1. Call `mask_set_shape(workspace_path, project_file, track=2, clip=0, shape="rect", bounds="[0.2,0.2,0.6,0.6]")`.
2. Assert `data.effect_index == 0` and `data.type == "rotoscoping"`.
3. Re-open the project file from disk, parse MLT XML.
4. Locate the clip's filters; assert a filter with `mlt_service="rotoscoping"` is present as the first filter (index 0).
5. Assert the filter's points property contains exactly 4 points matching the rect corners for bounds `(0.2, 0.2, 0.6, 0.6)`.

## Expected Results
- Filter persisted at index 0.
- Service is `rotoscoping`.
- 4 points present and correct.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_e2e_mask_set_shape_rect -v`

## Pass / Fail Criteria
- **Pass:** all three asserts pass after re-parse.
- **Fail:** filter missing, wrong index, wrong service, or wrong points.
