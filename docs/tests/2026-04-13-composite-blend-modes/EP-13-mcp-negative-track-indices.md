---
scenario_id: "EP-13"
title: "composite_set negative track indices return _err"
tool: "bash"
type: test-scenario
covers: ["Edge: negative track indices"]
tags: [test-scenario, mcp, behavioral, edge-case, error-path]
---

# Scenario EP-13: Negative track indices edge case

## Description
Spec Edge Case: negative track indices should be caught by `patch_project` and wrapped by `_err`.

## Steps
1. Set up workspace + fixture.
2. Call `composite_set(..., track_a=-1, track_b=2, ...)`.
3. Assert `result["status"] == "err"`.
4. Repeat with `track_a=1, track_b=-3` and assert the same.

## Expected Results
- Both calls return `_err` shape (no uncaught exception).

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_negative_track_indices -v`

## Pass / Fail Criteria
- **Pass:** Both cases produce `_err`.
- **Fail:** Exception escapes or silent success.
