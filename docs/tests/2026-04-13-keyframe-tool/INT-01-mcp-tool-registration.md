---
scenario_id: "INT-01"
title: "Four MCP tools registered and discoverable via introspection"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - integration
  - structural
---

# Scenario INT-01: MCP tool registration + introspection

## Description
Verifies [STRUCTURAL]+[INTEGRATION] Sub-Spec 4 -- `server/tools.py` registers `effect_keyframe_set_scalar`, `effect_keyframe_set_rect`, `effect_keyframe_set_color`, and `effect_find`; an MCP introspection query exposes all four.

## Preconditions
- MCP server importable; `server/tools.py` imports the new tools.
- Existing MCP registration pattern in place.

## Steps
1. Import the MCP server/app.
2. Enumerate registered tools via the server's introspection API (or the FastMCP registry).
3. Assert all four tool names present in the registry.
4. Boot the server in-process and query its tool list via an MCP client stub; assert the same four names appear.
5. Confirm no existing tool names were displaced or collided with.

## Expected Results
- All four tools listed via both the in-process registry and an MCP client query.
- Pre-existing tools still registered.

## Execution Tool
bash -- `uv run pytest tests/integration/test_keyframe_mcp_tools.py::test_registration -v`

## Pass / Fail Criteria
- **Pass:** Four tools discoverable via introspection.
- **Fail:** Any missing, misnamed, or collision.
