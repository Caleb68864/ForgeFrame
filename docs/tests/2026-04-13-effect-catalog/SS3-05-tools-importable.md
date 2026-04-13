---
scenario_id: "SS3-05"
title: "All catalog tools importable as callables"
tool: "bash"
type: test-scenario
tags: [test-scenario, mcp, integration]
---

# Scenario SS3-05: All catalog tools importable as callables (INTEGRATION)

## Description
Verifies `[INTEGRATION]` requirement: `effect_info` and `effect_list_common` are importable as callables from `workshop_video_brain.edit_mcp.server.tools`.

## Preconditions
- Module importable.

## Steps
1. `from workshop_video_brain.edit_mcp.server.tools import effect_info, effect_list_common`.
2. Assert both are callable.
3. Call `effect_list_common()` directly (not via MCP transport); assert returns a dict with `status == "success"`.
4. Call `effect_info("acompressor")`; assert returns a dict with `status == "success"`.

## Expected Results
- Both directly importable + invokable without MCP transport.

## Execution Tool
bash -- `uv run pytest tests/integration/test_effect_catalog_mcp_tools.py::test_tools_importable -v`

## Pass / Fail Criteria
- **Pass:** Direct import + call succeeds.
- **Fail:** ImportError or wrapper-only access.
