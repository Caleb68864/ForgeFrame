---
scenario_id: "SR-21"
title: "server/tools.py registers effects_copy, effects_paste, effect_reorder"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
  - integration
---

# Scenario SR-21: MCP tool registration

## Description
Verifies `[STRUCTURAL]`/`[INTEGRATION]` -- the three new tools register on the MCP server and are importable as plain callables from `workshop_video_brain.edit_mcp.server.tools`.

## Preconditions
- Sub-Spec 3 merged.

## Steps
1. Import `from workshop_video_brain.edit_mcp.server import tools as t`.
2. Assert `callable(t.effects_copy)`, `callable(t.effects_paste)`, `callable(t.effect_reorder)`.
3. Inspect MCP registry (e.g. `mcp.list_tools()` or equivalent) and assert all three names appear with non-empty descriptions.
4. Inspect `effects_paste` parameter schema and assert `mode` defaults to `"append"`, `stack` is typed string (JSON).

## Expected Results
- All three callables present and registered with the MCP server.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_ops_mcp_tools.py::test_registration -v`

## Pass / Fail Criteria
- **Pass:** All present and registered.
- **Fail:** Missing tool or registration.
