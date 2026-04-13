---
scenario_id: "SR-31"
title: "MCP integration test file passes"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - mechanical
---

# Scenario SR-31: tests/integration/test_stack_ops_mcp_tools.py passes

## Description
Verifies `[MECHANICAL]` gate from Sub-Spec 3.

## Preconditions
- Sub-Spec 3 merged with `tests/integration/test_stack_ops_mcp_tools.py`.

## Steps
1. Run `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v`.

## Expected Results
- Exit 0; all PASSED.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py -v`

## Pass / Fail Criteria
- **Pass:** Exit 0.
- **Fail:** Any failure.
