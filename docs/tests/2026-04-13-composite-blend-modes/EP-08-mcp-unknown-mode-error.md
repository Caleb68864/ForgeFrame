---
scenario_id: "EP-08"
title: "composite_set unknown mode returns _err listing all 11 modes"
tool: "bash"
type: test-scenario
covers: ["[BEHAVIORAL] MCP unknown mode"]
tags: [test-scenario, mcp, behavioral, error-path, critical]
---

# Scenario EP-08: MCP unknown mode error

## Description
Spec Requirement 8 at MCP boundary: unknown mode returns `_err` shape and the error message lists all 11 valid modes.

## Preconditions
- Workspace set up.

## Steps
1. Set up workspace with fixture.
2. Call `composite_set(..., blend_mode="banana")`.
3. Assert `result["status"] == "err"`.
4. Assert `result["error"]` (or message field per `_err` convention) contains `"banana"`.
5. Assert every member of the 11 `BLEND_MODES` appears in the message.

## Expected Results
- `_err` result with informative message.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_unknown_mode_err -v`

## Pass / Fail Criteria
- **Pass:** Error shape correct; message complete.
- **Fail:** Exception escaped, missing identifiers in message.
