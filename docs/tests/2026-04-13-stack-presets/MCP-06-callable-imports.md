---
scenario_id: "MCP-06"
title: "All four tools importable as callables from server.tools"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
---

# Scenario MCP-06: Tool callable imports

## Description
Verifies `[INTEGRATION]` -- after `import workshop_video_brain.edit_mcp.server.tools`, the four tool names are importable as callables (not just registered with FastMCP).

## Preconditions
- Module importable.

## Steps
1. `from workshop_video_brain.edit_mcp.server.tools import effect_stack_preset, effect_stack_apply, effect_stack_promote, effect_stack_list`.
2. Assert each is `callable(...)`.

## Expected Results
- All four importable and callable.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_tool_imports -v`

## Pass / Fail Criteria
- **Pass:** Imports and callable checks pass.
- **Fail:** Otherwise.
