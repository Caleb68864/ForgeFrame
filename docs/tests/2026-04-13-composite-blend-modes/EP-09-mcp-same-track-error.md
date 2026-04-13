---
scenario_id: "EP-09"
title: "composite_set track_a == track_b returns _err"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] MCP same-track"]
tags: [test-scenario, mcp, behavioral, error-path]
---

# Scenario EP-09: MCP same-track error

## Steps
1. Set up workspace + fixture.
2. Call `composite_set(..., track_a=2, track_b=2, ...)`.
3. Assert `result["status"] == "err"`.
4. Assert error message references same-track condition.

## Expected Results
- `_err` shape returned; `ValueError` from pipeline caught and translated.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_same_track_err -v`

## Pass / Fail Criteria
- **Pass:** Error returned, no exception escaped.
- **Fail:** Silent success or uncaught exception.
