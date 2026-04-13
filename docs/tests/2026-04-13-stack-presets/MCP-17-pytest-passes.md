---
scenario_id: "MCP-17"
title: "tests/integration/test_stack_presets_mcp_tools.py passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - mechanical
---

# Scenario MCP-17: MCP integration pytest passes

## Description
Verifies `[MECHANICAL]` -- the new MCP integration test file passes end-to-end.

## Preconditions
- All Sub-Spec 3 implementation complete; all MCP-* scenarios implemented.

## Steps
1. Run `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v`.

## Expected Results
- Exit code 0.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py -v`

## Pass / Fail Criteria
- **Pass:** Zero failures/errors.
- **Fail:** Any failure.
