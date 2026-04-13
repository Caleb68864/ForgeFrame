---
scenario_id: "MCP-04"
title: "effect_stack_promote signature and return envelope"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
  - mcp
  - structural
---

# Scenario MCP-04: effect_stack_promote envelope shape

## Description
Verifies `[STRUCTURAL]` -- `effect_stack_promote(workspace_path, name)` returns `{"status","data":{"workspace_path":str,"vault_path":str}}`.

## Preconditions
- Workspace with a saved preset; a configured vault root.

## Steps
1. Inspect signature; assert exactly two parameters.
2. Call with valid args. Assert response: `status` and `data`; data has `workspace_path` and `vault_path` strings pointing to existing files.

## Expected Results
- Match.

## Execution Tool
bash -- `uv run pytest tests/integration/test_stack_presets_mcp_tools.py::test_promote_envelope -v`

## Pass / Fail Criteria
- **Pass:** Match.
- **Fail:** Otherwise.
