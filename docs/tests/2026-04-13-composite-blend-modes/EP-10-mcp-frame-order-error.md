---
scenario_id: "EP-10"
title: "composite_set end_frame <= start_frame returns _err"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] MCP frame ordering"]
tags: [test-scenario, mcp, behavioral, error-path]
---

# Scenario EP-10: MCP frame ordering error

## Steps
1. Set up workspace + fixture.
2. Parametrize `(start, end)` across `[(10, 10), (20, 10)]`.
3. Call `composite_set(..., start_frame=start, end_frame=end, ...)`.
4. Assert `result["status"] == "err"` for each.

## Expected Results
- Both zero-length and inverted ranges return `_err`.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_frame_ordering_err -v`

## Pass / Fail Criteria
- **Pass:** Both cases return `_err`.
- **Fail:** Any case returns ok or raises.
