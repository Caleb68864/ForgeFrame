---
scenario_id: "SS3-01"
title: "effect_info MCP tool registered"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, structural]
---

# Scenario SS3-01: effect_info MCP tool registered

## Description
Verifies `[STRUCTURAL]` `server/tools.py` registers `@mcp.tool() effect_info(name: str) -> dict`.

## Preconditions
- Sub-Spec 3 implementation merged.

## Steps
1. Import `workshop_video_brain.edit_mcp.server.tools` and the `mcp` instance.
2. Inspect registered tool names (e.g. via FastMCP's tool registry).
3. Assert `"effect_info"` is registered.
4. Assert the underlying callable's signature is `(name: str) -> dict`.

## Expected Results
- Tool registered with documented signature.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_effect_info_registered -v`

## Pass / Fail Criteria
- **Pass:** Tool present + sig matches.
- **Fail:** Missing or wrong sig.
