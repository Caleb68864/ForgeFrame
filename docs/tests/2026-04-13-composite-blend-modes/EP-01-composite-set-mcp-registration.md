---
scenario_id: "EP-01"
title: "composite_set registered as an MCP tool"
tool: "bash"
type: test-scenario
covers: ["[STRUCTURAL] tool registration"]
tags: [test-scenario, mcp, structural, critical]
---

# Scenario EP-01: composite_set registered as an MCP tool

## Description
Verifies the `composite_set` callable is registered with the FastMCP `mcp` instance via `@mcp.tool()` (spec Requirement 6 and Sub-Spec 2 STRUCTURAL).

## Preconditions
- Sub-Spec 2 implemented.

## Steps
1. Import `mcp` from `workshop_video_brain.edit_mcp.server.tools`.
2. Enumerate registered tools (e.g. via `await mcp.list_tools()` or inspecting `mcp._tool_manager` depending on FastMCP version -- mirror the pattern used by existing tests like `test_mcp_tools.py`).
3. Assert a tool named `composite_set` is present.
4. Assert its declared input schema contains parameters: `workspace_path, project_file, track_a, track_b, start_frame, end_frame, blend_mode, geometry`.
5. Assert `blend_mode` default is `"cairoblend"` and `geometry` default is `""`.

## Expected Results
- Tool registered under the exact name `composite_set`.
- Schema matches spec signature.

## Execution Tool
bash -- `uv run pytest tests/integration/test_composite_set_mcp_tool.py::test_composite_set_registered -v`

## Pass / Fail Criteria
- **Pass:** Tool found with correct schema.
- **Fail:** Missing tool, wrong name, wrong schema.
