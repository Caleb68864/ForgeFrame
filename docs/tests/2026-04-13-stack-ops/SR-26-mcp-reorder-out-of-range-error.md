---
scenario_id: "SR-26"
title: "effect_reorder out-of-range from_index returns _err with stack length"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - behavioral
  - error-path
---

# Scenario SR-26: MCP reorder out-of-range error envelope

## Description
Verifies `[BEHAVIORAL]` -- the MCP tool wraps the patcher's `IndexError` in an `_err` envelope (`{"status":"error","message":<str>}`) whose message names the current stack length.

## Preconditions
- Fresh workspace; clip with N filters known.

## Steps
1. `result = effect_reorder(workspace, project_file, track=2, clip=0, from_index=N+5, to_index=0)`.
2. Assert `result["status"] == "error"`.
3. Assert `str(N)` substring in `result["message"]`.
4. Repeat with `to_index=N+5` and `from_index=-1`; same envelope expected.
5. Confirm no snapshot mutation occurred (project file unchanged).

## Expected Results
- Error envelope returned (no exception out of MCP boundary); message names current stack length; no state change.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_reorder_out_of_range -v`

## Pass / Fail Criteria
- **Pass:** Error envelope with length, no mutation.
- **Fail:** Exception escapes MCP layer or state mutated.
