---
scenario_id: "SR-19"
title: "MCP tools module registers all six tools and they are importable callables"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - structural
  - integration
  - sub-spec-3
---

# Scenario SR-19: MCP tools module registers all six tools and they are importable callables

## Description
Verifies [STRUCTURAL] registration of all six new MCP tools in `server/tools.py` and [INTEGRATION] that they are importable as callables from `workshop_video_brain.edit_mcp.server.tools` after module import.

## Preconditions
- `uv sync` complete.

## Steps
1. Run: `uv run python -c "from workshop_video_brain.edit_mcp.server import tools; names=['mask_set','mask_set_shape','mask_apply','effect_chroma_key','effect_chroma_key_advanced','effect_object_mask']; print([(n, callable(getattr(tools, n, None))) for n in names])"`.
2. Additionally, query the FastMCP registry for tool registrations and assert all six tool names appear as registered MCP tools.

## Expected Results
- All six names resolve as callables.
- FastMCP registry lists all six.

## Execution Tool
bash — `uv run pytest tests/integration/test_masking_mcp_tools.py::test_tools_registered_and_importable -v`

## Pass / Fail Criteria
- **Pass:** all callable, all registered.
- **Fail:** any missing from module or registry.
