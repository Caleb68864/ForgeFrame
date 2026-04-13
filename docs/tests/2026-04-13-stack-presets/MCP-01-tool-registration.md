---
scenario_id: "MCP-01"
title: "server/tools.py registers all four MCP tools"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario MCP-01: Four tools registered with FastMCP

## Description
Verifies `[STRUCTURAL]` -- `effect_stack_preset`, `effect_stack_apply`, `effect_stack_promote`, `effect_stack_list` are registered with the FastMCP server in `server/tools.py`.

## Preconditions
- `workshop_video_brain.edit_mcp.server.tools` import succeeds.

## Steps
1. Import the server module; obtain the FastMCP `mcp` instance.
2. Inspect registered tool names (via the FastMCP introspection API or the module-level decorator side effects).
3. Assert all four names are present.

## Expected Results
- All four tools registered.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_tools_registered -v`

## Pass / Fail Criteria
- **Pass:** All four found.
- **Fail:** Any missing.
