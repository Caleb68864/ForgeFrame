---
scenario_id: "SR-36"
title: "mask_set_shape with unknown shape returns _err listing the three valid shapes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - behavioral
  - sub-spec-3
---

# Scenario SR-36: mask_set_shape with unknown shape returns _err listing the three valid shapes

## Description
Verifies [BEHAVIORAL] that `mask_set_shape(shape="triangle", ...)` returns an `_err` response listing the three valid shapes (`rect`, `ellipse`, `polygon`).

## Preconditions
- Workspace fixture ready.

## Steps
1. Call `mask_set_shape(..., shape="triangle")`.
2. Assert `_err` response.
3. Assert message contains `rect`, `ellipse`, `polygon`.
4. Assert no filter persisted.

## Expected Results
- `_err` with exhaustive shape list.
- Project unchanged.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_mask_set_shape_unknown_shape -v`

## Pass / Fail Criteria
- **Pass:** error with full list, project untouched.
- **Fail:** missing shape(s) or mutation occurred.
